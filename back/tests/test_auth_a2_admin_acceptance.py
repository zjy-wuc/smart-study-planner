"""V3.0 A2 用户管理与审计验收测试。

约束：
- 仅在隔离测试库 ssp_v3_admin_test 执行。
- 通过生产路由 /admin/* 验收，不新增生产接口。
- 封禁/解封等写操作真实提交，tearDownClass 按测试前缀精确清理。
- 并发用例使用真实 MySQL 多连接（HTTP + 独立 DB 事务）。
- 不输出密钥、Token、密码。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_auth_a2_admin_acceptance.py -q
"""

import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.config import settings
from app.core import security
from app.core.clock import business_today, utc_db_now
from app.database import engine
from app.main import app as production_app
from app.repositories.auth import user_repository

# ============================================================
# 隔离库守卫
# ============================================================

ALLOWED_TEST_DBS = {"ssp_v3_admin_test"}


def _guard_database() -> str:
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if db_name not in ALLOWED_TEST_DBS:
        raise RuntimeError(
            f"测试仅允许在隔离测试库执行，当前数据库: {db_name}"
        )
    return db_name


CURRENT_DB = _guard_database()

ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {
    "Origin": ORIGIN,
    "X-CSRF-Protection": "1",
}
PASSWORD = "AdminPass123"

_port_lock = threading.Lock()
_port_counter = [52310]


def _next_port() -> int:
    with _port_lock:
        _port_counter[0] += 1
        return _port_counter[0]


def _new_client() -> TestClient:
    return TestClient(
        production_app,
        base_url="https://ssp.test",
        client=("127.0.0.1", _next_port()),
        raise_server_exceptions=False,
    )


def _in_clause(sql: str, key: str = "ids"):
    return text(sql).bindparams(bindparam(key, expanding=True))


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ============================================================
# 基类
# ============================================================


