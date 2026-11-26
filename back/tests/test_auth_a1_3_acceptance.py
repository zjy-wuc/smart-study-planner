"""Auth V2.0 A1.3 集中验收测试（只读业务源码，不修改源码）。

约束：
- 仅使用隔离数据库 ssp_a0_migrate2。
- 邮件发送全部 Mock，不产生真实邮件。
- 测试数据在 tearDownClass 中精确清理。
- 不输出密钥、Token、密码、验证码。
"""

import threading
import unittest
import uuid

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.config import settings
from app.core import security
from app.core.auth_cookie import get_request_ip, set_refresh_cookie
from app.core.clock import business_today, utc_db_now
from app.database import SessionLocal, engine
from app.main import app
from app.repositories.auth import (
    auth_event_repository,
    session_repository,
    token_repository,
    user_repository,
    verification_repository,
)
from app.schemas.auth import EmailCodePurpose
from app.schemas.user import UserCreate
from app.services.auth import (
    activity_service,
    auth_service,
    mail_service,
    rate_limit_service,
    session_service,
    verification_service,
)


TEST_DB = "ssp_a0_migrate2"
ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}
PASSWORD = "GoodPass123"


def assert_isolated_db():
    with engine.connect() as conn:
        name = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if name != TEST_DB:
        raise RuntimeError(f"拒绝在非隔离库运行: {name}")


def _in_clause(sql, key="ids"):
    return text(sql).bindparams(bindparam(key, expanding=True))


