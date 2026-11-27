"""V3.0 A4.2 精确滑动窗口限流验收测试。

约束：
- 仅在隔离库 ssp_v3_admin_test 执行；不修改业务源码。
- 真实 Memurai；AI Provider 使用 Mock。
- 仅操作 ssp:ssp_v3_admin_test: 前缀 key，不执行 FLUSHALL/FLUSHDB。
- 时间相关用例使用短窗口或预置 ZSET 分数，避免长时间等待。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_a4_2_sliding_window_acceptance.py -q
"""

import threading
import time
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import text

from app.config import settings
from app.core import security
from app.core.clock import utc_db_now
from app.core.redis_client import redis_client
from app.database import SessionLocal, engine
from app.main import app as production_app
from app.repositories.knowledge import ai_guard_repository
from app.services.knowledge import (
    ai_guard_service,
    ai_rate_limit_service,
)


ALLOWED_TEST_DBS = {"ssp_v3_admin_test"}
PREFIX = f"a42{uuid.uuid4().hex[:8]}"
PASSWORD = "AdminPass123"
ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}

BASELINE_CONFIG = {
    "enabled": 1,
    "user_daily_limit": 10,
    "global_daily_limit": 80,
}


def _guard_database() -> str:
    with engine.connect() as conn:
        name = conn.execute(text("SELECT DATABASE()")).scalar_one()

    if name not in ALLOWED_TEST_DBS:
        raise RuntimeError(
            f"测试仅允许在隔离测试库执行，当前数据库: {name}"
        )

    return name


DB_NAME_NOW = _guard_database()


def v2_key(user_id: int, db_name: str | None = None) -> str:
    return f"ssp:{db_name or DB_NAME_NOW}:ai:rate:v2:{user_id}"


def legacy_key(user_id: int) -> str:
    return f"ssp:{DB_NAME_NOW}:ai:rate:{user_id}"


def redis_now_ms() -> int:
    seconds, micros = redis_client.time()
    return int(seconds) * 1000 + int(micros) // 1000


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


def ai_request_count(user_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM ai_requests WHERE user_id = :u"
                ),
                {"u": user_id},
            ).scalar_one()
        )


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


# ============================================================
# 夹具
# ============================================================


@pytest.fixture(scope="session", autouse=True)
def _raise_auth_ip_limits():
    old_pwd = settings.PASSWORD_IP_MAX_ATTEMPTS
    old_mail = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
    settings.PASSWORD_IP_MAX_ATTEMPTS = 10 ** 9
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 10 ** 9
    yield
    settings.PASSWORD_IP_MAX_ATTEMPTS = old_pwd
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = old_mail


@pytest.fixture(autouse=True)
def _baseline():
    write_config(**BASELINE_CONFIG)
    old_key = settings.DEEPSEEK_API_KEY
    if not old_key:
        settings.DEEPSEEK_API_KEY = "a42-test-key"

    yield

    write_config(**BASELINE_CONFIG)
    settings.DEEPSEEK_API_KEY = old_key


@pytest.fixture()
def rate_uid():
    """Redis 限流专用用户 ID；不创建数据库用户。"""

    user_id = 10 ** 9 + uuid.uuid4().int % 10 ** 8
    yield user_id
    redis_client.delete(v2_key(user_id))
    redis_client.delete(legacy_key(user_id))


@pytest.fixture()
def set_rate(monkeypatch):
    def _set(limit: int = 6, window: int = 10) -> None:
        monkeypatch.setattr(settings, "AI_USER_RATE_LIMIT", limit)
        monkeypatch.setattr(settings, "AI_RATE_WINDOW_SECONDS", window)

    return _set


@pytest.fixture()
def factory():
    client = TestClient(
        production_app,
        base_url="https://ssp.test",
        client=("127.0.0.1", 52410),
        raise_server_exceptions=False,
    )
    user_ids: list[int] = []

    def make_user(*, with_token: bool = False) -> dict:
        username = f"{PREFIX}{uuid.uuid4().hex[:8]}"

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users ("
                    "username, password_hash, password_updated_at, "
                    "email, email_verified_at, nickname, role, created_at"
                    ") VALUES ("
                    ":username, :password_hash, :now, :email, :now, "
                    ":nickname, 'USER', CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "username": username,
                    "password_hash": security.hash_password(PASSWORD),
                    "now": utc_db_now(),
                    "email": f"{username}@example.com",
                    "nickname": username,
                },
            )
            user_id = int(result.lastrowid)

        user_ids.append(user_id)
        token = None

        if with_token:
            response = client.post(
                "/auth/login",
                data={
                    "username": username,
                    "password": PASSWORD,
                },
                headers=CSRF_HEADERS,
            )
            assert response.status_code == 200, response.text
            token = response.json()["data"]["access_token"]

        return {
            "id": user_id,
            "username": username,
            "token": token,
        }

    yield client, make_user

    with engine.begin() as conn:
        for user_id in user_ids:
            for table in (
                "refresh_tokens",
                "login_sessions",
                "auth_events",
                "email_verifications",
            ):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE user_id = :i"),
                    {"i": user_id},
                )
            conn.execute(
                text("DELETE FROM ai_requests WHERE user_id = :i"),
                {"i": user_id},
            )
            conn.execute(
                text("DELETE FROM users WHERE id = :i"),
                {"i": user_id},
            )


