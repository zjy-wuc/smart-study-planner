"""V3.0 A4 管理端 AI 动态配置与共享 Guard 验收测试。

约束：
- 仅在隔离测试库 ssp_v3_admin_test 执行（模块导入即校验 SELECT DATABASE()）。
- 不修改业务源码；发现缺陷由断言暴露，保留失败用例。
- Redis 仅操作 ssp:ssp_v3_admin_test: 前缀的 key，不执行 FLUSHALL/FLUSHDB。
- 模型调用全部 Mock，不访问真实 DeepSeek。
- 每个用例前后把 ai_runtime_config(id=1) 恢复为基线
  (enabled=1, user_daily_limit=10, global_daily_limit=80)。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_a4_dynamic_config_acceptance.py -q
"""

import asyncio
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.config import settings
from app.core import security
from app.core.clock import business_today, utc_db_now
from app.core.practice_ticket import create_practice_ticket
from app.core.redis_client import redis_client
from app.database import SessionLocal, engine
from app.main import app as production_app
from app.repositories.admin import ai_config_repository
from app.repositories.knowledge import ai_guard_repository
from app.services.admin import ai_config_service
from app.services.knowledge import (
    ai_guard_service,
    ai_note_service,
    ai_practice_grading_service,
    ai_practice_service,
    ai_qa_service,
    ai_rate_limit_service,
    ai_runtime_service,
)
from app.services.knowledge.ai_service import (
    CheckedCompletionEvent,
    _sse as sse_frame,
)

from redis.exceptions import RedisError


# ============================================================
# 环境与常量
# ============================================================

ALLOWED_TEST_DBS = {"ssp_v3_admin_test"}
ALLOWED_REDIS_PREFIX = "ssp:ssp_v3_admin_test:"

PASSWORD = "AdminPass123"
ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}

BASELINE_CONFIG = {
    "enabled": 1,
    "user_daily_limit": 10,
    "global_daily_limit": 80,
}

PREFIX = f"a4{uuid.uuid4().hex[:8]}"


def _guard_database() -> str:
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT DATABASE()")).scalar_one()

    if db_name not in ALLOWED_TEST_DBS:
        raise RuntimeError(
            f"测试仅允许在隔离测试库执行，当前数据库: {db_name}"
        )

    return db_name


DB_NAME_NOW = _guard_database()


def _in(sql: str, key: str = "ids"):
    return text(sql).bindparams(bindparam(key, expanding=True))


def rate_key(user_id: int) -> str:
    """A4.2 起限流键为 ZSET v2；本文件适配精确滑动窗口。"""
    return f"ssp:{DB_NAME_NOW}:ai:rate:v2:{user_id}"


def rate_count(user_id: int) -> int:
    return int(redis_client.zcard(rate_key(user_id)))


def redis_now_ms() -> int:
    seconds, micros = redis_client.time()
    return int(seconds) * 1000 + int(micros) // 1000


def client_factory() -> TestClient:
    return TestClient(
        production_app,
        base_url="https://ssp.test",
        client=("127.0.0.1", 52410),
        raise_server_exceptions=False,
    )


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_headers(token: str) -> dict:
    return {**auth_headers(token), **CSRF_HEADERS}


def today():
    return business_today()


# ============================================================
# 配置读写（测试夹具，不写审计）
# ============================================================


def write_config(
    *,
    enabled: int = BASELINE_CONFIG["enabled"],
    user_daily_limit: int = BASELINE_CONFIG["user_daily_limit"],
    global_daily_limit: int = BASELINE_CONFIG["global_daily_limit"],
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ai_runtime_config "
                "SET enabled = :e, user_daily_limit = :u, "
                "global_daily_limit = :g "
                "WHERE id = 1"
            ),
            {
                "e": enabled,
                "u": user_daily_limit,
                "g": global_daily_limit,
            },
        )


