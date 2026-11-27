"""V3.0 A1 管理员认证验收测试。

约束：
- 仅运行于隔离测试库（默认 ssp_v3_admin_test，兼容 ssp_a0_migrate2）。
- 管理接口在测试内用独立 FastAPI 实例挂载，不新增生产路由。
- 登录态相关用例需要真实提交，tearDownClass 按前缀精确清理。
- 不输出密钥、Token、密码、验证码。
"""

import uuid
import unittest
from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.config import settings
from app.core import security
from app.core.clock import utc_db_now
from app.core.deps import require_admin
from app.database import SessionLocal, engine
from app.main import app as production_app
from app.repositories.auth import user_repository
from app.response import success
from app.schemas.auth import EmailCodePurpose

# ============================================================
# 隔离库守卫
# ============================================================

ALLOWED_TEST_DBS = {"ssp_v3_admin_test", "ssp_a0_migrate2"}


def _guard_database() -> str:
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if db_name not in ALLOWED_TEST_DBS:
        raise RuntimeError(
            f"测试仅允许在隔离测试库执行，当前数据库: {db_name}"
        )
    return db_name


CURRENT_DB = _guard_database()

# ============================================================
# 测试专用管理路由（不进入生产 api_router）
# ============================================================


def _build_admin_test_app() -> FastAPI:
    test_app = FastAPI()

    # 复用生产应用的统一异常响应格式
    for exc_type, handler in production_app.exception_handlers.items():
        test_app.add_exception_handler(exc_type, handler)

    @test_app.get("/__test__/admin/ping")
    def admin_ping(user: dict = Depends(require_admin)):
        return success(
            data={
                "user_id": user["id"],
                "role": user["role"],
            }
        )

    return test_app


admin_app = _build_admin_test_app()

ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {
    "Origin": ORIGIN,
    "X-CSRF-Protection": "1",
}
PASSWORD = "AdminPass123"


def _in_clause(sql: str, key: str = "ids"):
    return text(sql).bindparams(bindparam(key, expanding=True))


# ============================================================
# 基类：用户构造 / 登录 / DB 操作 / 清理
# ============================================================


class BaseAdminTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.PREFIX = f"a1adm{uuid.uuid4().hex[:8]}"
        cls.START = utc_db_now()
        cls.client = TestClient(
            production_app,
            base_url="https://ssp.test",
            client=("127.0.0.1", 51990),
            raise_server_exceptions=False,
        )
        cls.admin_client = TestClient(
            admin_app,
            base_url="https://ssp.test",
            client=("127.0.0.1", 51991),
            raise_server_exceptions=False,
        )
        cls._ip_pwd_limit = settings.PASSWORD_IP_MAX_ATTEMPTS
        cls._ip_mail_limit = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
        settings.PASSWORD_IP_MAX_ATTEMPTS = 100000
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 100000

    @classmethod
    def tearDownClass(cls):
        settings.PASSWORD_IP_MAX_ATTEMPTS = cls._ip_pwd_limit
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = cls._ip_mail_limit
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
                        "DELETE FROM refresh_tokens WHERE user_id IN :ids"
                    ),
                    params,
                )
                conn.execute(
                    _in_clause(
                        "DELETE FROM login_sessions WHERE user_id IN :ids"
                    ),
                    params,
                )
                conn.execute(
                    _in_clause(
                        "DELETE FROM auth_events WHERE user_id IN :ids"
                    ),
                    params,
                )
                conn.execute(
                    _in_clause(
                        "DELETE FROM email_verifications "
                        "WHERE user_id IN :ids"
                    ),
                    params,
                )
                conn.execute(
                    _in_clause(
                        "DELETE FROM users WHERE id IN :ids"
                    ),
                    params,
                )

            conn.execute(
                text(
                    "DELETE FROM email_verifications "
                    "WHERE email LIKE :p"
                ),
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

    # ---------- 构造 ----------

    def make_user(self, suffix: str, *, role: str = "USER"):
        """直接落库创建用户，返回 (user_id, username, email)。"""

        username = f"{self.PREFIX}{suffix}{uuid.uuid4().hex[:4]}"
        email = f"{username}@example.com"

        with SessionLocal() as db:
            user_id = user_repository.insert_user(
                db,
                username=username,
                email=email,
                password_hash=security.hash_password(PASSWORD),
                nickname=username,
                now=utc_db_now(),
            )
            if role != "USER":
                db.execute(
                    text(
                        "UPDATE users SET role = :r WHERE id = :i"
                    ),
                    {"r": role, "i": user_id},
                )
            db.commit()

        return user_id, username, email

    def mk_register_code(self, email: str, code: str = "123456") -> None:
        purpose = EmailCodePurpose.REGISTER.value
        now = utc_db_now()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO email_verifications (
                        email, purpose, user_id, family_id,
                        code_hash, attempts, created_at, expires_at,
                        consumed_at, invalidated_at, request_ip, send_status
                    ) VALUES (
                        :email, :purpose, NULL, NULL,
                        :code_hash, 0, :now, :expires_at,
                        NULL, NULL, :ip, 'SENT'
                    )
                    """
                ),
                {
                    "email": email,
                    "purpose": purpose,
                    "code_hash": security.hash_email_code(
                        email, purpose, code
                    ),
                    "now": now,
                    "expires_at": now + timedelta(seconds=300),
                    "ip": "127.0.0.1",
                },
            )

    def login(self, username: str):
        """表单登录，返回 (access_token, user_payload)。"""

        response = self.client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        return data["access_token"], data["user"]

    def auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def ping(self, token: str | None = None):
        headers = self.auth(token) if token else {}
        return self.admin_client.get(
            "/__test__/admin/ping",
            headers=headers,
        )

    # ---------- DB ----------

    def read_role(self, user_id: int) -> str:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT role FROM users WHERE id = :i"),
                {"i": user_id},
            ).scalar_one()

    def db_exec(self, sql: str, **params) -> None:
        with engine.begin() as conn:
            conn.execute(text(sql), params)

    def family_id_of(self, access_token: str) -> str:
        payload = security.decode_access_token(access_token)
        self.assertIsNotNone(payload)
        return payload["family_id"]


# ============================================================
# T1 管理路由访问控制
# ============================================================


class TestAdminRouteAccess(BaseAdminTest):

    def test_t1_01_anonymous_rejected_401(self):
        """未登录访问管理接口返回 401"""
        response = self.ping()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"],
            "INVALID_TOKEN",
        )

    def test_t1_02_normal_user_403_admin_required(self):
        """普通用户访问管理接口返回 403 ADMIN_REQUIRED"""
        _, username, _ = self.make_user("normal")
        token, user = self.login(username)
        self.assertEqual(user["role"], "USER")

        response = self.ping(token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ADMIN_REQUIRED",
        )

    def test_t1_03_admin_allowed_200(self):
        """管理员访问管理接口返回 200"""
        user_id, username, _ = self.make_user("admin", role="ADMIN")
        token, user = self.login(username)
        self.assertEqual(user["role"], "ADMIN")

        response = self.ping(token)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["user_id"], user_id)
        self.assertEqual(data["role"], "ADMIN")


# ============================================================
# T2 管理员会话失效
# ============================================================


class TestAdminSessionInvalidation(BaseAdminTest):

    def test_t2_01_disabled_admin_rejected(self):
        """禁用管理员账号后拒绝访问"""
        user_id, username, _ = self.make_user("disabled", role="ADMIN")
        token, _ = self.login(username)
        self.assertEqual(self.ping(token).status_code, 200)

        self.db_exec(
            "UPDATE users SET is_active = 0 WHERE id = :i",
            i=user_id,
        )

        response = self.ping(token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ACCOUNT_DISABLED",
        )

    def test_t2_02_revoked_session_rejected(self):
        """撤销管理员登录会话后拒绝访问"""
        _, username, _ = self.make_user("revoked", role="ADMIN")
        token, _ = self.login(username)
        self.assertEqual(self.ping(token).status_code, 200)

        self.db_exec(
            """
            UPDATE login_sessions
            SET revoked_at = :now, revoked_reason = 'TEST_REVOKE'
            WHERE family_id = :f AND revoked_at IS NULL
            """,
            now=utc_db_now(),
            f=self.family_id_of(token),
        )

        response = self.ping(token)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"],
            "SESSION_REVOKED",
        )


# ============================================================
# T3 角色变更即时生效（Token 不重签）
# ============================================================


class TestRoleChangeTakesEffect(BaseAdminTest):

    def test_t3_01_promote_user_token_gains_admin(self):
        """USER 提升为 ADMIN 后原 Token 获得管理权限"""
        user_id, username, _ = self.make_user("promote")
        token, _ = self.login(username)

        self.assertEqual(self.ping(token).status_code, 403)

        self.db_exec(
            "UPDATE users SET role = 'ADMIN' WHERE id = :i",
            i=user_id,
        )

        response = self.ping(token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["role"], "ADMIN")
        self.assertEqual(self.read_role(user_id), "ADMIN")

    def test_t3_02_demote_admin_token_loses_admin(self):
        """ADMIN 降级为 USER 后原 Token 立即失去管理权限"""
        user_id, username, _ = self.make_user("demote", role="ADMIN")
        token, _ = self.login(username)

        self.assertEqual(self.ping(token).status_code, 200)

        self.db_exec(
            "UPDATE users SET role = 'USER' WHERE id = :i",
            i=user_id,
        )

        response = self.ping(token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ADMIN_REQUIRED",
        )
        self.assertEqual(self.read_role(user_id), "USER")


# ============================================================
# T4 越权注入防护
# ============================================================


class TestRoleInjectionRejected(BaseAdminTest):

    def test_t4_01_register_with_admin_role_cannot_escalate(self):
        """注册时注入 role=ADMIN 无法提权"""
        username = f"{self.PREFIX}inj{uuid.uuid4().hex[:6]}"
        email = f"{username}@example.com"
        self.mk_register_code(email)

        response = self.client.post(
            "/users",
            json={
                "username": username,
                "password": PASSWORD,
                "email": email,
                "code": "123456",
                "nickname": username,
                "role": "ADMIN",
            },
            headers=CSRF_HEADERS,
        )
        self.assertEqual(response.status_code, 201, response.text)

        data = response.json()["data"]
        self.assertEqual(data["user"]["role"], "USER")

        with engine.connect() as conn:
            user_id = conn.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": username},
            ).scalar_one()
        self.assertEqual(self.read_role(user_id), "USER")

        # 注册即登录，返回的 Token 不具备管理权限
        response = self.ping(data["access_token"])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"],
            "ADMIN_REQUIRED",
        )

    def test_t4_02_profile_update_with_admin_role_cannot_escalate(self):
        """修改资料时注入 role=ADMIN 无法提权"""
        user_id, username, _ = self.make_user("upd")
        token, _ = self.login(username)

        new_nickname = f"nick{uuid.uuid4().hex[:6]}"
        response = self.client.put(
            f"/users/{user_id}",
            json={"nickname": new_nickname, "role": "ADMIN"},
            headers=self.auth(token),
        )
        self.assertEqual(response.status_code, 200, response.text)

        self.assertEqual(self.read_role(user_id), "USER")

        me = self.client.get(
            "/users/me",
            headers=self.auth(token),
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["role"], "USER")
        self.assertEqual(me.json()["data"]["nickname"], new_nickname)

        self.assertEqual(self.ping(token).status_code, 403)


# ============================================================
# T5 UserPublic 响应中的 role
# ============================================================


class TestUserPublicRole(BaseAdminTest):

    def test_t5_01_register_login_profile_include_role(self):
        """注册、登录、个人资料响应均正确返回 role"""
        username = f"{self.PREFIX}pub{uuid.uuid4().hex[:6]}"
        email = f"{username}@example.com"
        self.mk_register_code(email)

        # 注册
        register = self.client.post(
            "/users",
            json={
                "username": username,
                "password": PASSWORD,
                "email": email,
                "code": "123456",
                "nickname": username,
            },
            headers=CSRF_HEADERS,
        )
        self.assertEqual(register.status_code, 201, register.text)
        register_user = register.json()["data"]["user"]
        self.assertIn("role", register_user)
        self.assertEqual(register_user["role"], "USER")

        # 登录
        token, login_user = self.login(username)
        self.assertIn("role", login_user)
        self.assertEqual(login_user["role"], "USER")

        # /users/me
        me = self.client.get("/users/me", headers=self.auth(token))
        self.assertEqual(me.status_code, 200)
        self.assertIn("role", me.json()["data"])
        self.assertEqual(me.json()["data"]["role"], "USER")

        # /users/{id}
        profile = self.client.get(
            f"/users/{register_user['id']}",
            headers=self.auth(token),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertIn("role", profile.json()["data"])
        self.assertEqual(profile.json()["data"]["role"], "USER")

    def test_t5_02_admin_role_exposed_in_profile(self):
        """管理员个人资料返回 role=ADMIN"""
        user_id, username, _ = self.make_user("pubadmin", role="ADMIN")
        token, login_user = self.login(username)

        self.assertEqual(login_user["role"], "ADMIN")

        me = self.client.get("/users/me", headers=self.auth(token))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["role"], "ADMIN")

        profile = self.client.get(
            f"/users/{user_id}",
            headers=self.auth(token),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["data"]["role"], "ADMIN")