class BaseA2Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.PREFIX = f"a2{uuid.uuid4().hex[:8]}"
        cls.START = utc_db_now()
        cls.client = _new_client()
        cls._pwd_limit = settings.PASSWORD_IP_MAX_ATTEMPTS
        cls._mail_limit = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
        settings.PASSWORD_IP_MAX_ATTEMPTS = 1000000
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 1000000

    @classmethod
    def tearDownClass(cls):
        settings.PASSWORD_IP_MAX_ATTEMPTS = cls._pwd_limit
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = cls._mail_limit
        cls._cleanup()

    @classmethod
    def _cleanup(cls):
        with engine.begin() as conn:
            uids = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT id FROM users WHERE username LIKE :p"
                    ),
                    {"p": cls.PREFIX + "%"},
                )
            ]
            if uids:
                params = {"ids": uids}
                conn.execute(
                    _in_clause(
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
                    "knowledge_notes",
                    "study_plans",
                    "ai_requests",
                ):
                    conn.execute(
                        _in_clause(
                            f"DELETE FROM {table} WHERE user_id IN :ids"
                        ),
                        params,
                    )
                conn.execute(
                    _in_clause(
                        "DELETE FROM users WHERE id IN :ids"
                    ),
                    params,
                )

            # 清理本次测试产生的匿名限流事件
            conn.execute(
                text(
                    "DELETE FROM auth_events "
                    "WHERE user_id IS NULL AND ip = '127.0.0.1' "
                    "AND created_at >= :start"
                ),
                {"start": cls.START},
            )

    # ---------- 构造 ----------

    def make_user(self, suffix: str, *, role: str = "USER"):
        username = f"{self.PREFIX}{suffix}{uuid.uuid4().hex[:4]}"
        email = f"{username}@example.com"

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users ("
                    "username, password_hash, password_updated_at, "
                    "email, email_verified_at, nickname, role"
                    ") VALUES ("
                    ":username, :password_hash, :now, "
                    ":email, :now, :nickname, :role"
                    ")"
                ),
                {
                    "username": username,
                    "password_hash": security.hash_password(PASSWORD),
                    "now": utc_db_now(),
                    "email": email,
                    "nickname": username,
                    "role": role,
                },
            )
            user_id = int(result.lastrowid)

        return user_id, username, email

    def make_admin(self, suffix: str = "op"):
        user_id, username, _ = self.make_user(suffix, role="ADMIN")
        token, _ = self.login(username)
        return user_id, username, token

    def login(self, username: str, client: TestClient | None = None):
        client = client or self.client
        response = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        return data["access_token"], data["user"]

    def login_client(self, username: str):
        client = _new_client()
        token, user = self.login(username, client)
        return client, token, user

    def auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def post_admin(
        self,
        token: str,
        path: str,
        payload: dict | None = None,
        *,
        csrf: bool = True,
    ):
        headers = self.auth(token)
        if csrf:
            headers = {**headers, **CSRF_HEADERS}
        return self.client.post(
            path,
            json=payload if payload is not None else {"reason": "A2 验收操作"},
            headers=headers,
        )

    # ---------- DB ----------

    def db_scalar(self, sql: str, **params):
        with engine.connect() as conn:
            return conn.execute(text(sql), params).scalar_one()

    def db_all(self, sql: str, **params):
        with engine.connect() as conn:
            return conn.execute(text(sql), params).mappings().all()

    def db_exec(self, sql: str, **params) -> None:
        with engine.begin() as conn:
            conn.execute(text(sql), params)

    def read_user(self, user_id: int) -> dict:
        with engine.connect() as conn:
            return dict(
                conn.execute(
                    text(
                        "SELECT id, role, is_active FROM users "
                        "WHERE id = :i"
                    ),
                    {"i": user_id},
                ).mappings().one()
            )

    def family_id_of(self, access_token: str) -> str:
        payload = security.decode_access_token(access_token)
        self.assertIsNotNone(payload)
        return payload["family_id"]

    def audit_count(
        self,
        *,
        target_id: int | None = None,
        action: str | None = None,
    ) -> int:
        sql = "SELECT COUNT(*) FROM admin_audit_logs WHERE 1=1"
        params: dict = {}
        if target_id is not None:
            sql += " AND target_id = :t"
            params["t"] = target_id
        if action is not None:
            sql += " AND action = :a"
            params["a"] = action
        return int(self.db_scalar(sql, **params))

    def session_state(self, user_id: int):
        with engine.connect() as conn:
            return dict(
                conn.execute(
                    text(
                        "SELECT "
                        "COUNT(*) AS total, "
                        "COALESCE(SUM(revoked_at IS NULL), 0) "
                        "AS active "
                        "FROM login_sessions WHERE user_id = :i"
                    ),
                    {"i": user_id},
                ).mappings().one()
            )

    def token_state(self, user_id: int):
        with engine.connect() as conn:
            return dict(
                conn.execute(
                    text(
                        "SELECT "
                        "COUNT(*) AS total, "
                        "COALESCE(SUM(revoked_at IS NULL), 0) "
                        "AS active "
                        "FROM refresh_tokens WHERE user_id = :i"
                    ),
                    {"i": user_id},
                ).mappings().one()
            )

    def seed_learning_data(self, user_id: int) -> None:
        now = utc_db_now()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO study_plans "
                    "(user_id, name, start_date, end_date, status) "
                    "VALUES (:u, 'A2 验收计划', CURDATE(), "
                    "DATE_ADD(CURDATE(), INTERVAL 7 DAY), 'ACTIVE')"
                ),
                {"u": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO study_plans "
                    "(user_id, name, start_date, end_date, status) "
                    "VALUES (:u, 'A2 已结束计划', CURDATE(), "
                    "DATE_ADD(CURDATE(), INTERVAL 7 DAY), 'ENDED')"
                ),
                {"u": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO knowledge_notes "
                    "(user_id, title, content_md) "
                    "VALUES (:u, 'A2 笔记', '内容')"
                ),
                {"u": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO knowledge_notes "
                    "(user_id, title, content_md, deleted_at) "
                    "VALUES (:u, 'A2 已删笔记', '内容', :now)"
                ),
                {"u": user_id, "now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO ai_requests "
                    "(request_id, user_id, operation, request_date, "
                    "status, leased_until) "
                    "VALUES (:rid, :u, 'TEST', :d, 'SUCCESS', :now)"
                ),
                {
                    "rid": str(uuid.uuid4()),
                    "u": user_id,
                    "d": business_today(),
                    "now": now,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO ai_requests "
                    "(request_id, user_id, operation, request_date, "
                    "status, leased_until) "
                    "VALUES (:rid, :u, 'TEST', :d, 'SUCCESS', :now)"
                ),
                {
                    "rid": str(uuid.uuid4()),
                    "u": user_id,
                    "d": business_today() - timedelta(days=1),
                    "now": now,
                },
            )

    def learning_counts(self, user_id: int) -> dict:
        with engine.connect() as conn:
            return dict(
                conn.execute(
                    text(
                        "SELECT "
                        "(SELECT COUNT(*) FROM study_plans "
                        " WHERE user_id = :i) AS plans, "
                        "(SELECT COUNT(*) FROM knowledge_notes "
                        " WHERE user_id = :i) AS notes"
                    ),
                    {"i": user_id},
                ).mappings().one()
            )

    # ---------- 线程 ----------

    def run_threads(self, targets) -> None:
        threads = [threading.Thread(target=t) for t in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=40)
        for thread in threads:
            self.assertFalse(thread.is_alive(), "并发线程未在超时内结束")


# ============================================================
# T1 权限与 CSRF
# ============================================================