# ============================================================
# 工具
# ============================================================


def check(user_id: int) -> None:
    ai_rate_limit_service.check_ai_rate_limit(user_id)


def limit_error(user_id: int) -> HTTPException:
    with pytest.raises(HTTPException) as info:
        check(user_id)
    return info.value


def run_script(
    user_id: int,
    *,
    limit: int,
    window_ms: int,
    request_id: str,
) -> list:
    return ai_rate_limit_service.sliding_window_script(
        keys=[v2_key(user_id)],
        args=[limit, window_ms, request_id],
    )


# ============================================================
# 1. 前 6 次通过，第 7 次 429
# ============================================================


def test_six_allowed_seventh_rejected(set_rate, rate_uid):
    set_rate(6, 10)

    for _ in range(6):
        check(rate_uid)

    assert redis_client.zcard(v2_key(rate_uid)) == 6

    exc = limit_error(rate_uid)

    assert exc.status_code == 429
    assert exc.detail["code"] == "AI_RATE_LIMIT"
    assert exc.headers["Retry-After"] == str(exc.detail["retry_after"])

    # 超限请求不写入 ZSET。
    assert redis_client.zcard(v2_key(rate_uid)) == 6


# ============================================================
# 2. 窗口边界无双倍突发
# ============================================================


def test_no_double_burst_at_window_boundary(set_rate, rate_uid):
    window = 3
    set_rate(6, window)

    for _ in range(6):
        check(rate_uid)

    # 固定窗口在此刻已重置并允许新一批；滑动窗口仍拒绝。
    time.sleep(window - 0.4)

    assert limit_error(rate_uid).detail["code"] == "AI_RATE_LIMIT"
    assert redis_client.zcard(v2_key(rate_uid)) == 6

    # 等超过完整窗口后一次性请求才被允许。
    time.sleep(0.8)
    check(rate_uid)
    assert redis_client.zcard(v2_key(rate_uid)) == 1


# ============================================================
# 3. 名额逐条释放
# ============================================================


def test_slots_release_gradually(set_rate, rate_uid):
    window = 4
    set_rate(6, window)

    check(rate_uid)  # t0

    time.sleep(1.0)
    for _ in range(5):
        check(rate_uid)  # t1 = t0 + 1s

    assert redis_client.zcard(v2_key(rate_uid)) == 6

    # t0 已离开窗口，t1 的 5 条仍在窗口内。
    time.sleep(window - 1.0 + 0.4)
    check(rate_uid)
    assert redis_client.zcard(v2_key(rate_uid)) == 6

    # 仅释放了 1 个名额，紧接着再次请求必须被拒绝。
    assert limit_error(rate_uid).detail["code"] == "AI_RATE_LIMIT"
    assert redis_client.zcard(v2_key(rate_uid)) == 6


# ============================================================
# 4. 同毫秒 / 同 Score 不互相覆盖
# ============================================================


def test_same_millisecond_requests_all_recorded(set_rate, rate_uid):
    set_rate(1000, 30)

    for index in range(200):
        result = run_script(
            rate_uid,
            limit=1000,
            window_ms=30000,
            request_id=f"ms-{index}",
        )
        assert int(result[0]) == 1

    rows = redis_client.zrange(
        v2_key(rate_uid),
        0,
        -1,
        withscores=True,
    )

    assert len(rows) == 200
    assert len({member for member, _ in rows}) == 200


def test_equal_scores_do_not_overwrite(set_rate, rate_uid):
    set_rate(1000, 30)
    key = v2_key(rate_uid)

    score = redis_now_ms()
    redis_client.zadd(key, {"same-a": score, "same-b": score})
    redis_client.pexpire(key, 30000)

    assert redis_client.zcard(key) == 2

    result = run_script(
        rate_uid,
        limit=1000,
        window_ms=30000,
        request_id="same-c",
    )
    assert int(result[0]) == 1
    assert redis_client.zcard(key) == 3