def read_config_row() -> dict:
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT id, enabled, user_daily_limit, "
                    "global_daily_limit, updated_at "
                    "FROM ai_runtime_config WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """扩大登录 IP 限流，避免同 IP 多次登录互相影响；模型 key 使用测试值。"""

    old_pwd = settings.PASSWORD_IP_MAX_ATTEMPTS
    old_mail = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
    old_key = settings.DEEPSEEK_API_KEY

    settings.PASSWORD_IP_MAX_ATTEMPTS = 10 ** 9
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 10 ** 9
    # 不使用 .env 中的真实密钥；所有模型调用均被 Mock。
    settings.DEEPSEEK_API_KEY = "test-only-key"

    yield

    settings.PASSWORD_IP_MAX_ATTEMPTS = old_pwd
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = old_mail
    settings.DEEPSEEK_API_KEY = old_key


@pytest.fixture(autouse=True)
def baseline_config():
    """每个用例前后恢复运行时配置基线。"""

    write_config()
    yield
    write_config()


@pytest.fixture
def client():
    return client_factory()


# ============================================================
# 数据夹具
# ============================================================


class Factory:
    def __init__(self, client: TestClient):
        self.client = client
        self.user_ids: list[int] = []

    # ---------- 用户 / 登录 ----------

    def make_user(
        self,
        suffix: str = "u",
        *,
        role: str = "USER",
        created_at: datetime | None = None,
    ) -> dict:
        username = f"{PREFIX}{suffix}{uuid.uuid4().hex[:4]}"
        email = f"{username}@example.com"

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users ("
                    "username, password_hash, password_updated_at, "
                    "email, email_verified_at, nickname, role, created_at"
                    ") VALUES ("
                    ":username, :password_hash, :now, :email, :now, "
                    ":nickname, :role, "
                    "COALESCE(:created_at, CURRENT_TIMESTAMP)"
                    ")"
                ),
                {
                    "username": username,
                    "password_hash": security.hash_password(PASSWORD),
                    "now": utc_db_now(),
                    "email": email,
                    "nickname": username,
                    "role": role,
                    "created_at": created_at,
                },
            )
            user_id = int(result.lastrowid)

        self.user_ids.append(user_id)
        return {"id": user_id, "username": username, "email": email}

    def login(self, username: str) -> str:
        response = self.client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]["access_token"]

    def make_user_with_token(self, suffix: str = "u") -> dict:
        user = self.make_user(suffix)
        user["token"] = self.login(user["username"])
        return user

    def make_admin(self, suffix: str = "op") -> dict:
        admin = self.make_user(suffix, role="ADMIN")
        admin["token"] = self.login(admin["username"])
        return admin

    # ---------- 业务数据 ----------

    def make_note(
        self,
        user_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        deleted: bool = False,
    ) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO knowledge_notes "
                    "(user_id, title, content_md, deleted_at) "
                    "VALUES (:u, :t, :c, :d)"
                ),
                {
                    "u": user_id,
                    "t": title or f"A4 笔记 {uuid.uuid4().hex[:4]}",
                    "c": content or NOTE_CONTENT,
                    "d": utc_db_now() if deleted else None,
                },
            )
            return int(result.lastrowid)

    def make_ai_request(
        self,
        user_id: int,
        *,
        operation: str = "SUMMARY",
        status: str = "RUNNING",
        request_date=None,
        lease_seconds: int = 3600,
    ) -> str:
        request_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ai_requests ("
                    "request_id, user_id, note_id, operation, "
                    "request_date, status, leased_until"
                    ") VALUES ("
                    ":r, :u, NULL, :o, :d, :s, "
                    "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL :ls SECOND)"
                    ")"
                ),
                {
                    "r": request_id,
                    "u": user_id,
                    "o": operation,
                    "d": request_date or today(),
                    "s": status,
                    "ls": lease_seconds,
                },
            )
        return request_id

    def make_practice_record(
        self,
        user_id: int,
        *,
        generation_id: str | None = None,
        note_id: int | None = None,
        title: str = "A4 练习",
        score: float = 80.0,
    ) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO practice_records ("
                    "user_id, note_id, note_title_snapshot, "
                    "generation_id, question_count, score, questions_json"
                    ") VALUES ("
                    ":u, :n, :t, :g, 5, :s, :q"
                    ")"
                ),
                {
                    "u": user_id,
                    "n": note_id,
                    "t": title,
                    "g": generation_id or str(uuid.uuid4()),
                    "s": score,
                    "q": json.dumps(
                        [
                            {
                                "id": f"q{index}",
                                "type": "SINGLE_CHOICE",
                            }
                            for index in range(1, 6)
                        ],
                        ensure_ascii=False,
                    ),
                },
            )
            return int(result.lastrowid)

    # ---------- 清理 ----------

    def cleanup(self) -> None:
        ids = list(self.user_ids)

        try:
            with engine.begin() as conn:
                if ids:
                    params = {"ids": ids}
                    plan_ids = [
                        row[0]
                        for row in conn.execute(
                            _in(
                                "SELECT id FROM study_plans "
                                "WHERE user_id IN :ids"
                            ),
                            params,
                        )
                    ]

                    conn.execute(
                        _in(
                            "DELETE FROM admin_audit_logs "
                            "WHERE admin_id IN :ids OR target_id IN :ids"
                        ),
                        params,
                    )
                    for table in (
                        "refresh_tokens",
                        "login_sessions",
                        "auth_events",
                        "email_verifications",
                    ):
                        conn.execute(
                            _in(
                                f"DELETE FROM {table} WHERE user_id IN :ids"
                            ),
                            params,
                        )

                    conn.execute(
                        _in(
                            "DELETE FROM practice_records "
                            "WHERE user_id IN :ids"
                        ),
                        params,
                    )
                    conn.execute(
                        _in(
                            "DELETE FROM ai_requests WHERE user_id IN :ids"
                        ),
                        params,
                    )
                    conn.execute(
                        _in(
                            "DELETE FROM study_records "
                            "WHERE user_id IN :ids"
                        ),
                        params,
                    )
                    conn.execute(
                        _in(
                            "DELETE FROM knowledge_notes "
                            "WHERE user_id IN :ids"
                        ),
                        params,
                    )

                    if plan_ids:
                        plan_params = {"pids": plan_ids}
                        conn.execute(
                            _in(
                                "DELETE FROM daily_tasks "
                                "WHERE plan_id IN :pids",
                                "pids",
                            ),
                            plan_params,
                        )
                        conn.execute(
                            _in(
                                "DELETE FROM plan_steps "
                                "WHERE plan_id IN :pids",
                                "pids",
                            ),
                            plan_params,
                        )

                    conn.execute(
                        _in(
                            "DELETE FROM study_plans WHERE user_id IN :ids"
                        ),
                        params,
                    )
                    conn.execute(
                        _in("DELETE FROM users WHERE id IN :ids"),
                        params,
                    )
        finally:
            for user_id in ids:
                try:
                    redis_client.delete(rate_key(user_id))
                except RedisError:
                    pass


@pytest.fixture
def factory(client):
    instance = Factory(client)
    yield instance
    instance.cleanup()


# ============================================================
# 通用工具
# ============================================================

NOTE_CONTENT = (
    "JWT Access Token 用于访问受保护资源，"
    "Refresh Token 用于续期并支持轮换，"
    "轮换后旧令牌立即失效，可用于检测重放攻击。"
)

MARKDOWN_OUTPUT = "# JWT 认证\n\n## 核心概念\n\nAccess Token 用于访问受保护资源。"

SUMMARY_OUTPUT = (
    "## 核心概述\nJWT 使用双令牌机制。\n"
    "## 关键知识点\n- Access Token 用于鉴权\n"
    "## 知识提纲\n1. 令牌概念\n2. 令牌轮换"
)

PRACTICE_OUTPUT = json.dumps(
    {
        "questions": [
            {
                "type": "SINGLE_CHOICE",
                "stem": "JWT 中 Access Token 的主要用途是什么？",
                "options": {
                    "A": "访问受保护资源",
                    "B": "创建数据库索引",
                    "C": "保存用户密码",
                    "D": "执行系统命令",
                },
                "correct_answer": "A",
                "explanation": "Access Token 用于鉴权。",
            },
            {
                "type": "SINGLE_CHOICE",
                "stem": "Refresh Token 轮换后旧令牌会怎样？",
                "options": {
                    "A": "永久有效",
                    "B": "立即失效",
                    "C": "变成密码",
                    "D": "自动续期",
                },
                "correct_answer": "B",
                "explanation": "轮换后旧令牌失效。",
            },
            {
                "type": "SINGLE_CHOICE",
                "stem": "以下哪项属于 JWT 的安全实现要求？",
                "options": {
                    "A": "只在前端校验",
                    "B": "跳过签名校验",
                    "C": "服务端强制校验令牌",
                    "D": "明文保存令牌",
                },
                "correct_answer": "C",
                "explanation": "令牌必须由服务端校验。",
            },
            {
                "type": "SHORT_ANSWER",
                "stem": "请说明 Refresh Token 轮换的作用。",
                "reference_answer": "生成新令牌、旧令牌失效并检测重放。",
                "grading_points": ["旧令牌失效", "检测重放"],
                "explanation": "轮换有助于识别异常使用。",
            },
            {
                "type": "SHORT_ANSWER",
                "stem": "请比较两类令牌的职责区别。",
                "reference_answer": "Access 用于鉴权，Refresh 用于续期。",
                "grading_points": ["Access 鉴权", "Refresh 续期"],
                "explanation": "两者职责不同。",
            },
        ]
    },
    ensure_ascii=False,
)


class ModelMock:
    """按 Prompt 内容返回合法结果的 Mock 模型边界。"""

    def __init__(self):
        self.calls: list[list[dict]] = []

    def install(self, monkeypatch) -> None:
        for module in (
            ai_note_service,
            ai_qa_service,
            ai_practice_service,
            ai_practice_grading_service,
        ):
            monkeypatch.setattr(
                module,
                "stream_checked_completion",
                self._fake_stream,
            )

    @staticmethod
    def _grading_output(messages: list[dict]) -> str:
        joined = "\n".join(item["content"] for item in messages)
        ids = list(dict.fromkeys(re.findall(r'"id":\s*"(q\d+)"', joined)))
        return json.dumps(
            {
                "grades": [
                    {
                        "id": question_id,
                        "score": 80,
                        "mastered_points": ["部分掌握"],
                        "missing_points": ["仍需补充"],
                        "suggestion": "继续完善答案。",
                    }
                    for question_id in ids
                ]
            },
            ensure_ascii=False,
        )

    async def _fake_stream(self, messages):
        self.calls.append(messages)
        system_prompt = messages[0]["content"]

        if "知识笔记总结助手" in system_prompt:
            output = SUMMARY_OUTPUT
        elif "学习练习出题助手" in system_prompt:
            output = PRACTICE_OUTPUT
        elif "简答题批改助手" in system_prompt:
            output = self._grading_output(messages)
        else:
            output = MARKDOWN_OUTPUT

        split = min(20, len(output))
        yield CheckedCompletionEvent(
            kind="delta", text=output[:split]
        )
        yield CheckedCompletionEvent(
            kind="delta", text=output[split:]
        )
        yield CheckedCompletionEvent(
            kind="finish",
            text=output,
            usage={"prompt_tokens": 7, "completion_tokens": 11},
        )


def collect_frames(generator) -> list[str]:
    async def run():
        return [frame async for frame in generator]

    return asyncio.run(run())


def sse_events(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in response.text.strip().split("\n\n"):
        if not block.strip():
            continue
        name = None
        payload: dict = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                value = json.loads(line[len("data: "):])
                payload = value if isinstance(value, dict) else {}
        if name is not None:
            events.append((name, payload))
    return events


def admit(user_id: int, operation: str = "SUMMARY", note_id=None):
    with SessionLocal() as db:
        return ai_guard_service.admit_request(
            db=db,
            user_id=user_id,
            note_id=note_id,
            operation=operation,
        )


def admit_error(user_id: int, operation: str = "SUMMARY") -> HTTPException:
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user_id,
                note_id=None,
                operation=operation,
            )
    return exc_info.value


def settle(request_id: str, status: str = "SUCCESS") -> None:
    with SessionLocal() as db:
        ai_guard_repository.finish_request(
            db=db,
            request_id=request_id,
            status=status,
            prompt_tokens=None,
            completion_tokens=None,
        )
        db.commit()


def admit_and_settle(user_id: int, operation: str = "SUMMARY", note_id=None):
    admission = admit(user_id, operation, note_id)
    settle(admission.request_id, "SUCCESS")
    return admission


def ai_request_count(user_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM ai_requests "
                    "WHERE user_id = :u AND request_date = :d"
                ),
                {"u": user_id, "d": today()},
            ).scalar_one()
        )


def ai_request_status(request_id: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status FROM ai_requests "
                "WHERE request_id = :r"
            ),
            {"r": request_id},
        ).scalar_one()


def audit_count(admin_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM admin_audit_logs "
                    "WHERE admin_id = :a AND action = 'UPDATE_AI_CONFIG'"
                ),
                {"a": admin_id},
            ).scalar_one()
        )


def as_json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def patch_config(
    client: TestClient,
    token: str,
    body: dict,
    *,
    with_csrf: bool = True,
):
    headers = auth_headers(token)
    if with_csrf:
        headers.update(CSRF_HEADERS)
    return client.patch("/admin/ai/config", json=body, headers=headers)


# ---------- 练习凭证 ----------


def _choice_question(index: int) -> dict:
    topics = [
        ("JWT 中 Access Token 的主要用途是什么？", "A"),
        ("Refresh Token 轮换后旧令牌会怎样？", "B"),
        ("以下哪项属于安全实现要求？", "C"),
        ("令牌失效后应如何处理请求？", "D"),
        ("服务端校验令牌的主要目的是什么？", "A"),
    ]
    stem, answer = topics[index - 1]
    return {
        "id": f"q{index}",
        "type": "SINGLE_CHOICE",
        "stem": stem,
        "options": {
            "A": "访问受保护资源",
            "B": "立即失效旧令牌",
            "C": "服务端强制校验",
            "D": "拒绝并重新登录",
        },
        "correct_answer": answer,
        "explanation": "依据笔记内容作答。",
    }


def _short_question(index: int) -> dict:
    topics = [
        ("请说明 Refresh Token 轮换的作用。", "旧令牌失效并检测重放。"),
        ("请比较两类令牌的职责区别。", "Access 鉴权，Refresh 续期。"),
    ]
    stem, reference = topics[index - 1]
    return {
        "id": f"q{index}",
        "type": "SHORT_ANSWER",
        "stem": stem,
        "reference_answer": reference,
        "grading_points": ["核心要点"],
        "explanation": "依据笔记内容作答。",
    }


def build_paper(
    user_id: int,
    *,
    note_id: int | None = None,
    generation_id: str | None = None,
    short_answers: bool = True,
    question_count: int = 5,
) -> dict:
    questions = []
    if short_answers:
        choice_count = question_count - 2
    else:
        choice_count = question_count

    for index in range(1, choice_count + 1):
        questions.append(_choice_question(index))
    for offset in range(question_count - choice_count):
        question = _short_question(offset + 1)
        question["id"] = f"q{choice_count + offset + 1}"
        questions.append(question)

    return {
        "purpose": "A5_GENERATION",
        "version": 1,
        "generation_id": generation_id or str(uuid.uuid4()),
        "user_id": user_id,
        "note_id": note_id or 999999,
        "note_title_snapshot": "JWT 认证",
        "note_version": "v1",
        "note_content": NOTE_CONTENT,
        "question_count": question_count,
        "questions": questions,
    }


def make_ticket(paper: dict) -> str:
    return create_practice_ticket(paper)


def default_answers(paper: dict, *, include_short: bool = False) -> list[dict]:
    answers = []
    for question in paper["questions"]:
        if question["type"] == "SINGLE_CHOICE":
            answers.append(
                {
                    "id": question["id"],
                    "answer": question["correct_answer"],
                }
            )
        elif include_short:
            answers.append(
                {
                    "id": question["id"],
                    "answer": "生成新令牌，并让旧令牌失效。",
                }
            )
    return answers


# ============================================================
# 1. Redis 原子限流
# ============================================================


def test_rate_limit_six_allowed_seventh_rejected(factory):
    user = factory.make_user("rl")

    for _ in range(6):
        admit_and_settle(user["id"])

    exc = admit_error(user["id"])

    assert exc.status_code == 429
    assert exc.detail["code"] == "AI_RATE_LIMIT"
    assert exc.headers and exc.headers.get("Retry-After")

    # 滑动窗口：被拒绝的请求不会写入成员，窗口内仍精确为 6。
    key = rate_key(user["id"])
    assert redis_client.zcard(key) == 6
    pttl = redis_client.pttl(key)
    assert 0 < pttl <= settings.AI_RATE_WINDOW_SECONDS * 1000


def test_rate_limit_ttl_recovery(factory):
    user = factory.make_user("ttl")
    for _ in range(6):
        admit_and_settle(user["id"])

    assert admit_error(user["id"]).detail["code"] == "AI_RATE_LIMIT"

    key = rate_key(user["id"])
    redis_client.pexpire(key, 1000)
    time.sleep(1.2)

    # 窗口过期后计数重新开始，当前额度充足。
    admission = admit_and_settle(user["id"])
    assert admission.user_id == user["id"]
    assert redis_client.zcard(key) == 1


def test_http_429_keeps_retry_after_header(factory):
    """统一异常处理器必须透传 Retry-After，而不是只保留在 HTTPException。"""

    user = factory.make_user_with_token("hdr")
    key = rate_key(user["id"])

    # 预置窗口内已用 6 次（ZSET v2），下一次请求必定被 Redis 频控拒绝。
    now = redis_now_ms()
    redis_client.zadd(key, {f"prefill-{i}": now for i in range(6)})
    redis_client.pexpire(key, 60000)

    response = factory.client.post(
        "/notes/ai/generate",
        json={"topic": "动态配置验收"},
        headers=auth_headers(user["token"]),
    )

    assert response.status_code == 429, response.text
    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None, response.headers
    assert int(retry_after) >= 1

    body = response.json()
    assert body["detail"]["code"] == "AI_RATE_LIMIT"
    assert body["detail"]["retry_after"] == int(retry_after)
    assert ai_request_count(user["id"]) == 0


def test_rate_limit_isolated_between_users(factory):
    first = factory.make_user("iso1")
    second = factory.make_user("iso2")

    for _ in range(6):
        admit_and_settle(first["id"])

    assert admit_error(first["id"]).detail["code"] == "AI_RATE_LIMIT"

    # 另一个用户不受影响。
    admit_and_settle(second["id"])
    assert rate_count(second["id"]) == 1


def test_rate_limit_threadsafe_count_is_exact(factory, monkeypatch):
    user = factory.make_user("thr")

    # 隔离并发信号：本用例只验证 Redis 原子计数，
    # 并发上限由第 7 组单独覆盖。
    monkeypatch.setattr(settings, "AI_USER_CONCURRENCY", 50)
    monkeypatch.setattr(settings, "AI_GLOBAL_CONCURRENCY", 50)

    results: list[tuple[str, str | None]] = []

    def worker(_index: int) -> None:
        with SessionLocal() as db:
            try:
                admission = ai_guard_service.admit_request(
                    db=db,
                    user_id=user["id"],
                    note_id=None,
                    operation="SUMMARY",
                )
            except HTTPException as exc:
                results.append(("error", exc.detail.get("code")))
                return

        settle(admission.request_id, "SUCCESS")
        results.append(("ok", None))

    threads = [
        threading.Thread(target=worker, args=(index,))
        for index in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "限流并发测试疑似死锁"

    successes = [item for item in results if item[0] == "ok"]
    errors = [item for item in results if item[0] == "error"]

    assert len(successes) == 6
    assert len(errors) == 2
    assert all(code == "AI_RATE_LIMIT" for _, code in errors)

    # 计数精确：仅 6 次成功请求写入窗口，超限请求不新增成员。
    assert rate_count(user["id"]) == 6


# ============================================================
# 2. Redis 不可用
# ============================================================


def test_redis_unavailable_returns_503_while_notes_still_work(
    factory, monkeypatch
):
    user = factory.make_user_with_token("redis")

    def boom(*args, **kwargs):
        raise RedisError("redis down")

    # A4.2 使用 register_script 注册的滑动窗口脚本，替换脚本入口模拟 Redis 不可用。
    monkeypatch.setattr(
        ai_rate_limit_service,
        "sliding_window_script",
        boom,
    )

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    assert exc_info.value.status_code == 503
    assert (
        exc_info.value.detail["code"] == "AI_RATE_LIMIT_UNAVAILABLE"
    )

    # 同一时刻普通学习接口不受 Redis 影响。
    response = factory.client.get(
        "/notes", headers=auth_headers(user["token"])
    )
    assert response.status_code == 200, response.text


# ============================================================
# 3. 管理员配置权限与校验
# ============================================================


def test_config_permissions(factory):
    admin = factory.make_admin()
    user = factory.make_user_with_token("perm")

    response = factory.client.get(
        "/admin/ai/config", headers=auth_headers(admin["token"])
    )
    assert response.status_code == 200, response.text
    assert "effective_user_daily_limit" in response.json()["data"]

    response = factory.client.get(
        "/admin/ai/config", headers=auth_headers(user["token"])
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ADMIN_REQUIRED"

    response = factory.client.get("/admin/ai/config")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"

    # 普通用户带 CSRF 也不能修改配置。
    response = patch_config(
        factory.client,
        user["token"],
        {"user_daily_limit": 9, "reason": "A4 普通用户尝试"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ADMIN_REQUIRED"

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 9, "reason": "A4 管理员修改"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["changed"] is True


def test_config_requires_csrf(factory):
    admin = factory.make_admin()

    response = patch_config(
        factory.client,
        admin["token"],
        {"enabled": False, "reason": "A4 缺少 CSRF"},
        with_csrf=False,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_REJECTED"


@pytest.mark.parametrize(
    "body",
    [
        {"user_daily_limit": 0, "reason": "A4 零额度"},
        {"user_daily_limit": -1, "reason": "A4 负额度"},
        {"user_daily_limit": "10", "reason": "A4 字符串额度"},
        {"user_daily_limit": True, "reason": "A4 布尔额度"},
        {"user_daily_limit": 1.5, "reason": "A4 浮点额度"},
        {"global_daily_limit": 0, "reason": "A4 全站零额度"},
    ],
)
def test_config_rejects_illegal_limits(factory, body):
    admin = factory.make_admin()

    response = patch_config(factory.client, admin["token"], body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == 422


def test_config_user_limit_cannot_exceed_global(factory):
    admin = factory.make_admin()

    response = patch_config(
        factory.client,
        admin["token"],
        {
            "user_daily_limit": 20,
            "global_daily_limit": 10,
            "reason": "A4 用户额度大于全站",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "AI_CONFIG_INVALID"


@pytest.mark.parametrize(
    "body",
    [
        {"user_daily_limit": 51, "reason": "A4 超过用户硬上限"},
        {
            "user_daily_limit": 50,
            "global_daily_limit": 201,
            "reason": "A4 超过全站硬上限",
        },
    ],
)
def test_config_rejects_values_above_hard_limits(factory, body):
    admin = factory.make_admin()

    response = patch_config(factory.client, admin["token"], body)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "AI_CONFIG_INVALID"


@pytest.mark.parametrize(
    "body",
    [
        {"user_daily_limit": 9},
        {"user_daily_limit": 9, "reason": ""},
        {"user_daily_limit": 9, "reason": "x" * 201},
        {"user_daily_limit": 9, "reason": "A4", "unknown": 1},
    ],
)
def test_config_reason_and_unknown_fields(factory, body):
    admin = factory.make_admin()

    response = patch_config(factory.client, admin["token"], body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == 422


# ============================================================
# 4. 配置与审计同事务
# ============================================================


def test_config_patch_writes_config_and_audit(factory):
    admin = factory.make_admin()
    before = read_config_row()

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 9, "reason": "A4 审计验证"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["changed"] is True

    after = read_config_row()
    assert int(after["user_daily_limit"]) == 9
    assert int(after["enabled"]) == int(before["enabled"])
    assert int(after["global_daily_limit"]) == int(
        before["global_daily_limit"]
    )

    with engine.connect() as conn:
        logs = conn.execute(
            text(
                "SELECT action, target_type, target_id, "
                "before_data, after_data, reason "
                "FROM admin_audit_logs "
                "WHERE admin_id = :a AND action = 'UPDATE_AI_CONFIG'"
            ),
            {"a": admin["id"]},
        ).mappings().all()

    assert len(logs) == 1
    log = logs[0]
    assert log["target_type"] == "AI_CONFIG"
    assert int(log["target_id"]) == 1

    before_data = as_json_dict(log["before_data"])
    after_data = as_json_dict(log["after_data"])
    assert before_data["user_daily_limit"] == int(before["user_daily_limit"])
    assert before_data["global_daily_limit"] == int(
        before["global_daily_limit"]
    )
    assert after_data["user_daily_limit"] == 9
    assert after_data["global_daily_limit"] == int(
        before["global_daily_limit"]
    )


def test_config_audit_failure_rolls_back(factory, monkeypatch):
    admin = factory.make_admin()
    before = read_config_row()
    audits_before = audit_count(admin["id"])

    def boom(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(
        ai_config_service.audit_repository,
        "insert_audit_log",
        boom,
    )

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 7, "reason": "A4 审计失败回滚"},
    )

    assert response.status_code == 500, response.text

    after = read_config_row()
    assert int(after["user_daily_limit"]) == int(before["user_daily_limit"])
    assert int(after["global_daily_limit"]) == int(
        before["global_daily_limit"]
    )
    assert int(after["enabled"]) == int(before["enabled"])
    assert audit_count(admin["id"]) == audits_before


def test_config_unchanged_writes_no_audit(factory):
    admin = factory.make_admin()
    current = read_config_row()
    audits_before = audit_count(admin["id"])

    response = patch_config(
        factory.client,
        admin["token"],
        {
            "enabled": bool(current["enabled"]),
            "user_daily_limit": int(current["user_daily_limit"]),
            "global_daily_limit": int(current["global_daily_limit"]),
            "reason": "A4 无实际变更",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["changed"] is False
    assert audit_count(admin["id"]) == audits_before


# ============================================================
# 5. AI 总开关
# ============================================================


def test_ai_disabled_blocks_all_six_entries(factory, monkeypatch):
    model = ModelMock()
    model.install(monkeypatch)

    admin = factory.make_admin()
    user = factory.make_user_with_token("off")
    note_id = factory.make_note(user["id"])

    response = patch_config(
        factory.client,
        admin["token"],
        {"enabled": False, "reason": "A4 关闭 AI"},
    )
    assert response.status_code == 200, response.text

    paper = build_paper(user["id"], note_id=note_id)
    ticket = make_ticket(paper)

    requests = [
        ("/notes/ai/generate", {"topic": "动态配置验收"}),
        (f"/notes/{note_id}/ai/organize", None),
        (f"/notes/{note_id}/ai/summary", None),
        (f"/notes/{note_id}/ai/ask", {"question": "JWT 是什么？"}),
        ("/ai/practices/generate", {"note_id": note_id, "question_count": 5}),
        (
            "/ai/practices/submit",
            {
                "practice_ticket": ticket,
                "answers": default_answers(paper, include_short=True),
            },
        ),
    ]

    used_before = ai_request_count(user["id"])

    for path, body in requests:
        if body is None:
            response = factory.client.post(
                path, headers=auth_headers(user["token"])
            )
        else:
            response = factory.client.post(
                path,
                json=body,
                headers=auth_headers(user["token"]),
            )

        assert response.status_code == 503, f"{path}: {response.text}"
        assert response.json()["detail"]["code"] == "AI_DISABLED", path

    assert model.calls == []
    assert ai_request_count(user["id"]) == used_before


def test_disable_mid_stream_does_not_break_running_stream(factory):
    user = factory.make_user("stream")
    note_id = factory.make_note(user["id"])
    admission = admit(user["id"], "SUMMARY", note_id)

    async def stream():
        yield sse_frame("start", {"mode": "summary"})
        # 流中途用另一个连接关闭 AI。
        write_config(enabled=0)
        yield sse_frame(
            "done",
            {"status": "success", "usage": {"completion_tokens": 2}},
        )

    frames = collect_frames(
        ai_guard_service.metered_ai_stream(admission, stream())
    )
    names = [
        frame.split("\n", 1)[0].removeprefix("event: ").strip()
        for frame in frames
    ]

    assert "done" in names
    assert ai_request_status(admission.request_id) == "SUCCESS"

    # 恢复开启后，当日已用额度不被重置。
    write_config(enabled=1)
    assert ai_request_count(user["id"]) == 1


def test_reenable_keeps_daily_usage(factory):
    user = factory.make_user("reenable")

    admit_and_settle(user["id"])
    used = ai_request_count(user["id"])
    assert used == 1

    write_config(enabled=0)
    assert ai_request_count(user["id"]) == used

    write_config(enabled=1)
    assert ai_request_count(user["id"]) == used

    # 额度连续累计，而不是重新从 0 开始。
    admit_and_settle(user["id"])
    assert ai_request_count(user["id"]) == used + 1


# ============================================================
# 6. 动态额度即时生效
# ============================================================


def test_dynamic_user_limit_raise_applies_immediately(factory):
    admin = factory.make_admin()
    user = factory.make_user("raise")

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 1, "reason": "A4 降低到 1"},
    )
    assert response.status_code == 200, response.text

    admit_and_settle(user["id"])
    exc = admit_error(user["id"])
    assert exc.detail["code"] == "AI_USER_DAILY_LIMIT"


def test_dynamic_user_limit_lower_rejects_used_over_new_limit(factory):
    admin = factory.make_admin()
    user = factory.make_user("lower")

    factory.make_ai_request(user["id"])
    factory.make_ai_request(user["id"])

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 1, "reason": "A4 已用超过新额度"},
    )
    assert response.status_code == 200, response.text

    exc = admit_error(user["id"])
    assert exc.detail["code"] == "AI_USER_DAILY_LIMIT"


def test_dynamic_global_limit_applies_immediately(factory):
    admin = factory.make_admin()
    user = factory.make_user("gusr")
    other = factory.make_user("gother")

    factory.make_ai_request(other["id"])
    factory.make_ai_request(other["id"])

    response = patch_config(
        factory.client,
        admin["token"],
        {
            "user_daily_limit": 2,
            "global_daily_limit": 2,
            "reason": "A4 全站额度 2",
        },
    )
    assert response.status_code == 200, response.text

    exc = admit_error(user["id"])
    assert exc.detail["code"] == "AI_GLOBAL_DAILY_LIMIT"


# ============================================================
# 7. MySQL 多连接竞争
# ============================================================


def test_mysql_concurrent_config_and_admission(factory):
    admin = factory.make_admin()
    user = factory.make_user("race")

    errors: list[BaseException] = []
    admitted: list[str] = []
    rejected_codes: list[str] = []
    start = threading.Barrier(2)

    def patch_worker():
        try:
            local_client = client_factory()
            start.wait(timeout=10)
            for index in range(6):
                limit = 5 if index % 2 == 0 else 6
                response = patch_config(
                    local_client,
                    admin["token"],
                    {
                        "user_daily_limit": limit,
                        "reason": f"A4 并发配置 {index}",
                    },
                )
                assert response.status_code == 200, response.text
                time.sleep(0.02)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def admit_worker():
        try:
            start.wait(timeout=10)
            for _ in range(10):
                # 本用例只验证 MySQL 竞争；隔离 Redis 频控计数。
                redis_client.delete(rate_key(user["id"]))
                with SessionLocal() as db:
                    try:
                        admission = ai_guard_service.admit_request(
                            db=db,
                            user_id=user["id"],
                            note_id=None,
                            operation="SUMMARY",
                        )
                    except HTTPException as exc:
                        rejected_codes.append(exc.detail.get("code"))
                        time.sleep(0.02)
                        continue

                admitted.append(admission.request_id)
                settle(admission.request_id, "SUCCESS")
                time.sleep(0.02)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=patch_worker),
        threading.Thread(target=admit_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), "PATCH 与准入并发疑似死锁"

    assert errors == []
    assert all(
        code == "AI_USER_DAILY_LIMIT" for code in rejected_codes
    )
    # 配置在 5/6 之间切换，准入数量不可突破当前用户额度。
    assert len(admitted) <= 6
    assert len(admitted) + len(rejected_codes) == 10

    config = read_config_row()
    assert int(config["enabled"]) == 1
    assert int(config["user_daily_limit"]) in {5, 6}
    assert int(config["global_daily_limit"]) == 80

    # 并发不被突破：用户并发 1、全站并发 2。
    with engine.connect() as conn:
        assert int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM ai_requests "
                    "WHERE status = 'RUNNING' "
                    "AND leased_until > UTC_TIMESTAMP(6)"
                )
            ).scalar_one()
        ) == 0

    holder_a = factory.make_user("hold_a")
    holder_b = factory.make_user("hold_b")
    extra = factory.make_user("hold_c")

    first = admit(holder_a["id"])
    busy = admit_error(holder_a["id"])
    assert busy.detail["code"] == "AI_USER_BUSY"

    second = admit(holder_b["id"])
    global_busy = admit_error(extra["id"])
    assert global_busy.detail["code"] == "AI_GLOBAL_BUSY"

    settle(first.request_id, "SUCCESS")
    settle(second.request_id, "SUCCESS")


# ============================================================
# 8. 额度边界
# ============================================================


def test_yesterday_requests_not_counted_today(factory):
    admin = factory.make_admin()
    user = factory.make_user("day")

    factory.make_ai_request(
        user["id"],
        status="SUCCESS",
        request_date=today() - timedelta(days=1),
    )

    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 1, "reason": "A4 跨日额度"},
    )
    assert response.status_code == 200, response.text

    admit_and_settle(user["id"])
    assert ai_request_count(user["id"]) == 1

    # 今天再请求一次即达到 1 次额度。
    assert admit_error(user["id"]).detail["code"] == "AI_USER_DAILY_LIMIT"


def test_practice_generate_requires_two_remaining_quota(factory):
    admin = factory.make_admin()
    user = factory.make_user("prac")
    other = factory.make_user("prac_other")

    # 用户剩余额度不足 2。
    response = patch_config(
        factory.client,
        admin["token"],
        {"user_daily_limit": 5, "reason": "A4 用户练习额度"},
    )
    assert response.status_code == 200, response.text
    for _ in range(4):
        factory.make_ai_request(user["id"])

    exc = admit_error(user["id"], "PRACTICE_GENERATE")
    assert exc.status_code == 429
    assert exc.detail["code"] == "AI_PRACTICE_QUOTA_INSUFFICIENT"

    # 全站剩余额度不足 2。
    response = patch_config(
        factory.client,
        admin["token"],
        {
            "user_daily_limit": 5,
            "global_daily_limit": 5,
            "reason": "A4 全站练习额度",
        },
    )
    assert response.status_code == 200, response.text
    for _ in range(4):
        factory.make_ai_request(other["id"])

    fresh = factory.make_user("prac_fresh")
    exc = admit_error(fresh["id"], "PRACTICE_GENERATE")
    assert exc.status_code == 429
    assert (
        exc.detail["code"] == "AI_PRACTICE_GLOBAL_QUOTA_INSUFFICIENT"
    )


def test_failed_and_cancelled_streams_still_consume_quota(factory):
    user = factory.make_user("settle")

    # 1) 流内 error 事件 -> ERROR，仍占用额度。
    admission = admit(user["id"])
    frames = collect_frames(
        ai_guard_service.metered_ai_stream(
            admission,
            _error_stream(),
        )
    )
    assert frames[-1].startswith("event: error")
    assert ai_request_status(admission.request_id) == "ERROR"
    assert ai_request_count(user["id"]) == 1

    # 2) 客户端取消 -> CANCELLED，仍占用额度。
    cancelled = admit(user["id"])
    _cancel_stream(cancelled)

    deadline = time.time() + 5
    while time.time() < deadline:
        if ai_request_status(cancelled.request_id) == "CANCELLED":
            break
        time.sleep(0.05)

    assert ai_request_status(cancelled.request_id) == "CANCELLED"
    assert ai_request_count(user["id"]) == 2

    # 额度按已占用的 2 次结算。
    write_config(
        enabled=1,
        user_daily_limit=2,
        global_daily_limit=80,
    )
    exc = admit_error(user["id"])
    assert exc.detail["code"] == "AI_USER_DAILY_LIMIT"


async def _error_stream():
    yield sse_frame("start", {"mode": "summary"})
    yield sse_frame(
        "error",
        {"code": "MODEL_TIMEOUT", "message": "AI 生成超时"},
    )


def _cancel_stream(admission) -> None:
    state = {"closed": False}

    async def slow_stream():
        try:
            yield sse_frame("start", {"mode": "summary"})
            yield sse_frame("delta", {"text": "part"})
            await asyncio.sleep(30)
        finally:
            state["closed"] = True

    async def run_and_cancel():
        async def consume():
            async for _ in ai_guard_service.metered_ai_stream(
                admission, slow_stream()
            ):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.2)

    asyncio.run(run_and_cancel())
    assert state["closed"] is True


# ============================================================
# 9. 配置缺失 / 旧事务
# ============================================================


def test_missing_config_returns_503(factory, monkeypatch):
    user = factory.make_user("nocfg")

    monkeypatch.setattr(
        ai_config_repository,
        "find_config",
        lambda db: None,
    )

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "AI_CONFIG_UNAVAILABLE"


def test_dirty_session_rejected(factory):
    user = factory.make_user("dirty")

    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        assert db.in_transaction() is True

        with pytest.raises(RuntimeError) as exc_info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    assert str(exc_info.value) == "AI admission requires a clean Session"


# ============================================================
# 10. 不依赖 AI 的能力
# ============================================================


def test_objective_submission_does_not_call_ai(factory, monkeypatch):
    model = ModelMock()
    model.install(monkeypatch)

    user = factory.make_user_with_token("obj")
    note_id = factory.make_note(user["id"])

    paper = build_paper(
        user["id"],
        note_id=note_id,
        short_answers=False,
    )
    ticket = make_ticket(paper)

    response = factory.client.post(
        "/ai/practices/submit",
        json={
            "practice_ticket": ticket,
            "answers": default_answers(paper),
        },
        headers=auth_headers(user["token"]),
    )

    assert response.status_code == 200, response.text
    events = sse_events(response)
    assert events[-1][0] == "done"
    assert events[-1][1]["already_saved"] is False
    assert model.calls == []
    assert ai_request_count(user["id"]) == 0

    with engine.connect() as conn:
        saved = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM practice_records "
                    "WHERE user_id = :u AND generation_id = :g"
                ),
                {"u": user["id"], "g": paper["generation_id"]},
            ).scalar_one()
        )
    assert saved == 1


def test_duplicate_submission_returns_saved_result(factory, monkeypatch):
    model = ModelMock()
    model.install(monkeypatch)

    user = factory.make_user_with_token("dup")
    note_id = factory.make_note(user["id"])
    paper = build_paper(
        user["id"],
        note_id=note_id,
        short_answers=False,
    )
    ticket = make_ticket(paper)
    payload = {
        "practice_ticket": ticket,
        "answers": default_answers(paper),
    }

    first = factory.client.post(
        "/ai/practices/submit",
        json=payload,
        headers=auth_headers(user["token"]),
    )
    assert first.status_code == 200, first.text

    second = factory.client.post(
        "/ai/practices/submit",
        json=payload,
        headers=auth_headers(user["token"]),
    )
    assert second.status_code == 200, second.text

    events = sse_events(second)
    assert events[-1][0] == "done"
    assert events[-1][1]["already_saved"] is True

    with engine.connect() as conn:
        saved = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM practice_records "
                    "WHERE user_id = :u AND generation_id = :g"
                ),
                {"u": user["id"], "g": paper["generation_id"]},
            ).scalar_one()
        )
    assert saved == 1
    assert model.calls == []
    assert ai_request_count(user["id"]) == 0


def test_practice_history_works_when_ai_disabled(factory, monkeypatch):
    user = factory.make_user_with_token("hist")

    record_one = factory.make_practice_record(user["id"])
    record_two = factory.make_practice_record(user["id"])

    write_config(enabled=0)

    listing = factory.client.get(
        "/ai/practices", headers=auth_headers(user["token"])
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"]["total"] >= 2

    detail = factory.client.get(
        f"/ai/practices/{record_one}",
        headers=auth_headers(user["token"]),
    )
    assert detail.status_code == 200, detail.text

    deleted = factory.client.delete(
        f"/ai/practices/{record_one}",
        headers=auth_headers(user["token"]),
    )
    assert deleted.status_code == 200, deleted.text

    # Redis 不可用时历史读取与删除仍正常。
    write_config(enabled=1)

    def boom(*args, **kwargs):
        raise RedisError("redis down")

    # A4.2 使用 register_script 注册的滑动窗口脚本，替换脚本入口模拟 Redis 不可用。
    monkeypatch.setattr(
        ai_rate_limit_service,
        "sliding_window_script",
        boom,
    )

    listing = factory.client.get(
        "/ai/practices", headers=auth_headers(user["token"])
    )
    assert listing.status_code == 200, listing.text

    deleted = factory.client.delete(
        f"/ai/practices/{record_two}",
        headers=auth_headers(user["token"]),
    )
    assert deleted.status_code == 200, deleted.text


# ============================================================
# 11. AI 统计一致性
# ============================================================


def test_statistics_config_contract(factory):
    admin = factory.make_admin()

    response = factory.client.get(
        "/admin/ai/statistics",
        headers=auth_headers(admin["token"]),
    )
    assert response.status_code == 200, response.text

    config = response.json()["data"]["config"]
    # 契约（A3 已确立）：统计接口展示运行时配置与实际生效开关。
    for key in (
        "enabled",
        "configured_enabled",
        "user_daily_limit",
        "global_daily_limit",
        "user_concurrency",
        "global_concurrency",
        "model_configured",
    ):
        assert key in config, key

    # 关闭 AI 后 enabled（生效开关）必须为 false，configured_enabled 同步。
    admin_patch = patch_config(
        factory.client,
        admin["token"],
        {"enabled": False, "reason": "A4 统计关闭验证"},
    )
    assert admin_patch.status_code == 200, admin_patch.text

    response = factory.client.get(
        "/admin/ai/statistics",
        headers=auth_headers(admin["token"]),
    )
    assert response.status_code == 200, response.text
    config = response.json()["data"]["config"]
    assert config["enabled"] is False
    assert config["configured_enabled"] is False


def test_statistics_effective_values_match_guard(factory):
    admin = factory.make_admin()
    row = read_config_row()

    expected_user = min(
        int(row["user_daily_limit"]),
        settings.AI_USER_DAILY_HARD_LIMIT,
    )
    expected_global = min(
        int(row["global_daily_limit"]),
        settings.AI_GLOBAL_DAILY_HARD_LIMIT,
    )

    response = factory.client.get(
        "/admin/ai/statistics",
        headers=auth_headers(admin["token"]),
    )
    assert response.status_code == 200, response.text
    config = response.json()["data"]["config"]

    assert config["user_daily_limit"] == expected_user
    assert config["global_daily_limit"] == expected_global
    assert config["enabled"] is True

    # 与 Guard 实际读取值一致。
    with SessionLocal() as db:
        runtime = ai_runtime_service.read_config(db)

    guard_user, guard_global = ai_runtime_service.effective_limits(runtime)
    assert config["user_daily_limit"] == guard_user
    assert config["global_daily_limit"] == guard_global