class TestAdminPermissions(BaseA2Test):

    def setUp(self):
        self.admin_id, _, self.admin_token = self.make_admin("op")
        self.user_id, self.user_name, _ = self.make_user("usr")
        self.user_token, _ = self.login(self.user_name)

    def _endpoints(self):
        return [
            ("get", "/admin/users", None),
            ("get", f"/admin/users/{self.user_id}", None),
            ("post", f"/admin/users/{self.user_id}/ban", {"reason": "x"}),
            ("post", f"/admin/users/{self.user_id}/unban", {"reason": "x"}),
            (
                "post",
                f"/admin/users/{self.user_id}/revoke-sessions",
                {"reason": "x"},
            ),
            ("get", "/admin/audit-logs", None),
        ]

    def test_t1_01_normal_user_rejected_on_all_endpoints(self):
        """全部管理员接口拒绝普通用户（403 ADMIN_REQUIRED）"""
        for method, path, body in self._endpoints():
            with self.subTest(path=path):
                if method == "get":
                    response = self.client.get(
                        path, headers=self.auth(self.user_token)
                    )
                else:
                    response = self.client.post(
                        path,
                        json=body,
                        headers={
                            **self.auth(self.user_token),
                            **CSRF_HEADERS,
                        },
                    )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "ADMIN_REQUIRED",
                )

    def test_t1_02_anonymous_rejected_on_all_endpoints(self):
        """未登录访问管理员接口返回 401"""
        for method, path, body in self._endpoints():
            with self.subTest(path=path):
                if method == "get":
                    response = self.client.get(path)
                else:
                    response = self.client.post(
                        path, json=body, headers=CSRF_HEADERS
                    )
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "INVALID_TOKEN",
                )

    def test_t1_03_admin_allowed(self):
        """管理员可访问全部接口"""
        response = self.client.get(
            "/admin/users", headers=self.auth(self.admin_token)
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("items", response.json()["data"])

        response = self.client.get(
            "/admin/audit-logs", headers=self.auth(self.admin_token)
        )
        self.assertEqual(response.status_code, 200, response.text)

        response = self.post_admin(
            self.admin_token,
            f"/admin/users/{self.user_id}/ban",
            {"reason": "管理员可用性校验"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_t1_04_write_endpoints_require_csrf(self):
        """敏感写接口必须校验 CSRF"""
        writes = [
            f"/admin/users/{self.user_id}/ban",
            f"/admin/users/{self.user_id}/unban",
            f"/admin/users/{self.user_id}/revoke-sessions",
        ]
        for path in writes:
            with self.subTest(path=path, case="missing"):
                response = self.client.post(
                    path,
                    json={"reason": "x"},
                    headers=self.auth(self.admin_token),
                )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "CSRF_REJECTED",
                )

            with self.subTest(path=path, case="bad-origin"):
                response = self.client.post(
                    path,
                    json={"reason": "x"},
                    headers={
                        **self.auth(self.admin_token),
                        "Origin": "http://evil.example",
                        "X-CSRF-Protection": "1",
                    },
                )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "CSRF_REJECTED",
                )

    def test_t1_05_admin_target_forbidden(self):
        """禁止封禁、解封、下线任何 ADMIN（含自身）"""
        other_id, _, other_token = self.make_admin("op2")

        for target_id in (other_id, self.admin_id):
            for action in ("ban", "unban", "revoke-sessions"):
                with self.subTest(target=target_id, action=action):
                    response = self.post_admin(
                        self.admin_token,
                        f"/admin/users/{target_id}/{action}",
                        {"reason": "尝试操作管理员"},
                    )
                    self.assertEqual(
                        response.status_code, 403, response.text
                    )
                    self.assertEqual(
                        response.json()["detail"]["code"],
                        "ADMIN_TARGET_FORBIDDEN",
                    )

        # 被操作的管理员仍保持 ADMIN 且可访问
        self.assertEqual(self.read_user(other_id)["role"], "ADMIN")
        response = self.client.get(
            "/admin/users", headers=self.auth(other_token)
        )
        self.assertEqual(response.status_code, 200, response.text)


# ============================================================
# T2 查询
# ============================================================


class TestAdminUserQuery(BaseA2Test):

    def setUp(self):
        # 每个用例使用独立标记，避免同类前序用例数据干扰统计
        self.tag = uuid.uuid4().hex[:6]
        self.admin_id, _, self.admin_token = self.make_admin(
            f"op{self.tag}"
        )
        self.u1, self.u1_name, self.u1_email = self.make_user(
            f"alpha{self.tag}"
        )
        self.u2, self.u2_name, self.u2_email = self.make_user(
            f"beta{self.tag}"
        )
        self.u3, self.u3_name, _ = self.make_user(f"gamma{self.tag}")
        self.db_exec(
            "UPDATE users SET is_active = 0 WHERE id = :i",
            i=self.u2,
        )

    def _list(self, **params):
        params.setdefault("keyword", self.tag)
        response = self.client.get(
            "/admin/users",
            params=params,
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_t2_01_pagination(self):
        """分页返回稳定且不重复"""
        page1 = self._list(page=1, page_size=2)
        page2 = self._list(page=2, page_size=2)
        page3 = self._list(page=3, page_size=2)

        total = page1["total"]
        self.assertGreaterEqual(total, 4)
        self.assertEqual(len(page1["items"]), min(2, total))

        seen = []
        for page in (page1, page2, page3):
            seen.extend(item["id"] for item in page["items"])
        self.assertEqual(len(seen), total)
        self.assertEqual(len(set(seen)), total)
        self.assertEqual(page1["page"], 1)
        self.assertEqual(page1["page_size"], 2)

    def test_t2_02_username_fuzzy_search(self):
        """用户名模糊搜索（含大小写不敏感）"""
        keyword = f"alpha{self.tag}"
        data = self._list(keyword=keyword)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], self.u1)

        upper = self._list(keyword=keyword.upper())
        self.assertGreaterEqual(upper["total"], 1)
        self.assertIn(self.u1, [item["id"] for item in upper["items"]])

    def test_t2_03_email_exact_search(self):
        """邮箱精确搜索，部分邮箱不命中"""
        data = self._list(keyword=self.u1_email)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], self.u1)

        partial = self.u1_email[:-4]
        data = self._list(keyword=partial)
        self.assertEqual(data["total"], 0)

    def test_t2_04_status_filter(self):
        """状态筛选"""
        disabled = self._list(status="DISABLED")
        self.assertGreaterEqual(disabled["total"], 1)
        self.assertTrue(
            all(item["is_active"] is False for item in disabled["items"])
        )
        self.assertIn(self.u2, [item["id"] for item in disabled["items"]])

        active = self._list(status="ACTIVE")
        self.assertTrue(
            all(item["is_active"] is True for item in active["items"])
        )
        ids = [item["id"] for item in active["items"]]
        self.assertIn(self.u1, ids)
        self.assertIn(self.u3, ids)
        self.assertNotIn(self.u2, ids)

    def test_t2_05_email_masked_in_list(self):
        """列表邮箱脱敏"""
        data = self._list(keyword=f"alpha{self.tag}")
        item = data["items"][0]
        masked = f"{self.u1_name[0]}***@example.com"
        self.assertEqual(item["email"], masked)

    def test_t2_06_no_sensitive_fields(self):
        """列表/详情不泄漏敏感字段"""
        data = self._list(keyword=f"alpha{self.tag}")
        item = data["items"][0]
        forbidden = {
            "password_hash",
            "password_updated_at",
            "token_hash",
        }
        self.assertFalse(forbidden & set(item))

        detail = self.client.get(
            f"/admin/users/{self.u1}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        payload = detail.json()["data"]
        self.assertFalse(forbidden & set(payload))
        self.assertEqual(payload["email"], self.u1_email)
        self.assertEqual(payload["id"], self.u1)

    def test_t2_07_detail_statistics_accurate(self):
        """详情统计准确（有效计划/未删笔记/今日 AI/活跃会话）"""
        user_id, user_name, _ = self.make_user("stats")
        self.login(user_name)
        self.seed_learning_data(user_id)

        response = self.client.get(
            f"/admin/users/{user_id}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        statistics = response.json()["data"]["statistics"]

        self.assertEqual(statistics["active_plan_count"], 1)
        self.assertEqual(statistics["note_count"], 1)
        self.assertEqual(statistics["today_ai_requests"], 1)
        self.assertEqual(statistics["active_session_count"], 1)

    def test_t2_08_detail_not_found(self):
        """不存在的用户返回 404"""
        response = self.client.get(
            "/admin/users/999999999",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 404, response.text)


# ============================================================
# T3 封禁
# ============================================================


class TestBanUser(BaseA2Test):

    def test_t3_01_ban_disables_and_revokes_all_credentials(self):
        """封禁：账户禁用 + 会话/Refresh Token 全部撤销 + 学习数据保留"""
        admin_id, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("ban")
        self.seed_learning_data(user_id)

        client_a, token_a, _ = self.login_client(user_name)
        _, token_b, _ = self.login_client(user_name)

        before = self.session_state(user_id)
        self.assertEqual(before["total"], 2)
        self.assertEqual(before["active"], 2)

        audit_before = self.audit_count(target_id=user_id)

        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": "封禁验收原因"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["user_id"], user_id)
        self.assertIs(data["is_active"], False)
        self.assertEqual(data["revoked_session_count"], 2)
        self.assertEqual(data["revoked_token_count"], 2)
        self.assertIs(data["changed"], True)

        # 数据库状态
        user = self.read_user(user_id)
        self.assertEqual(user["is_active"], 0)
        self.assertEqual(self.session_state(user_id)["active"], 0)
        self.assertEqual(self.token_state(user_id)["active"], 0)

        # 学习数据保留
        counts = self.learning_counts(user_id)
        self.assertEqual(counts["plans"], 2)
        self.assertEqual(counts["notes"], 2)

        # 旧凭证失效
        me = client_a.get("/users/me", headers=self.auth(token_a))
        self.assertEqual(me.status_code, 401, me.text)
        self.assertEqual(
            me.json()["detail"]["code"], "SESSION_REVOKED"
        )

        me_b = self.client.get("/users/me", headers=self.auth(token_b))
        self.assertEqual(me_b.status_code, 401)

        refresh = client_a.post(
            "/auth/refresh", headers=CSRF_HEADERS
        )
        self.assertNotEqual(refresh.status_code, 200, refresh.text)
        self.assertIn(
            refresh.json()["detail"]["code"],
            {"ACCOUNT_DISABLED", "SESSION_REVOKED", "REFRESH_INVALID"},
        )

        relogin = self.client.post(
            "/auth/login",
            data={"username": user_name, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        self.assertEqual(relogin.status_code, 403, relogin.text)
        self.assertEqual(
            relogin.json()["detail"]["code"], "ACCOUNT_DISABLED"
        )

        # 审计
        self.assertEqual(
            self.audit_count(target_id=user_id), audit_before + 1
        )
        rows = self.db_all(
            "SELECT admin_id, action, target_type, before_data, "
            "after_data, reason, created_at "
            "FROM admin_audit_logs WHERE target_id = :t "
            "ORDER BY id DESC LIMIT 1",
            t=user_id,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["admin_id"], admin_id)
        self.assertEqual(row["action"], "BAN_USER")
        self.assertEqual(row["target_type"], "USER")
        self.assertEqual(row["reason"], "封禁验收原因")


# ============================================================
# T4 解封
# ============================================================


class TestUnbanUser(BaseA2Test):

    def test_t4_01_unban_restores_login_but_not_old_sessions(self):
        """解封：恢复登录能力，不恢复旧会话"""
        _, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("unban")
        old_token, _ = self.login(user_name)

        ban = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": "先封禁"},
        )
        self.assertEqual(ban.status_code, 200, ban.text)

        unban = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/unban",
            {"reason": "解封验收"},
        )
        self.assertEqual(unban.status_code, 200, unban.text)
        data = unban.json()["data"]
        self.assertIs(data["is_active"], True)
        self.assertIs(data["changed"], True)
        self.assertEqual(data["revoked_session_count"], 0)
        self.assertEqual(data["revoked_token_count"], 0)

        self.assertEqual(self.read_user(user_id)["is_active"], 1)

        # 旧会话未恢复
        me = self.client.get(
            "/users/me", headers=self.auth(old_token)
        )
        self.assertEqual(me.status_code, 401, me.text)
        self.assertEqual(
            me.json()["detail"]["code"], "SESSION_REVOKED"
        )

        # 可重新登录
        new_token, _ = self.login(user_name)
        me = self.client.get(
            "/users/me", headers=self.auth(new_token)
        )
        self.assertEqual(me.status_code, 200, me.text)

        self.assertEqual(
            self.audit_count(target_id=user_id, action="UNBAN_USER"), 1
        )

    def test_t4_02_duplicate_ban_and_unban_return_409(self):
        """重复封禁/解封返回 409，且不写审计"""
        _, _, admin_token = self.make_admin("op")
        user_id, _, _ = self.make_user("dup")

        first = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": "首次封禁"},
        )
        self.assertEqual(first.status_code, 200, first.text)

        audit_after_ban = self.audit_count(target_id=user_id)

        second = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": "重复封禁"},
        )
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(
            second.json()["detail"]["code"], "USER_ALREADY_DISABLED"
        )
        self.assertEqual(
            self.audit_count(target_id=user_id), audit_after_ban
        )

        unban = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/unban",
            {"reason": "解封"},
        )
        self.assertEqual(unban.status_code, 200, unban.text)

        audit_after_unban = self.audit_count(target_id=user_id)

        again = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/unban",
            {"reason": "重复解封"},
        )
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(
            again.json()["detail"]["code"], "USER_ALREADY_ACTIVE"
        )
        self.assertEqual(
            self.audit_count(target_id=user_id), audit_after_unban
        )