class BaseAuthTest(unittest.TestCase):
    """共享隔离库守卫、邮件 Mock、数据清理与常用构造器。"""

    @classmethod
    def setUpClass(cls):
        assert_isolated_db()

        tag = "".join(ch for ch in cls.__name__ if ch.isalnum())[:8].lower()
        cls.PREFIX = f"a13{tag}{uuid.uuid4().hex[:6]}"
        cls.START = utc_db_now()

        cls._mail_ready = mail_service.mail_ready
        cls._mail_send = mail_service.send_verification_code
        cls._ip_pwd = settings.PASSWORD_IP_MAX_ATTEMPTS
        cls._ip_mail = settings.EMAIL_CODE_IP_MAX_ATTEMPTS

        settings.PASSWORD_IP_MAX_ATTEMPTS = 100000
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 100000

        cls.sent = []
        mail_service.mail_ready = staticmethod(lambda: True)

        def fake_send(*, email, code, purpose):
            cls.sent.append((email, str(purpose), code))
            return True

        mail_service.send_verification_code = staticmethod(fake_send)

    @classmethod
    def tearDownClass(cls):
        mail_service.mail_ready = cls._mail_ready
        mail_service.send_verification_code = cls._mail_send
        settings.PASSWORD_IP_MAX_ATTEMPTS = cls._ip_pwd
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = cls._ip_mail
        cls.cleanup()

    @classmethod
    def cleanup(cls):
        with engine.begin() as conn:
            uids = [
                row[0]
                for row in conn.execute(
                    text("SELECT id FROM users WHERE username LIKE :p"),
                    {"p": cls.PREFIX + "%"},
                )
            ]

            if uids:
                params = {"ids": uids}
                conn.execute(
                    _in_clause("DELETE FROM refresh_tokens WHERE user_id IN :ids"),
                    params,
                )
                conn.execute(
                    _in_clause("DELETE FROM login_sessions WHERE user_id IN :ids"),
                    params,
                )
                conn.execute(
                    _in_clause("DELETE FROM auth_events WHERE user_id IN :ids"),
                    params,
                )
                conn.execute(
                    _in_clause("DELETE FROM email_verifications WHERE user_id IN :ids"),
                    params,
                )
                conn.execute(
                    _in_clause("DELETE FROM users WHERE id IN :ids"),
                    params,
                )

            conn.execute(
                text("DELETE FROM email_verifications WHERE email LIKE :p"),
                {"p": cls.PREFIX + "%"},
            )
            conn.execute(
                text("DELETE FROM auth_events WHERE identifier LIKE :p"),
                {"p": cls.PREFIX + "%"},
            )
            # 仅清理本次测试期间产生的匿名 IP 限流事件
            conn.execute(
                text(
                    "DELETE FROM auth_events "
                    "WHERE user_id IS NULL AND identifier IS NULL "
                    "AND ip = '127.0.0.1' AND created_at >= :start"
                ),
                {"start": cls.START},
            )
            

    # ---------- 构造器 ----------

    def new_client(self):
        return TestClient(
            app,
            base_url="https://ssp.test",
            client=("127.0.0.1", 51888),
            raise_server_exceptions=False,
        )

    def make_user(self, suffix, *, password=PASSWORD, nickname=None, active=True):
        username = f"{self.PREFIX}{suffix}"
        email = f"{self.PREFIX}{suffix}@example.com"

        with SessionLocal() as db:
            uid = user_repository.insert_user(
                db,
                username=username,
                email=email,
                password_hash=security.hash_password(password),
                nickname=nickname if nickname is not None else username,
                now=utc_db_now(),
            )
            if not active:
                db.execute(
                    text("UPDATE users SET is_active = 0 WHERE id = :i"),
                    {"i": uid},
                )
            db.commit()

        return uid, username, email

    def mk_code(
        self,
        email,
        purpose,
        code="123456",
        *,
        user_id=None,
        family_id=None,
        status="SENT",
        expires_in=300,
        attempts=0,
        consumed=False,
        invalidated=False,
    ):
        purpose_value = purpose.value if hasattr(purpose, "value") else purpose
        now = utc_db_now()

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO email_verifications (
                        email, purpose, user_id, family_id,
                        code_hash, attempts, created_at, expires_at,
                        consumed_at, invalidated_at, request_ip, send_status
                    ) VALUES (
                        :email, :purpose, :user_id, :family_id,
                        :code_hash, :attempts, :now, :expires_at,
                        :consumed_at, :invalidated_at, :ip, :status
                    )
                    """
                ),
                {
                    "email": email,
                    "purpose": purpose_value,
                    "user_id": user_id,
                    "family_id": family_id,
                    "code_hash": security.hash_email_code(
                        email, purpose_value, code
                    ),
                    "attempts": attempts,
                    "now": now,
                    "expires_at": now + timedelta(seconds=expires_in),
                    "consumed_at": now if consumed else None,
                    "invalidated_at": now if invalidated else None,
                    "ip": "127.0.0.1",
                    "status": status,
                },
            )
            return int(result.lastrowid)

    def login(self, username, password=PASSWORD):
        with SessionLocal() as db:
            pair, user = auth_service.login_with_password(
                db,
                identifier=username,
                password=password,
                ip="127.0.0.1",
                user_agent="test-agent",
            )
        return pair.model_dump(), user

    def get_session_row(self, family_id):
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM login_sessions WHERE family_id = :f"
                ),
                {"f": family_id},
            ).mappings().first()
        return dict(row) if row else None

    def count(self, sql, params=None):
        with engine.connect() as conn:
            return int(conn.execute(text(sql), params or {}).scalar_one())

    def backdate_activity(self, family_id, seconds):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET last_activity_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now() - timedelta(seconds=seconds), "f": family_id},
            )


# ======================================================================
# 第 3 节：模块导入与接口检查
# ======================================================================


class TestImportsAndInterface(BaseAuthTest):
    def test_all_auth_modules_import(self):
        import importlib

        for mod in (
            "app.config",
            "app.core.security",
            "app.core.clock",
            "app.core.auth_cookie",
            "app.core.deps",
            "app.schemas.auth",
            "app.schemas.user",
            "app.repositories.auth.user_repository",
            "app.repositories.auth.session_repository",
            "app.repositories.auth.token_repository",
            "app.repositories.auth.verification_repository",
            "app.repositories.auth.auth_event_repository",
            "app.repositories.auth.lock_repository",
            "app.services.auth.auth_service",
            "app.services.auth.session_service",
            "app.services.auth.user_service",
            "app.services.auth.verification_service",
            "app.services.auth.rate_limit_service",
            "app.services.auth.activity_service",
            "app.services.auth.mail_service",
        ):
            importlib.import_module(mod)

    def test_app_object_built(self):
        self.assertEqual(app.title, "智能学习计划管理系统")
        paths = app.openapi()["paths"]
        for expected in ("/health", "/users", "/auth/login", "/auth/refresh"):
            self.assertIn(expected, paths)

    def test_http_error_unified_envelope_contract(self):
        """HTTPException 4xx 响应应保持统一 {code,message,detail,data} 结构。

        当前 main.py 只注册了 RequestValidationError / Exception 处理器，
        未注册 StarletteHTTPException 处理器（导入了却未使用），
        导致 4xx 直接返回 {"detail": {...}}。本用例用于固定该契约。
        """
        client = self.new_client()
        resp = client.get("/users/me")
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertIn(
            "code",
            body,
            f"4xx 响应缺少统一 code 字段，实际响应：{body}",
        )

    def test_no_legacy_route_refs(self):
        spec = app.openapi()["paths"]

        # 旧版 logout-all 暂时关闭
        self.assertFalse(
            any("logout-all" in p or "logout_all" in p for p in spec)
        )

        # 匿名 GET /users（列出全部用户）不再开放
        self.assertIn("/users", spec)
        self.assertNotIn("get", spec["/users"])

    def test_revoke_all_sessions_repo_exists_but_unused(self):
        # 仓库层保留能力，但当前没有 Service/路由引用（A2 使用）
        self.assertTrue(callable(session_repository.revoke_all_sessions))
        self.assertTrue(callable(token_repository.revoke_all_tokens))

    def test_old_token_api_not_referenced(self):
        import inspect

        # 新代码中不应再出现旧版 issue_token_pair / RefreshRequest 语义
        source = inspect.getsource(auth_service)
        self.assertNotIn("issue_token_pair", source)
        self.assertNotIn("RefreshRequest", source)

    def test_route_signatures_consistent(self):
        # Service 与 Repository 参数一致性（关键函数可调用性）
        self.assertTrue(callable(session_service.get_active_session))
        self.assertTrue(callable(verification_service.check_verification))
        self.assertTrue(callable(verification_service.consume_verification))
        self.assertTrue(callable(verification_service.request_email_code))


# ======================================================================
# 第 4 节：注册
# ======================================================================


class TestRegister(BaseAuthTest):
    def _register(self, client, username, email, code, password=PASSWORD, nickname=None):
        payload = {
            "username": username,
            "password": password,
            "email": email,
            "code": code,
        }
        if nickname is not None:
            payload["nickname"] = nickname
        return client.post("/users", json=payload, headers=CSRF)

    def test_register_success_returns_access_and_cookie(self):
        client = self.new_client()
        _, username, email = self._user_names("ok")
        self.mk_code(email, EmailCodePurpose.REGISTER, "246810")

        resp = self._register(client, username, email, "246810")

        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["code"], 201)
        self.assertTrue(body["data"]["access_token"])
        self.assertEqual(body["data"]["token_type"], "Bearer")
        self.assertNotIn("refresh_token", resp.text)
        self.assertIn("set-cookie", {k.lower() for k in resp.headers.keys()})

        uid = body["data"]["user"]["id"]
        self.assertEqual(
            self.count("SELECT COUNT(*) FROM users WHERE id = :i", {"i": uid}), 1
        )
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM login_sessions WHERE user_id = :i", {"i": uid}
            ),
            1,
        )
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM refresh_tokens WHERE user_id = :i", {"i": uid}
            ),
            1,
        )

    def test_register_nickname_defaults_to_username(self):
        client = self.new_client()
        _, username, email = self._user_names("nick")
        self.mk_code(email, EmailCodePurpose.REGISTER, "135790")

        resp = self._register(client, username, email, "135790")
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["data"]["user"]["nickname"], username)

    def test_register_wrong_code_increments_persisted(self):
        client = self.new_client()
        _, username, email = self._user_names("wrong")
        vid = self.mk_code(email, EmailCodePurpose.REGISTER, "111111")

        resp = self._register(client, username, email, "222222")
        self.assertEqual(resp.status_code, 400, resp.text)

        with engine.connect() as conn:
            attempts = conn.execute(
                text("SELECT attempts FROM email_verifications WHERE id = :i"),
                {"i": vid},
            ).scalar_one()
        self.assertEqual(attempts, 1)

        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM users WHERE username = :u", {"u": username}
            ),
            0,
        )

    def test_register_rejects_consumed_code(self):
        client = self.new_client()
        _, username, email = self._user_names("used")
        self.mk_code(email, EmailCodePurpose.REGISTER, "333333", consumed=True)

        resp = self._register(client, username, email, "333333")
        self.assertEqual(resp.status_code, 400)

    def test_register_rejects_invalidated_code(self):
        client = self.new_client()
        _, username, email = self._user_names("inv")
        self.mk_code(email, EmailCodePurpose.REGISTER, "444444", invalidated=True)

        resp = self._register(client, username, email, "444444")
        self.assertEqual(resp.status_code, 400)

    def test_register_rejects_expired_code(self):
        client = self.new_client()
        _, username, email = self._user_names("exp")
        self.mk_code(email, EmailCodePurpose.REGISTER, "555555", expires_in=-1)

        resp = self._register(client, username, email, "555555")
        self.assertEqual(resp.status_code, 400)

    def test_register_rejects_other_purpose_code(self):
        client = self.new_client()
        _, username, email = self._user_names("purp")
        self.mk_code(email, EmailCodePurpose.LOGIN, "666666")

        resp = self._register(client, username, email, "666666")
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_username_409(self):
        client = self.new_client()
        uid, username, _ = self.make_user("dup1")  # 占用用户名
        email2 = f"{self.PREFIX}dup2@example.com"
        self.mk_code(email2, EmailCodePurpose.REGISTER, "777777")

        resp = self._register(client, username, email2, "777777")
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_register_duplicate_email_409(self):
        client = self.new_client()
        uid, _, email = self.make_user("dupemail")
        username2 = f"{self.PREFIX}dupemail2"
        self.mk_code(email, EmailCodePurpose.REGISTER, "888888")

        resp = self._register(client, username2, email, "888888")
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_register_failure_does_not_consume_code(self):
        client = self.new_client()
        uid, username, _ = self.make_user("nocon")  # 占用用户名

        email2 = f"{self.PREFIX}nocon2@example.com"
        vid = self.mk_code(email2, EmailCodePurpose.REGISTER, "999999")

        resp = self._register(client, username, email2, "999999")
        self.assertEqual(resp.status_code, 409, resp.text)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT consumed_at, invalidated_at FROM email_verifications "
                    "WHERE id = :i"
                ),
                {"i": vid},
            ).mappings().first()
        self.assertIsNone(row["consumed_at"])
        self.assertIsNone(row["invalidated_at"])

    def test_register_weak_password_rejected(self):
        client = self.new_client()
        _, username, email = self._user_names("weak")
        self.mk_code(email, EmailCodePurpose.REGISTER, "101010")

        resp = self._register(client, username, email, "101010", password="12345678")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_register_short_password_schema_rejected(self):
        client = self.new_client()
        _, username, email = self._user_names("short")
        self.mk_code(email, EmailCodePurpose.REGISTER, "101011")

        resp = self._register(client, username, email, "101011", password="Ab1!")
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_register_concurrent_same_username_only_one(self):
        _, username, _ = self._user_names("race")

        codes = []
        for _ in range(2):
            suffix = uuid.uuid4().hex[:5]
            email = f"{self.PREFIX}race{suffix}@example.com"
            vid = self.mk_code(email, EmailCodePurpose.REGISTER, "121212")
            codes.append((email, vid))

        results = []
        lock = threading.Lock()

        def worker(email):
            try:
                with SessionLocal() as db:
                    pair, user = auth_service.register(
                        db,
                        data=UserCreate(
                            username=username,
                            password=PASSWORD,
                            email=email,
                            code="121212",
                        ),
                        ip="127.0.0.1",
                        user_agent="race",
                    )
                with lock:
                    results.append("ok")
            except Exception:
                with lock:
                    results.append("fail")

        threads = [threading.Thread(target=worker, args=(e,)) for e, _ in codes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)

        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM users WHERE username = :u", {"u": username}
            ),
            1,
        )

    def _user_names(self, suffix):
        token = f"{suffix}{uuid.uuid4().hex[:4]}"
        return (
            None,
            f"{self.PREFIX}{token}",
            f"{self.PREFIX}{token}@example.com",
        )


# ======================================================================
# 第 5 节：密码登录
# ======================================================================


class TestPasswordLogin(BaseAuthTest):
    def test_login_by_username(self):
        uid, username, _ = self.make_user("u1")
        pair, user = self.login(username)
        self.assertTrue(pair["access_token"])
        self.assertEqual(user["id"], uid)

    def test_login_by_email(self):
        uid, _, email = self.make_user("u2")
        with SessionLocal() as db:
            pair, user = auth_service.login_with_password(
                db,
                identifier=email,
                password=PASSWORD,
                ip="127.0.0.1",
                user_agent="ua",
            )
        self.assertEqual(user["id"], uid)

    def test_username_and_email_share_failure_counter(self):
        uid, username, email = self.make_user("u3")

        def fail(identifier):
            with SessionLocal() as db:
                with self.assertRaises(Exception):
                    auth_service.login_with_password(
                        db,
                        identifier=identifier,
                        password="WrongPass999",
                        ip="127.0.0.1",
                        user_agent="ua",
                    )

        fail(username)
        fail(email)
        fail(username)
        fail(email)

        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE user_id = :i AND event_type = 'PASSWORD_FAILED'",
                {"i": uid},
            ),
            4,
        )

    def test_five_failures_lock_account(self):
        uid, username, _ = self.make_user("u4")

        for _ in range(5):
            with SessionLocal() as db:
                with self.assertRaises(Exception):
                    auth_service.login_with_password(
                        db,
                        identifier=username,
                        password="WrongPass999",
                        ip="127.0.0.1",
                        user_agent="ua",
                    )

        # 第 6 次即使密码正确也应被锁定拒绝
        with SessionLocal() as db:
            with self.assertRaises(Exception) as ctx:
                auth_service.login_with_password(
                    db,
                    identifier=username,
                    password=PASSWORD,
                    ip="127.0.0.1",
                    user_agent="ua",
                )
        detail = ctx.exception.detail
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(detail["code"], "RATE_LIMITED")

        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE user_id = :i AND event_type = 'PASSWORD_LOCKED'",
                {"i": uid},
            ),
            1,
        )

    def test_lock_does_not_extend(self):
        uid, username, _ = self.make_user("u5")

        for _ in range(5):
            with SessionLocal() as db:
                with self.assertRaises(Exception):
                    auth_service.login_with_password(
                        db,
                        identifier=username,
                        password="WrongPass999",
                        ip="127.0.0.1",
                        user_agent="ua",
                    )

        with engine.connect() as conn:
            first = conn.execute(
                text(
                    "SELECT created_at FROM auth_events "
                    "WHERE user_id = :i AND event_type = 'PASSWORD_LOCKED' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"i": uid},
            ).scalar_one()

        # 锁定期内再次尝试
        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_password(
                    db,
                    identifier=username,
                    password=PASSWORD,
                    ip="127.0.0.1",
                    user_agent="ua",
                )

        with engine.connect() as conn:
            latest = conn.execute(
                text(
                    "SELECT created_at FROM auth_events "
                    "WHERE user_id = :i AND event_type = 'PASSWORD_LOCKED' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"i": uid},
            ).scalar_one()

        self.assertEqual(first, latest)

    def test_lock_expires_and_login_recovers(self):
        uid, username, _ = self.make_user("u6")
        self.make_lock(uid, username, minutes_ago=16)

        pair, user = self.login(username)
        self.assertEqual(user["id"], uid)

    def test_successful_login_resets_failures(self):
        uid, username, _ = self.make_user("u7")

        for _ in range(3):
            with SessionLocal() as db:
                with self.assertRaises(Exception):
                    auth_service.login_with_password(
                        db,
                        identifier=username,
                        password="WrongPass999",
                        ip="127.0.0.1",
                        user_agent="ua",
                    )

        self.login(username)

        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE user_id = :i AND event_type = 'PASSWORD_CLEAR'",
                {"i": uid},
            ),
            1,
        )

        # 再失败 1 次不应触发锁定
        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_password(
                    db,
                    identifier=username,
                    password="WrongPass999",
                    ip="127.0.0.1",
                    user_agent="ua",
                )
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE user_id = :i AND event_type = 'PASSWORD_LOCKED'",
                {"i": uid},
            ),
            0,
        )

    def test_disabled_account_cannot_login(self):
        uid, username, _ = self.make_user("u8", active=False)
        with SessionLocal() as db:
            with self.assertRaises(Exception) as ctx:
                auth_service.login_with_password(
                    db,
                    identifier=username,
                    password=PASSWORD,
                    ip="127.0.0.1",
                    user_agent="ua",
                )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["code"], "ACCOUNT_DISABLED")

    def test_unknown_account_returns_generic_error(self):
        with SessionLocal() as db:
            with self.assertRaises(Exception) as ctx:
                auth_service.login_with_password(
                    db,
                    identifier=f"{self.PREFIX}ghost",
                    password=PASSWORD,
                    ip="127.0.0.1",
                    user_agent="ua",
                )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail["code"], "INVALID_CREDENTIALS")

    def test_ip_rate_limit_persisted(self):
        old = settings.PASSWORD_IP_MAX_ATTEMPTS
        settings.PASSWORD_IP_MAX_ATTEMPTS = 2
        try:
            rate_limit_service.reserve_password_attempt("10.9.8.7")
            rate_limit_service.reserve_password_attempt("10.9.8.7")
            with self.assertRaises(Exception) as ctx:
                rate_limit_service.reserve_password_attempt("10.9.8.7")
            self.assertEqual(ctx.exception.status_code, 429)
        finally:
            settings.PASSWORD_IP_MAX_ATTEMPTS = old
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM auth_events WHERE ip = '10.9.8.7'")
                )

    def test_ip_rate_limit_concurrent_not_bypassed(self):
        old = settings.PASSWORD_IP_MAX_ATTEMPTS
        settings.PASSWORD_IP_MAX_ATTEMPTS = 3
        ip = "10.9.8.6"
        ok = []
        lock = threading.Lock()

        def worker():
            try:
                rate_limit_service.reserve_password_attempt(ip)
                with lock:
                    ok.append(1)
            except Exception:
                pass

        try:
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
            self.assertEqual(sum(ok), 3)
        finally:
            settings.PASSWORD_IP_MAX_ATTEMPTS = old
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM auth_events WHERE ip = :ip"), {"ip": ip})

    def make_lock(self, uid, username, minutes_ago):
        when = utc_db_now() - timedelta(minutes=minutes_ago)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_events (user_id, identifier, event_type, ip, created_at) "
                    "VALUES (:u, :i, 'PASSWORD_LOCKED', '127.0.0.1', :t)"
                ),
                {"u": uid, "i": username, "t": when},
            )


# ======================================================================
# 第 6 节：邮箱验证码登录
# ======================================================================


class TestEmailCodeLogin(BaseAuthTest):
    def test_login_with_email_code(self):
        uid, _, email = self.make_user("e1")
        vid = self.mk_code(email, EmailCodePurpose.LOGIN, "112233", user_id=uid)

        with SessionLocal() as db:
            pair, user = auth_service.login_with_email(
                db, email=email, code="112233", ip="127.0.0.1", user_agent="ua"
            )

        self.assertEqual(user["id"], uid)
        self.assertTrue(pair.access_token)

        with engine.connect() as conn:
            consumed = conn.execute(
                text("SELECT consumed_at FROM email_verifications WHERE id = :i"),
                {"i": vid},
            ).scalar_one()
        self.assertIsNotNone(consumed)

    def test_register_code_cannot_login(self):
        uid, _, email = self.make_user("e2")
        self.mk_code(email, EmailCodePurpose.REGISTER, "223344")

        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_email(
                    db, email=email, code="223344", ip="127.0.0.1", user_agent="ua"
                )

    def test_reset_code_cannot_login(self):
        uid, _, email = self.make_user("e3")
        self.mk_code(email, EmailCodePurpose.RESET_PASSWORD, "334455", user_id=uid)

        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_email(
                    db, email=email, code="334455", ip="127.0.0.1", user_agent="ua"
                )

    def test_unknown_email_not_auto_registered(self):
        email = f"{self.PREFIX}noexist@example.com"
        before = self.count("SELECT COUNT(*) FROM users")

        with SessionLocal() as db:
            with self.assertRaises(Exception) as ctx:
                auth_service.login_with_email(
                    db, email=email, code="445566", ip="127.0.0.1", user_agent="ua"
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.count("SELECT COUNT(*) FROM users"), before)

    def test_disabled_account_cannot_login_with_code(self):
        uid, _, email = self.make_user("e4", active=False)
        self.mk_code(email, EmailCodePurpose.LOGIN, "556677", user_id=uid)

        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_email(
                    db, email=email, code="556677", ip="127.0.0.1", user_agent="ua"
                )

    def test_wrong_code_increments_attempts(self):
        uid, _, email = self.make_user("e5")
        vid = self.mk_code(email, EmailCodePurpose.LOGIN, "667788", user_id=uid)

        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.login_with_email(
                    db, email=email, code="000000", ip="127.0.0.1", user_agent="ua"
                )

        with engine.connect() as conn:
            attempts = conn.execute(
                text("SELECT attempts FROM email_verifications WHERE id = :i"),
                {"i": vid},
            ).scalar_one()
        self.assertEqual(attempts, 1)

    def test_concurrent_same_code_only_one_success(self):
        uid, _, email = self.make_user("e6")
        self.mk_code(email, EmailCodePurpose.LOGIN, "778899", user_id=uid)

        results = []
        lock = threading.Lock()

        def worker():
            try:
                with SessionLocal() as db:
                    pair, user = auth_service.login_with_email(
                        db,
                        email=email,
                        code="778899",
                        ip="127.0.0.1",
                        user_agent="ua",
                    )
                with lock:
                    results.append("ok")
            except Exception:
                with lock:
                    results.append("fail")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)

        self.assertEqual(results.count("ok"), 1, results)


# ======================================================================
# 第 7 节：Session 与 Access Token
# ======================================================================


class TestSessionAndAccess(BaseAuthTest):
    def test_access_token_claims(self):
        uid, username, _ = self.make_user("s1")
        pair, _ = self.login(username)

        payload = security.decode_access_token(pair["access_token"])
        self.assertEqual(payload["sub"], str(uid))
        self.assertEqual(payload["type"], "access")
        for key in ("family_id", "iat", "exp", "jti"):
            self.assertIn(key, payload)

        # refresh 与 access 的 family_id 一致、jti 不同
        rp = security.decode_refresh_token(pair["refresh_token"])
        self.assertEqual(rp["family_id"], payload["family_id"])
        self.assertNotEqual(rp["jti"], payload["jti"])

    def test_different_logins_different_family(self):
        uid, username, _ = self.make_user("s2")
        p1, _ = self.login(username)
        p2, _ = self.login(username)

        f1 = security.decode_access_token(p1["access_token"])["family_id"]
        f2 = security.decode_access_token(p2["access_token"])["family_id"]
        self.assertNotEqual(f1, f2)

    def test_refresh_token_rejected_as_access(self):
        uid, username, _ = self.make_user("s3")
        pair, _ = self.login(username)
        payload, code = security.decode_access_token_detailed(pair["refresh_token"])
        self.assertIsNone(payload)
        self.assertEqual(code, "TOKEN_TYPE_INVALID")

    def test_access_token_rejected_as_refresh(self):
        uid, username, _ = self.make_user("s4")
        pair, _ = self.login(username)
        self.assertIsNone(security.decode_refresh_token(pair["access_token"]))

    def test_missing_family_id_rejected(self):
        uid = 1
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode(
            {
                "sub": str(uid),
                "iat": now,
                "exp": now + 900,
                "type": "access",
                "jti": str(uuid.uuid4()),
            },
            settings.SECRET_KEY,
            algorithm=security.JWT_ALGORITHM,
        )
        self.assertIsNone(security.decode_access_token(token))

    def test_invalid_declarations_no_500(self):
        now = int(datetime.now(timezone.utc).timestamp())
        cases = [
            {"sub": "abc", "family_id": str(uuid.uuid4())},
            {"sub": str(2**64), "family_id": str(uuid.uuid4())},
            {"sub": "1", "family_id": "not-a-uuid"},
        ]
        for claims in cases:
            token = jwt.encode(
                {
                    **claims,
                    "iat": now,
                    "exp": now + 900,
                    "type": "access",
                    "jti": str(uuid.uuid4()),
                },
                settings.SECRET_KEY,
                algorithm=security.JWT_ALGORITHM,
            )
            self.assertIsNone(security.decode_access_token(token))

    def test_expired_access_returns_access_expired(self):
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode(
            {
                "sub": "1",
                "family_id": str(uuid.uuid4()),
                "iat": now - 2000,
                "exp": now - 100,
                "type": "access",
                "jti": str(uuid.uuid4()),
            },
            settings.SECRET_KEY,
            algorithm=security.JWT_ALGORITHM,
        )
        payload, code = security.decode_access_token_detailed(token)
        self.assertIsNone(payload)
        self.assertEqual(code, "ACCESS_EXPIRED")

    def test_bad_signature_rejected(self):
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode(
            {
                "sub": "1",
                "family_id": str(uuid.uuid4()),
                "iat": now,
                "exp": now + 900,
                "type": "access",
                "jti": str(uuid.uuid4()),
            },
            "x" * 40,
            algorithm=security.JWT_ALGORITHM,
        )
        self.assertIsNone(security.decode_access_token(token))

    def test_disabled_user_access_denied(self):
        uid, username, _ = self.make_user("s5")
        pair, _ = self.login(username)

        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET is_active = 0 WHERE id = :i"), {"i": uid}
            )

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertNotIn(username, resp.text)

    def test_revoked_session_access_fails(self):
        uid, username, _ = self.make_user("s6")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family, now=utc_db_now(), reason="TEST"
                )

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_idle_expiry(self):
        uid, username, _ = self.make_user("s7")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.backdate_activity(family, 8 * 24 * 3600)

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_absolute_expiry(self):
        uid, username, _ = self.make_user("s8")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET absolute_expires_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now() - timedelta(days=1), "f": family},
            )

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_absolute_boundary_future_allowed(self):
        uid, username, _ = self.make_user("s9")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET absolute_expires_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now() + timedelta(seconds=60), "f": family},
            )

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_absolute_boundary_now_expired(self):
        uid, username, _ = self.make_user("sa")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET absolute_expires_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now() - timedelta(microseconds=1000), "f": family},
            )

        client = self.new_client()
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_token_never_exceeds_session_deadline(self):
        uid, username, _ = self.make_user("sb")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        session = self.get_session_row(family)
        deadline = session["absolute_expires_at"].replace(tzinfo=timezone.utc)

        for token in (pair["access_token"], pair["refresh_token"]):
            payload = security.decode_token(token)
            self.assertLessEqual(
                datetime.fromtimestamp(payload["exp"], timezone.utc),
                deadline,
            )

    def test_access_expiry_default_15_minutes(self):
        uid, username, _ = self.make_user("sc")
        pair, _ = self.login(username)
        payload = security.decode_access_token(pair["access_token"])
        self.assertEqual(payload["exp"] - payload["iat"], 15 * 60)

    def test_refresh_expiry_default_7_days(self):
        uid, username, _ = self.make_user("sd")
        pair, _ = self.login(username)
        payload = security.decode_refresh_token(pair["refresh_token"])
        self.assertEqual(payload["exp"] - payload["iat"], 7 * 24 * 3600)


# ======================================================================
# 第 8 节：Refresh Token
# ======================================================================


class TestRefreshToken(BaseAuthTest):
    def test_normal_refresh_rotates(self):
        uid, username, _ = self.make_user("r1")
        pair, _ = self.login(username)
        old = pair["refresh_token"]
        family = security.decode_refresh_token(old)["family_id"]

        with SessionLocal() as db:
            new_pair = auth_service.rotate_refresh_token(
                db, refresh_token=old, ip="127.0.0.1"
            )

        self.assertNotEqual(old, new_pair.refresh_token)
        self.assertEqual(
            security.decode_refresh_token(new_pair.refresh_token)["family_id"],
            family,
        )

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT revoked_at, replaced_by FROM refresh_tokens "
                    "WHERE token_hash = :h"
                ),
                {"h": security.hash_refresh_token(old)},
            ).mappings().first()
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(
            row["replaced_by"], security.hash_refresh_token(new_pair.refresh_token)
        )

        # 新 Token 摘要确实入库
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM refresh_tokens WHERE token_hash = :h",
                {"h": security.hash_refresh_token(new_pair.refresh_token)},
            ),
            1,
        )

    def test_refresh_does_not_touch_activity(self):
        uid, username, _ = self.make_user("r2")
        pair, _ = self.login(username)
        family = security.decode_refresh_token(pair["refresh_token"])["family_id"]
        before = self.get_session_row(family)["last_activity_at"]

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET last_activity_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now() - timedelta(seconds=2000), "f": family},
            )
        marked = self.get_session_row(family)["last_activity_at"]

        with SessionLocal() as db:
            auth_service.rotate_refresh_token(
                db, refresh_token=pair["refresh_token"], ip="127.0.0.1"
            )

        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(marked, after)

    def test_replay_detection_revokes_family(self):
        uid, username, _ = self.make_user("r3")
        pair, _ = self.login(username)
        old = pair["refresh_token"]
        family = security.decode_refresh_token(old)["family_id"]

        # 其他设备会话，用于验证不受影响
        other_pair, _ = self.login(username)
        other_family = security.decode_refresh_token(other_pair["refresh_token"])[
            "family_id"
        ]

        with SessionLocal() as db:
            auth_service.rotate_refresh_token(db, refresh_token=old, ip="127.0.0.1")

        # 重放旧 Token
        with SessionLocal() as db:
            with self.assertRaises(Exception) as ctx:
                auth_service.rotate_refresh_token(
                    db, refresh_token=old, ip="127.0.0.1"
                )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail["code"], "SESSION_REVOKED")

        # 会话已撤销，且撤销已提交
        self.assertIsNotNone(self.get_session_row(family)["revoked_at"])
        self.assertEqual(self.get_session_row(family)["revoked_reason"], "REFRESH_REPLAY")

        # family 内所有 Token 撤销
        active = self.count(
            "SELECT COUNT(*) FROM refresh_tokens "
            "WHERE family_id = :f AND revoked_at IS NULL",
            {"f": family},
        )
        self.assertEqual(active, 0)

        # 其他设备不受影响
        self.assertIsNone(self.get_session_row(other_family)["revoked_at"])

    def test_concurrent_refresh_single_success(self):
        uid, username, _ = self.make_user("r4")
        pair, _ = self.login(username)
        token = pair["refresh_token"]

        results = []
        lock = threading.Lock()

        def worker():
            try:
                with SessionLocal() as db:
                    auth_service.rotate_refresh_token(
                        db, refresh_token=token, ip="127.0.0.1"
                    )
                with lock:
                    results.append("ok")
            except Exception:
                with lock:
                    results.append("fail")

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)

        self.assertEqual(results.count("ok"), 1, results)

    def test_rotated_token_cannot_rotate_again(self):
        uid, username, _ = self.make_user("r5")
        pair, _ = self.login(username)
        old = pair["refresh_token"]

        with SessionLocal() as db:
            auth_service.rotate_refresh_token(db, refresh_token=old, ip="127.0.0.1")

        with SessionLocal() as db:
            with self.assertRaises(Exception):
                auth_service.rotate_refresh_token(
                    db, refresh_token=old, ip="127.0.0.1"
                )

    def test_expires_in_matches_access(self):
        uid, username, _ = self.make_user("r6")
        pair, _ = self.login(username)
        payload = security.decode_access_token(pair["access_token"])
        remaining = payload["exp"] - int(datetime.now(timezone.utc).timestamp())
        self.assertLessEqual(abs(pair["expires_in"] - remaining), 2)

    def test_rotation_rollback_leaves_old_token_active(self):
        uid, username, _ = self.make_user("r7")
        pair, _ = self.login(username)
        old = pair["refresh_token"]
        old_hash = security.hash_refresh_token(old)

        # 模拟轮换过程中抛出异常 → 整笔事务回滚，旧 Token 不得处于部分轮换状态
        with SessionLocal() as db:
            try:
                with db.begin():
                    record = token_repository.find_by_hash(
                        db, token_hash=old_hash, for_update=True
                    )
                    self.assertIsNotNone(record)
                    token_repository.mark_rotated(
                        db,
                        token_id=record["id"],
                        new_token_hash="deadbeef" * 8,
                        now=utc_db_now(),
                    )
                    raise RuntimeError("模拟中途失败")
            except RuntimeError:
                pass

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT revoked_at, replaced_by FROM refresh_tokens "
                    "WHERE token_hash = :h"
                ),
                {"h": old_hash},
            ).mappings().first()
        self.assertIsNone(row["revoked_at"])
        self.assertIsNone(row["replaced_by"])

        # 旧 Token 仍可正常轮换
        with SessionLocal() as db:
            new_pair = auth_service.rotate_refresh_token(
                db, refresh_token=old, ip="127.0.0.1"
            )
        self.assertNotEqual(new_pair.refresh_token, old)

    def test_mark_rotated_is_conditional(self):
        uid, username, _ = self.make_user("r8")
        pair, _ = self.login(username)
        old_hash = security.hash_refresh_token(pair["refresh_token"])

        with SessionLocal() as db:
            with db.begin():
                record = token_repository.find_by_hash(
                    db, token_hash=old_hash, for_update=True
                )
                first = token_repository.mark_rotated(
                    db,
                    token_id=record["id"],
                    new_token_hash="aa" * 32,
                    now=utc_db_now(),
                )
        with SessionLocal() as db:
            with db.begin():
                second = token_repository.mark_rotated(
                    db,
                    token_id=record["id"],
                    new_token_hash="bb" * 32,
                    now=utc_db_now(),
                )

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)


# ======================================================================
# 第 9 节：Cookie 与 CSRF
# ======================================================================


class TestCookieAndCsrf(BaseAuthTest):
    def _register_via_http(self, client, suffix="c1"):
        username = f"{self.PREFIX}{suffix}"
        email = f"{username}@example.com"
        self.mk_code(email, EmailCodePurpose.REGISTER, "1357911"[:6])
        resp = client.post(
            "/users",
            json={
                "username": username,
                "password": PASSWORD,
                "email": email,
                "code": "135791",
            },
            headers=CSRF,
        )
        return resp, username, email

    def test_register_sets_secure_cookie_attributes(self):
        client = self.new_client()
        resp, _, _ = self._register_via_http(client)
        self.assertEqual(resp.status_code, 201, resp.text)

        cookie = resp.headers.get("set-cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/auth", cookie)
        self.assertIn("SameSite=lax", cookie.lower().replace("samesite", "SameSite"))
        self.assertNotIn("Domain=", cookie)
        self.assertIn("Max-Age=", cookie)
        self.assertIn("no-store", resp.headers.get("cache-control", ""))

    def test_login_sets_cookie(self):
        uid, username, _ = self.make_user("c2")
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("HttpOnly", resp.headers.get("set-cookie", ""))

    def test_json_never_contains_refresh_token(self):
        uid, username, _ = self.make_user("c3")
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF,
        )
        body = resp.json()
        self.assertNotIn("refresh_token", body["data"])
        self.assertNotIn("refresh_token", resp.text)

    def test_secure_flag_when_enabled(self):
        from starlette.responses import JSONResponse

        uid, username, _ = self.make_user("c4")
        pair, _ = self.login(username)

        old = settings.REFRESH_COOKIE_SECURE
        settings.REFRESH_COOKIE_SECURE = True
        try:
            resp = JSONResponse({})
            set_refresh_cookie(resp, pair["refresh_token"])
            self.assertIn("Secure", resp.headers.get("set-cookie", ""))
        finally:
            settings.REFRESH_COOKIE_SECURE = old

    def test_missing_origin_rejected(self):
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": "x", "password": PASSWORD},
            headers={"X-CSRF-Protection": "1"},
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_invalid_origin_rejected(self):
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": "x", "password": PASSWORD},
            headers={"Origin": "https://evil.example", "X-CSRF-Protection": "1"},
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_missing_csrf_header_rejected(self):
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": "x", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_wrong_csrf_header_rejected(self):
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": "x", "password": PASSWORD},
            headers={"Origin": ORIGIN, "X-CSRF-Protection": "0"},
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_cors_whitelist_matches_auth_origins(self):
        options = [
            m.kwargs
            for m in app.user_middleware
            if m.cls is CORSMiddleware
        ]
        self.assertTrue(options)
        self.assertEqual(options[0]["allow_origins"], settings.AUTH_ALLOWED_ORIGINS)
        self.assertTrue(options[0]["allow_credentials"])

    def test_body_refresh_token_not_accepted(self):
        uid, username, _ = self.make_user("c5")
        pair, _ = self.login(username)

        client = self.new_client()
        resp = client.post(
            "/auth/refresh",
            json={"refresh_token": pair["refresh_token"]},
            headers=CSRF,
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_x_forwarded_for_not_trusted(self):
        client = self.new_client()
        username = f"{self.PREFIX}xff"
        email = f"{username}@example.com"
        self.mk_code(email, EmailCodePurpose.REGISTER, "246802")

        resp = client.post(
            "/users",
            json={
                "username": username,
                "password": PASSWORD,
                "email": email,
                "code": "246802",
            },
            headers={**CSRF, "X-Forwarded-For": "203.0.113.9"},
        )
        self.assertEqual(resp.status_code, 201, resp.text)

        uid = resp.json()["data"]["user"]["id"]
        with engine.connect() as conn:
            ip = conn.execute(
                text(
                    "SELECT ip FROM auth_events "
                    "WHERE user_id = :i AND event_type = 'REGISTER_SUCCESS'"
                ),
                {"i": uid},
            ).scalar_one()
        self.assertEqual(ip, "127.0.0.1")

    def test_cookie_max_age_not_exceed_refresh(self):
        uid, username, _ = self.make_user("c6")
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF,
        )
        cookie = resp.headers.get("set-cookie", "")
        max_age = int(cookie.split("Max-Age=")[1].split(";")[0])
        # refresh 7 天
        self.assertLessEqual(max_age, 7 * 24 * 3600)


# ======================================================================
# 第 10 节：退出当前会话
# ======================================================================


class TestLogout(BaseAuthTest):
    def _login_http(self, client, username):
        return client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF,
        )

    def test_logout_revokes_and_clears_cookie(self):
        uid, username, _ = self.make_user("l1")
        client = self.new_client()

        login_resp = self._login_http(client, username)
        self.assertEqual(login_resp.status_code, 200, login_resp.text)
        access = login_resp.json()["data"]["access_token"]
        family = security.decode_access_token(access)["family_id"]

        resp = client.post("/auth/logout", headers=CSRF)
        self.assertEqual(resp.status_code, 200, resp.text)

        session = self.get_session_row(family)
        self.assertIsNotNone(session["revoked_at"])
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM refresh_tokens "
                "WHERE family_id = :f AND revoked_at IS NULL",
                {"f": family},
            ),
            0,
        )

        cookie = resp.headers.get("set-cookie", "")
        self.assertIn("Max-Age=0", cookie)

        # 旧 Access 下一次访问失败
        after = client.get(
            "/users/me", headers={"Authorization": f"Bearer {access}"}
        )
        self.assertEqual(after.status_code, 401, after.text)

    def test_logout_without_cookie_safe(self):
        client = self.new_client()
        resp = client.post("/auth/logout", headers=CSRF)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_repeat_logout_safe(self):
        uid, username, _ = self.make_user("l2")
        client = self.new_client()
        self._login_http(client, username)
        self.assertEqual(client.post("/auth/logout", headers=CSRF).status_code, 200)
        self.assertEqual(client.post("/auth/logout", headers=CSRF).status_code, 200)

    def test_logout_isolated_from_other_session(self):
        uid, username, _ = self.make_user("l3")

        c1 = self.new_client()
        c2 = self.new_client()

        r1 = self._login_http(c1, username)
        r2 = self._login_http(c2, username)

        f1 = security.decode_access_token(r1.json()["data"]["access_token"])[
            "family_id"
        ]
        f2 = security.decode_access_token(r2.json()["data"]["access_token"])[
            "family_id"
        ]

        c1.post("/auth/logout", headers=CSRF)

        self.assertIsNotNone(self.get_session_row(f1)["revoked_at"])
        self.assertIsNone(self.get_session_row(f2)["revoked_at"])

        still = c2.get(
            "/users/me",
            headers={"Authorization": f"Bearer {r2.json()['data']['access_token']}"},
        )
        self.assertEqual(still.status_code, 200, still.text)


# ======================================================================
# 第 11 节：活跃时间
# ======================================================================


class TestActivity(BaseAuthTest):
    def _login_http(self, client, username):
        resp = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF,
        )
        return resp.json()["data"]["access_token"]

    def test_activity_request_updates_timestamp(self):
        uid, username, _ = self.make_user("a1")
        client = self.new_client()
        access = self._login_http(client, username)
        family = security.decode_access_token(access)["family_id"]

        self.backdate_activity(family, 400)
        before = self.get_session_row(family)["last_activity_at"]

        resp = client.get(
            "/plans",
            headers={
                "Authorization": f"Bearer {access}",
                "X-User-Activity": "1",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        after = self.get_session_row(family)["last_activity_at"]
        self.assertGreater(after, before)

    def test_without_marker_no_update(self):
        uid, username, _ = self.make_user("a2")
        client = self.new_client()
        access = self._login_http(client, username)
        family = security.decode_access_token(access)["family_id"]

        self.backdate_activity(family, 400)
        before = self.get_session_row(family)["last_activity_at"]

        client.get("/plans", headers={"Authorization": f"Bearer {access}"})

        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(before, after)

    def test_auth_path_no_update(self):
        uid, username, _ = self.make_user("a3")
        client = self.new_client()
        access = self._login_http(client, username)
        family = security.decode_access_token(access)["family_id"]

        self.backdate_activity(family, 400)
        before = self.get_session_row(family)["last_activity_at"]

        client.post(
            "/auth/refresh",
            headers={**CSRF, "X-User-Activity": "1"},
        )

        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(before, after)

    def test_non_2xx_no_update(self):
        uid, username, _ = self.make_user("a4")
        client = self.new_client()
        access = self._login_http(client, username)
        family = security.decode_access_token(access)["family_id"]

        self.backdate_activity(family, 400)
        before = self.get_session_row(family)["last_activity_at"]

        resp = client.get(
            "/plans/999999999",
            headers={
                "Authorization": f"Bearer {access}",
                "X-User-Activity": "1",
            },
        )
        self.assertGreaterEqual(resp.status_code, 400)

        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(before, after)

    def test_interval_300s_no_rewrite(self):
        uid, username, _ = self.make_user("a5")
        client = self.new_client()
        access = self._login_http(client, username)
        family = security.decode_access_token(access)["family_id"]

        self.backdate_activity(family, 100)
        before = self.get_session_row(family)["last_activity_at"]

        client.get(
            "/plans",
            headers={
                "Authorization": f"Bearer {access}",
                "X-User-Activity": "1",
            },
        )

        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(before, after)

    def test_touch_does_not_revive_revoked(self):
        uid, username, _ = self.make_user("a6")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family, now=utc_db_now(), reason="TEST"
                )

        with SessionLocal() as db:
            affected = session_repository.touch_session(
                db,
                user_id=uid,
                family_id=family,
                now=utc_db_now(),
                idle_cutoff=utc_db_now() - timedelta(days=7),
                write_cutoff=utc_db_now() - timedelta(seconds=300),
            )
            db.commit()

        self.assertEqual(affected, 0)

    def test_activity_failure_swallowed(self):
        uid, username, _ = self.make_user("a7")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]

        original = session_repository.touch_session

        def boom(*args, **kwargs):
            raise RuntimeError("db down")

        session_repository.touch_session = boom
        try:
            # 不应抛出
            activity_service.record_activity(uid, family)
        finally:
            session_repository.touch_session = original

    def test_is_activity_path_rules(self):
        self.assertTrue(activity_service.is_activity_path("/plans"))
        self.assertTrue(activity_service.is_activity_path("/tasks/1/complete"))
        self.assertFalse(activity_service.is_activity_path("/auth/refresh"))
        self.assertFalse(
            activity_service.is_activity_path("/tasks/today/unchecked-count")
        )


# ======================================================================
# 第 12 节：原业务回归
# ======================================================================


class TestBusinessRegression(BaseAuthTest):
    def test_business_today_is_utc8(self):
        now_bj = datetime.now(timezone(timedelta(hours=8)))
        self.assertEqual(business_today(), now_bj.date())

    def test_protected_endpoints_use_new_auth(self):
        uid, username, _ = self.make_user("b1")
        pair, _ = self.login(username)
        client = self.new_client()
        headers = {"Authorization": f"Bearer {pair['access_token']}"}

        for path in ("/users/me", "/plans", "/tasks/today"):
            resp = client.get(path, headers=headers)
            self.assertEqual(resp.status_code, 200, f"{path} -> {resp.text}")

    def test_anonymous_access_denied(self):
        client = self.new_client()
        for path in ("/plans", "/tasks/today", "/users/me"):
            resp = client.get(path)
            self.assertEqual(resp.status_code, 401, f"{path} -> {resp.text}")

    def test_ownership_enforced_on_profile(self):
        uid_a, username_a, _ = self.make_user("b2")
        uid_b, username_b, _ = self.make_user("b3")
        pair_a, _ = self.login(username_a)

        client = self.new_client()
        resp = client.get(
            f"/users/{uid_b}",
            headers={"Authorization": f"Bearer {pair_a['access_token']}"},
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_nickname_update(self):
        uid, username, _ = self.make_user("b4")
        pair, _ = self.login(username)
        client = self.new_client()
        headers = {"Authorization": f"Bearer {pair['access_token']}"}

        resp = client.put(
            f"/users/{uid}", json={"nickname": "新昵称"}, headers=headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        me = client.get("/users/me", headers=headers)
        self.assertEqual(me.json()["data"]["nickname"], "新昵称")

    def test_ai_guard_tables_untouched(self):
        before = self.count("SELECT COUNT(*) FROM ai_guard_mutex")
        uid, username, _ = self.make_user("b5")
        self.login(username)
        after = self.count("SELECT COUNT(*) FROM ai_guard_mutex")
        self.assertEqual(before, after)

    def test_plans_isolated_per_user(self):
        uid_a, username_a, _ = self.make_user("b6")
        uid_b, username_b, _ = self.make_user("b7")
        pair_a, _ = self.login(username_a)
        pair_b, _ = self.login(username_b)

        client = self.new_client()
        ra = client.get(
            "/plans", headers={"Authorization": f"Bearer {pair_a['access_token']}"}
        )
        rb = client.get(
            "/plans", headers={"Authorization": f"Bearer {pair_b['access_token']}"}
        )
        self.assertEqual(ra.status_code, 200)
        self.assertEqual(rb.status_code, 200)
        for plan in ra.json()["data"]:
            self.assertEqual(plan["user_id"], uid_a)


# ======================================================================
# 第 13 节：敏感信息保护 / 参数校验
# ======================================================================


class TestSensitiveData(BaseAuthTest):
    def test_validation_error_hides_password(self):
        client = self.new_client()
        secret = "SuperSecretPass!9"
        resp = client.post(
            "/users",
            json={
                "username": "ab",
                "password": secret[:4],
                "email": "not-an-email",
                "code": "12",
            },
            headers=CSRF,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertNotIn(secret[:4], resp.text)
        body = resp.json()
        self.assertEqual(body["code"], 422)
        self.assertIsInstance(body["data"], list)
        for item in body["data"]:
            self.assertIn("loc", item)
            self.assertIn("type", item)
            self.assertEqual(item["msg"], "Invalid input")

    def test_validation_error_hides_code(self):
        client = self.new_client()
        resp = client.post(
            "/auth/email-code",
            json={"email": f"{self.PREFIX}x@example.com", "purpose": "REGISTER", "code": "999999"},
            headers=CSRF,
        )
        # 多余字段被忽略或校验失败，都不应回显验证码
        self.assertNotIn("999999", resp.text)

    def test_login_error_generic(self):
        client = self.new_client()
        resp = client.post(
            "/auth/login",
            data={"username": f"{self.PREFIX}ghost2", "password": "WrongPass999"},
            headers=CSRF,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("ghost2", resp.text)

    def test_error_response_has_message(self):
        client = self.new_client()
        resp = client.get("/users/me")
        body = resp.json()
        self.assertIn("detail", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)