# ============================================================
# 5. 8 线程并发精确限制
# ============================================================


def test_concurrent_threads_exact(set_rate, rate_uid):
    set_rate(6, 10)
    barrier = threading.Barrier(8)
    results: list[str] = []

    def worker() -> None:
        barrier.wait()
        try:
            check(rate_uid)
        except HTTPException as exc:
            results.append(exc.detail.get("code"))
        else:
            results.append("ok")

    threads = [
        threading.Thread(target=worker)
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "滑动窗口并发测试疑似死锁"

    assert results.count("ok") == 6
    assert results.count("AI_RATE_LIMIT") == 2
    assert redis_client.zcard(v2_key(rate_uid)) == 6


# ============================================================
# 6. 同一 request_id 重复执行不重复计数
# ============================================================


def test_same_request_id_not_double_counted(set_rate, rate_uid):
    set_rate(6, 10)

    assert int(
        run_script(
            rate_uid,
            limit=6,
            window_ms=10000,
            request_id="fixed-rid",
        )[0]
    ) == 1
    assert int(
        run_script(
            rate_uid,
            limit=6,
            window_ms=10000,
            request_id="fixed-rid",
        )[0]
    ) == 1

    assert redis_client.zcard(v2_key(rate_uid)) == 1

    assert int(
        run_script(
            rate_uid,
            limit=6,
            window_ms=10000,
            request_id="other-rid",
        )[0]
    ) == 1
    assert redis_client.zcard(v2_key(rate_uid)) == 2


# ============================================================
# 7. 用户与数据库命名空间隔离
# ============================================================


def test_user_and_namespace_isolation(set_rate, rate_uid, monkeypatch):
    set_rate(6, 10)
    other_uid = rate_uid + 1
    other_default_key = v2_key(other_uid)

    try:
        for _ in range(6):
            check(rate_uid)
        assert limit_error(rate_uid).detail["code"] == "AI_RATE_LIMIT"

        # 不同用户互不影响。
        check(other_uid)
        assert redis_client.zcard(other_default_key) == 1

        # 不同数据库命名空间互不影响。
        namespace = f"ssp_v3_admin_test:ns{uuid.uuid4().hex[:6]}"
        monkeypatch.setattr(settings, "DB_NAME", namespace)

        check(other_uid)
        assert redis_client.zcard(v2_key(other_uid)) == 1

        for key in list(redis_client.scan_iter(f"ssp:{namespace}:*")):
            redis_client.delete(key)

    finally:
        redis_client.delete(other_default_key)


# ============================================================
# 8. 超限不新增成员、不延长 TTL
# ============================================================


def test_rejection_does_not_add_member_or_extend_ttl(
    set_rate, rate_uid
):
    set_rate(3, 5)

    for _ in range(3):
        check(rate_uid)

    key = v2_key(rate_uid)
    ttl_before = redis_client.pttl(key)
    assert ttl_before > 0

    time.sleep(0.3)

    assert limit_error(rate_uid).detail["code"] == "AI_RATE_LIMIT"

    ttl_after = redis_client.pttl(key)

    assert redis_client.zcard(key) == 3
    assert 0 < ttl_after < ttl_before


# ============================================================
# 9. 长期无请求后 Key 自动过期
# ============================================================


def test_key_expires_after_idle(set_rate, rate_uid):
    set_rate(6, 1)

    check(rate_uid)

    key = v2_key(rate_uid)
    assert 0 < redis_client.pttl(key) <= 1000

    time.sleep(1.2)
    assert redis_client.exists(key) == 0


# ============================================================
# 10. Retry-After 向上取整与边界
# ============================================================


def test_retry_after_is_ceiled(set_rate, rate_uid):
    key = v2_key(rate_uid)

    # 预置 1 条 500ms 前的请求，窗口 2s：剩余 1.5s，应向上取整为 2。
    redis_client.zadd(key, {"old": redis_now_ms() - 500})
    redis_client.pexpire(key, 5000)

    set_rate(1, 2)

    exc = limit_error(rate_uid)

    assert exc.detail["retry_after"] == 2
    assert exc.headers["Retry-After"] == "2"


def test_request_at_window_boundary_is_expired(set_rate, rate_uid):
    key = v2_key(rate_uid)

    # 恰好位于左边界：score <= cutoff 应被清理。
    redis_client.zadd(key, {"boundary": redis_now_ms() - 1000})
    redis_client.pexpire(key, 5000)

    set_rate(1, 1)
    check(rate_uid)

    assert redis_client.zcard(key) == 1


# ============================================================
# 11. Redis 不可用
# ============================================================


def test_redis_unavailable_503_learning_still_works(
    factory, monkeypatch
):
    client, make_user = factory
    user = make_user(with_token=True)

    def boom(*args, **kwargs):
        raise RedisError("redis down")

    monkeypatch.setattr(
        ai_rate_limit_service,
        "sliding_window_script",
        boom,
    )

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    assert info.value.status_code == 503
    assert (
        info.value.detail["code"] == "AI_RATE_LIMIT_UNAVAILABLE"
    )

    response = client.get(
        "/notes",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert response.status_code == 200, response.text


# ============================================================
# 12. 脚本缓存 / 重新加载
# ============================================================


def test_registered_script_loads_without_flushing_cache(
    set_rate, rate_uid
):
    set_rate(6, 10)
    check(rate_uid)

    sha = ai_rate_limit_service.sliding_window_script.sha
    assert redis_client.script_exists(sha) == [True]

    fresh = redis_client.register_script(
        ai_rate_limit_service.SLIDING_WINDOW_SCRIPT
    )
    result = fresh(
        keys=[v2_key(rate_uid)],
        args=[6, 10000, "reload-rid"],
    )

    assert int(result[0]) == 1
    # 未清空共享实例脚本缓存。
    assert redis_client.script_exists(sha) == [True]


# ============================================================
# 13. 降低阈值后的等待时间
# ============================================================


def test_lower_threshold_wait_time(
    set_rate, rate_uid, monkeypatch
):
    window = 4
    set_rate(6, window)

    check(rate_uid)
    time.sleep(0.5)
    check(rate_uid)
    time.sleep(0.5)
    check(rate_uid)

    key = v2_key(rate_uid)
    scores = sorted(
        float(score)
        for _, score in redis_client.zrange(
            key,
            0,
            -1,
            withscores=True,
        )
    )
    assert len(scores) == 3

    # 阈值降为 2 后，需要等到第 2 条请求离开窗口。
    monkeypatch.setattr(settings, "AI_USER_RATE_LIMIT", 2)

    exc = limit_error(rate_uid)
    now = redis_now_ms()
    expected_ms = max(
        1,
        int(scores[1]) + window * 1000 - now,
    )
    expected = (expected_ms + 999) // 1000

    assert abs(exc.detail["retry_after"] - expected) <= 1
    assert exc.headers["Retry-After"] == str(
        exc.detail["retry_after"]
    )


# ============================================================
# 14. 旧固定窗口 String Key 不冲突
# ============================================================


def test_legacy_string_key_no_wrongtype(set_rate, rate_uid):
    set_rate(6, 10)

    old = legacy_key(rate_uid)
    redis_client.set(old, 6, ex=60)

    check(rate_uid)

    assert redis_client.type(old) in ("string", b"string")
    assert redis_client.get(old) == "6"
    assert redis_client.zcard(v2_key(rate_uid)) == 1

    redis_client.delete(old)


# ============================================================
# 15. 六个 AI 入口共享限流状态
# ============================================================


def test_six_ai_entries_share_rate_limit(factory, set_rate):
    client, make_user = factory
    user = make_user()
    set_rate(6, 10)

    operations = [
        "GENERATE",
        "ORGANIZE",
        "SUMMARY",
        "ASK",
        "PRACTICE_GENERATE",
        "PRACTICE_GRADE",
    ]

    for operation in operations:
        with SessionLocal() as db:
            admission = ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation=operation,
            )
        settle(admission.request_id)

    assert redis_client.zcard(v2_key(user["id"])) == 6

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as info:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    assert info.value.detail["code"] == "AI_RATE_LIMIT"
    assert ai_request_count(user["id"]) == 6


# ============================================================
# 16. HTTP 429 响应头与响应体一致
# ============================================================


def test_http_429_retry_after_header_matches_body(
    factory, set_rate
):
    client, make_user = factory
    user = make_user(with_token=True)
    set_rate(6, 60)

    key = v2_key(user["id"])
    now = redis_now_ms()
    redis_client.zadd(
        key,
        {f"prefill-{index}": now for index in range(6)},
    )
    redis_client.pexpire(key, 60000)

    response = client.post(
        "/notes/ai/generate",
        json={"topic": "滑动窗口验收"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )

    assert response.status_code == 429, response.text

    body = response.json()
    retry_after = body["detail"]["retry_after"]
    header_value = response.headers["Retry-After"]

    assert body["detail"]["code"] == "AI_RATE_LIMIT"
    assert header_value == str(retry_after)
    assert retry_after in (59, 60)
    assert ai_request_count(user["id"]) == 0