# ============================================================
# T5 强制下线
# ============================================================


class TestRevokeSessions(BaseA2Test):

    def test_t5_01_revoke_keeps_account_active(self):
        """强制下线：账户状态不变，会话与 Token 撤销"""
        _, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("revoke")
        token, _ = self.login(user_name)

        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/revoke-sessions",
            {"reason": "强制下线验收"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIs(data["is_active"], True)
        self.assertIs(data["changed"], True)
        self.assertGreaterEqual(data["revoked_session_count"], 1)

        self.assertEqual(self.read_user(user_id)["is_active"], 1)
        self.assertEqual(self.session_state(user_id)["active"], 0)
        self.assertEqual(self.token_state(user_id)["active"], 0)

        me = self.client.get("/users/me", headers=self.auth(token))
        self.assertEqual(me.status_code, 401, me.text)

        # 仍可重新登录
        new_token, _ = self.login(user_name)
        me = self.client.get(
            "/users/me", headers=self.auth(new_token)
        )
        self.assertEqual(me.status_code, 200, me.text)

        self.assertEqual(
            self.audit_count(
                target_id=user_id, action="REVOKE_SESSIONS"
            ),
            1,
        )

    def test_t5_02_no_change_writes_no_audit(self):
        """无实际变更的强制下线不写审计"""
        _, _, admin_token = self.make_admin("op")
        user_id, _, _ = self.make_user("noop")

        audit_before = self.audit_count(target_id=user_id)

        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/revoke-sessions",
            {"reason": "无变更下线"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIs(data["changed"], False)
        self.assertEqual(data["revoked_session_count"], 0)
        self.assertEqual(data["revoked_token_count"], 0)
        self.assertEqual(
            self.audit_count(target_id=user_id), audit_before
        )

    def test_t5_03_expired_unrevoked_session_counts_as_change(self):
        """过期未撤销会话被撤销时视为实际变更并写审计"""
        _, _, admin_token = self.make_admin("op")
        user_id, _, _ = self.make_user("expired")
        family_id = str(uuid.uuid4())
        now = utc_db_now()

        self.db_exec(
            "INSERT INTO login_sessions "
            "(family_id, user_id, user_agent, created_at, "
            "last_activity_at, absolute_expires_at, revoked_at, "
            "revoked_reason) "
            "VALUES (:f, :u, 'pytest', :created, :last, :expires, "
            "NULL, NULL)",
            f=family_id,
            u=user_id,
            created=now - timedelta(days=10),
            last=now - timedelta(days=9),
            expires=now - timedelta(days=2),
        )
        self.db_exec(
            "INSERT INTO refresh_tokens "
            "(user_id, token_hash, family_id, expires_at) "
            "VALUES (:u, :h, :f, :expires)",
            u=user_id,
            h=uuid.uuid4().hex + uuid.uuid4().hex,
            f=family_id,
            expires=now - timedelta(days=2),
        )

        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/revoke-sessions",
            {"reason": "过期会话下线"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIs(data["changed"], True)
        self.assertEqual(data["revoked_session_count"], 1)
        self.assertEqual(data["revoked_token_count"], 1)

        row = self.db_all(
            "SELECT revoked_at, revoked_reason FROM login_sessions "
            "WHERE family_id = :f",
            f=family_id,
        )[0]
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(row["revoked_reason"], "ADMIN")
        self.assertEqual(
            self.audit_count(
                target_id=user_id, action="REVOKE_SESSIONS"
            ),
            1,
        )

    def test_t5_04_token_only_revocation_is_change(self):
        """仅 Token 发生撤销时也视为变更并写审计"""
        _, _, admin_token = self.make_admin("op")
        user_id, _, _ = self.make_user("tokonly")
        family_id = str(uuid.uuid4())
        now = utc_db_now()

        self.db_exec(
            "INSERT INTO login_sessions "
            "(family_id, user_id, user_agent, created_at, "
            "last_activity_at, absolute_expires_at, revoked_at, "
            "revoked_reason) "
            "VALUES (:f, :u, 'pytest', :now, :now, :expires, :now, "
            "'LOGOUT')",
            f=family_id,
            u=user_id,
            now=now,
            expires=now + timedelta(days=7),
        )
        self.db_exec(
            "INSERT INTO refresh_tokens "
            "(user_id, token_hash, family_id, expires_at) "
            "VALUES (:u, :h, :f, :expires)",
            u=user_id,
            h=uuid.uuid4().hex + uuid.uuid4().hex,
            f=family_id,
            expires=now + timedelta(days=7),
        )

        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/revoke-sessions",
            {"reason": "仅 Token 撤销"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIs(data["changed"], True)
        self.assertEqual(data["revoked_session_count"], 0)
        self.assertEqual(data["revoked_token_count"], 1)
        self.assertEqual(
            self.audit_count(
                target_id=user_id, action="REVOKE_SESSIONS"
            ),
            1,
        )


# ============================================================
# T6 事务回滚
# ============================================================


class TestAuditFailureRollback(BaseA2Test):

    def test_t6_01_audit_failure_rolls_back_all(self):
        """审计写入失败：账户状态、Session、Token 全部回滚"""
        _, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("rollback")
        self.login(user_name)

        audit_before = self.audit_count(target_id=user_id)
        self.assertEqual(self.session_state(user_id)["active"], 1)
        self.assertEqual(self.token_state(user_id)["active"], 1)

        self.db_exec("DROP TRIGGER IF EXISTS a2_fail_audit_bi")
        self.db_exec(
            "CREATE TRIGGER a2_fail_audit_bi "
            "BEFORE INSERT ON admin_audit_logs "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' "
            "SET MESSAGE_TEXT = 'A2_AUDIT_FAIL'"
        )

        try:
            response = self.post_admin(
                admin_token,
                f"/admin/users/{user_id}/ban",
                {"reason": "事务回滚验收"},
            )
            self.assertEqual(response.status_code, 500, response.text)
        finally:
            self.db_exec("DROP TRIGGER IF EXISTS a2_fail_audit_bi")

        self.assertEqual(self.read_user(user_id)["is_active"], 1)
        self.assertEqual(self.session_state(user_id)["active"], 1)
        self.assertEqual(self.token_state(user_id)["active"], 1)
        self.assertEqual(
            self.audit_count(target_id=user_id), audit_before
        )


# ============================================================
# T7 并发
# ============================================================


class TestConcurrency(BaseA2Test):

    def test_t7_01_ban_races_login(self):
        """封禁与登录竞争：封禁后不存在可用会话"""
        _, _, admin_token = self.make_admin("op")

        for index in range(3):
            user_id, user_name, _ = self.make_user(f"race{index}")
            barrier = threading.Barrier(2)
            results: dict = {}

            def do_login():
                try:
                    client = _new_client()
                    barrier.wait(timeout=10)
                    response = client.post(
                        "/auth/login",
                        data={
                            "username": user_name,
                            "password": PASSWORD,
                        },
                        headers=CSRF_HEADERS,
                    )
                    token = None
                    if response.status_code == 200:
                        token = response.json()["data"]["access_token"]
                    results["login"] = (response.status_code, token)
                except Exception as exc:  # pragma: no cover
                    results["login"] = ("EXC", repr(exc))

            def do_ban():
                try:
                    client = _new_client()
                    barrier.wait(timeout=10)
                    response = client.post(
                        f"/admin/users/{user_id}/ban",
                        json={"reason": "并发封禁"},
                        headers={
                            **self.auth(admin_token),
                            **CSRF_HEADERS,
                        },
                    )
                    results["ban"] = response.status_code
                except Exception as exc:  # pragma: no cover
                    results["ban"] = ("EXC", repr(exc))

            self.run_threads([do_login, do_ban])

            self.assertEqual(results["ban"], 200)
            self.assertEqual(
                self.read_user(user_id)["is_active"], 0
            )
            self.assertEqual(
                self.session_state(user_id)["active"], 0
            )
            self.assertEqual(
                self.token_state(user_id)["active"], 0
            )

            login_status, login_token = results["login"]
            self.assertIn(login_status, (200, 403))
            if login_status == 200:
                me = self.client.get(
                    "/users/me", headers=self.auth(login_token)
                )
                self.assertNotEqual(me.status_code, 200, me.text)

    def test_t7_02_revoke_races_refresh(self):
        """强制下线与刷新竞争：最终无可用会话/Token"""
        _, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("rrace")
        client, token, _ = self.login_client(user_name)

        barrier = threading.Barrier(2)
        results: dict = {}

        def do_refresh():
            try:
                barrier.wait(timeout=10)
                response = client.post(
                    "/auth/refresh", headers=CSRF_HEADERS
                )
                new_token = None
                if response.status_code == 200:
                    new_token = response.json()["data"]["access_token"]
                results["refresh"] = (response.status_code, new_token)
            except Exception as exc:  # pragma: no cover
                results["refresh"] = ("EXC", repr(exc))

        def do_revoke():
            try:
                revoke_client = _new_client()
                barrier.wait(timeout=10)
                response = revoke_client.post(
                    f"/admin/users/{user_id}/revoke-sessions",
                    json={"reason": "并发强制下线"},
                    headers={
                        **self.auth(admin_token),
                        **CSRF_HEADERS,
                    },
                )
                results["revoke"] = response.status_code
            except Exception as exc:  # pragma: no cover
                results["revoke"] = ("EXC", repr(exc))

        self.run_threads([do_refresh, do_revoke])

        self.assertEqual(results["revoke"], 200)
        self.assertEqual(self.read_user(user_id)["is_active"], 1)
        self.assertEqual(self.session_state(user_id)["active"], 0)
        self.assertEqual(self.token_state(user_id)["active"], 0)

        refresh_status, new_token = results["refresh"]
        self.assertIn(refresh_status, (200, 401, 403))
        if refresh_status == 200:
            me = self.client.get(
                "/users/me", headers=self.auth(new_token)
            )
            self.assertNotEqual(me.status_code, 200, me.text)

    def test_t7_03_two_admins_same_target(self):
        """两个管理员同时封禁同一用户：一次成功一次 409"""
        _, _, admin_a = self.make_admin("opA")
        _, _, admin_b = self.make_admin("opB")
        user_id, _, _ = self.make_user("duel")

        barrier = threading.Barrier(2)
        results: dict = {}

        def do_ban(key, token):
            def runner():
                try:
                    client = _new_client()
                    barrier.wait(timeout=10)
                    response = client.post(
                        f"/admin/users/{user_id}/ban",
                        json={"reason": "双管理员并发"},
                        headers={
                            **self.auth(token),
                            **CSRF_HEADERS,
                        },
                    )
                    results[key] = response.status_code
                except Exception as exc:  # pragma: no cover
                    results[key] = ("EXC", repr(exc))

            return runner

        self.run_threads(
            [do_ban("a", admin_a), do_ban("b", admin_b)]
        )

        self.assertEqual(
            sorted([results["a"], results["b"]]), [200, 409]
        )
        self.assertEqual(self.read_user(user_id)["is_active"], 0)
        self.assertEqual(
            self.audit_count(target_id=user_id, action="BAN_USER"), 1
        )

    def test_t7_04_operator_demoted_during_action(self):
        """操作者被降级：事务内重新校验，拒绝执行"""
        admin_id, _, admin_token = self.make_admin("demote")
        user_id, _, _ = self.make_user("victim")

        conn = engine.connect()
        transaction = conn.begin()
        try:
            conn.execute(
                text("UPDATE users SET role = 'USER' WHERE id = :i"),
                {"i": admin_id},
            )
            results: dict = {}

            def do_ban():
                try:
                    client = _new_client()
                    response = client.post(
                        f"/admin/users/{user_id}/ban",
                        json={"reason": "降级并发"},
                        headers={
                            **self.auth(admin_token),
                            **CSRF_HEADERS,
                        },
                    )
                    results["ban"] = (
                        response.status_code,
                        response.json().get("detail", {}).get("code"),
                    )
                except Exception as exc:  # pragma: no cover
                    results["ban"] = ("EXC", repr(exc))

            thread = threading.Thread(target=do_ban)
            thread.start()
            time.sleep(0.8)
            transaction.commit()
            thread.join(timeout=40)
            self.assertFalse(thread.is_alive())
        finally:
            if transaction.is_active:
                transaction.rollback()
            conn.close()

        status, code = results["ban"]
        self.assertEqual(status, 403)
        self.assertEqual(code, "ADMIN_REQUIRED")
        self.assertEqual(self.read_user(user_id)["is_active"], 1)
        self.assertEqual(self.audit_count(target_id=user_id), 0)

    def test_t7_05_operator_session_revoked_during_action(self):
        """操作者会话被撤销：事务内重新校验，拒绝执行"""
        admin_id, _, admin_token = self.make_admin("revoked")
        user_id, _, _ = self.make_user("victim2")
        family_id = self.family_id_of(admin_token)

        conn = engine.connect()
        transaction = conn.begin()
        try:
            conn.execute(
                text(
                    "UPDATE login_sessions "
                    "SET revoked_at = :now, revoked_reason = 'TEST_RACE' "
                    "WHERE family_id = :f AND revoked_at IS NULL"
                ),
                {"now": utc_db_now(), "f": family_id},
            )
            results: dict = {}

            def do_ban():
                try:
                    client = _new_client()
                    response = client.post(
                        f"/admin/users/{user_id}/ban",
                        json={"reason": "会话撤销并发"},
                        headers={
                            **self.auth(admin_token),
                            **CSRF_HEADERS,
                        },
                    )
                    results["ban"] = (
                        response.status_code,
                        response.json().get("detail", {}).get("code"),
                    )
                except Exception as exc:  # pragma: no cover
                    results["ban"] = ("EXC", repr(exc))

            thread = threading.Thread(target=do_ban)
            thread.start()
            time.sleep(0.8)
            transaction.commit()
            thread.join(timeout=40)
            self.assertFalse(thread.is_alive())
        finally:
            if transaction.is_active:
                transaction.rollback()
            conn.close()

        status, code = results["ban"]
        self.assertEqual(status, 401)
        self.assertEqual(code, "SESSION_REVOKED")
        self.assertEqual(self.read_user(user_id)["is_active"], 1)
        self.assertEqual(self.audit_count(target_id=user_id), 0)


# ============================================================
# T8 审计
# ============================================================


class TestAuditLogs(BaseA2Test):

    def test_t8_01_operator_snapshot_and_utc_time(self):
        """审计：操作人、原因、前后快照、UTC 时间"""
        admin_id, _, admin_token = self.make_admin("op")
        user_id, user_name, _ = self.make_user("audit")
        self.login(user_name)

        before = datetime.now(timezone.utc)
        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": "审计快照验收"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = datetime.now(timezone.utc)

        data = self.client.get(
            "/admin/audit-logs",
            params={"page": 1, "page_size": 100},
            headers=self.auth(admin_token),
        ).json()["data"]

        matches = [
            item
            for item in data["items"]
            if item["target_id"] == user_id
            and item["action"] == "BAN_USER"
        ]
        self.assertEqual(len(matches), 1)
        item = matches[0]

        self.assertEqual(item["admin_id"], admin_id)
        self.assertEqual(item["target_type"], "USER")
        self.assertEqual(item["reason"], "审计快照验收")

        self.assertIsInstance(item["before_data"], dict)
        self.assertIsInstance(item["after_data"], dict)
        self.assertIs(item["before_data"]["is_active"], True)
        self.assertIs(item["after_data"]["is_active"], False)
        self.assertGreaterEqual(
            item["before_data"]["active_session_count"], 1
        )
        self.assertGreaterEqual(
            item["after_data"]["revoked_session_count"], 1
        )

        created_at = _parse_dt(item["created_at"])
        self.assertIsNotNone(created_at.tzinfo)
        self.assertEqual(created_at.utcoffset(), timedelta(0))
        self.assertGreaterEqual(
            created_at, before - timedelta(seconds=30)
        )
        self.assertLessEqual(
            created_at, after + timedelta(seconds=30)
        )

    def test_t8_02_filter_by_action(self):
        """审计按操作类型筛选"""
        _, _, admin_token = self.make_admin("op")
        target_id, user_name, _ = self.make_user("filter")
        self.login(user_name)

        ban = self.post_admin(
            admin_token,
            f"/admin/users/{target_id}/ban",
            {"reason": "筛选-封禁"},
        )
        self.assertEqual(ban.status_code, 200, ban.text)

        response = self.client.get(
            "/admin/audit-logs",
            params={
                "page": 1,
                "page_size": 100,
                "action": "REVOKE_SESSIONS",
            },
            headers=self.auth(admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertTrue(
            all(item["action"] == "REVOKE_SESSIONS"
                for item in data["items"])
        )
        expected = int(
            self.db_scalar(
                "SELECT COUNT(*) FROM admin_audit_logs "
                "WHERE action = 'REVOKE_SESSIONS'"
            )
        )
        self.assertEqual(data["total"], expected)

    def test_t8_03_pagination(self):
        """审计分页"""
        _, _, admin_token = self.make_admin("op")
        for index in range(2):
            user_id, _, _ = self.make_user(f"page{index}")
            response = self.post_admin(
                admin_token,
                f"/admin/users/{user_id}/ban",
                {"reason": f"分页-{index}"},
            )
            self.assertEqual(response.status_code, 200, response.text)

        page1 = self.client.get(
            "/admin/audit-logs",
            params={"page": 1, "page_size": 1},
            headers=self.auth(admin_token),
        ).json()["data"]
        page2 = self.client.get(
            "/admin/audit-logs",
            params={"page": 2, "page_size": 1},
            headers=self.auth(admin_token),
        ).json()["data"]

        self.assertGreaterEqual(page1["total"], 2)
        self.assertEqual(len(page1["items"]), 1)
        self.assertEqual(len(page2["items"]), 1)
        self.assertNotEqual(
            page1["items"][0]["id"], page2["items"][0]["id"]
        )

    def test_t8_04_reason_validation(self):
        """拒绝空白原因及超长原因，超长边界外正常"""
        _, _, admin_token = self.make_admin("op")
        user_id, _, _ = self.make_user("reason")

        for payload in (
            {"reason": ""},
            {"reason": "   "},
            {"reason": "x" * 201},
            {},
        ):
            with self.subTest(reason=payload):
                response = self.post_admin(
                    admin_token,
                    f"/admin/users/{user_id}/ban",
                    payload,
                )
                self.assertEqual(
                    response.status_code, 422, response.text
                )

        # 200 字符边界允许，且去掉首尾空白后存储
        trimmed = "边界原因"
        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/ban",
            {"reason": " " * 3 + trimmed + " " * 3},
        )
        self.assertEqual(response.status_code, 200, response.text)

        rows = self.db_all(
            "SELECT reason FROM admin_audit_logs "
            "WHERE target_id = :t AND action = 'BAN_USER' "
            "ORDER BY id DESC LIMIT 1",
            t=user_id,
        )
        self.assertEqual(rows[0]["reason"], trimmed)

        # 强制下线同样拒绝空白原因
        response = self.post_admin(
            admin_token,
            f"/admin/users/{user_id}/revoke-sessions",
            {"reason": "   "},
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()