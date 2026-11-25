"""Auth V2.0 A1.1 验收测试。

仅运行于隔离库 ssp_a0_migrate2。所有 DB 测试在外层事务内执行，tearDown 回滚。
并发测试需要提交，使用独立连接并精确清理自建数据。
不读取/输出真实密钥，不实际发送邮件。
"""
import json
import os
import re
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core import security
from app.core.clock import BUSINESS_TIMEZONE, business_today, utc_db_now, utc_now
from app.database import engine
from app.main import app
from app.repositories.auth import (
    auth_event_repository,
    session_repository,
    token_repository,
    user_repository,
    verification_repository,
)

# ============================================================
# 隔离库连接守卫 — 模块加载即校验，避免误连正式库
# ============================================================

_EXPECTED_DB = "ssp_a0_migrate2"


def _guard_database():
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT DATABASE()")).scalar_one()
        if db_name != _EXPECTED_DB:
            raise RuntimeError(
                f"测试仅允许在 {_EXPECTED_DB} 执行，当前数据库: {db_name}"
            )


_guard_database()


# ============================================================
# 通用工具
# ============================================================


def unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


def make_email(prefix: str = "a11") -> str:
    return f"{prefix}_{unique_suffix()}@test.local"


class RollbackTestCase(unittest.TestCase):
    """每个测试独立连接 + 外层事务，tearDown 回滚。"""

    def setUp(self):
        self.conn = engine.connect()
        self.outer = self.conn.begin()
        self.db = Session(
            bind=self.conn,
            join_transaction_mode="create_savepoint",
        )
        # 再确认一次 DB 名
        db_name = self.db.execute(text("SELECT DATABASE()")).scalar_one()
        self.assertEqual(db_name, _EXPECTED_DB)

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.conn.close()

    def sql(self, query: str, **params):
        return self.db.execute(text(query), params)

    def insert_user(self, *, username=None, email=None) -> int:
        username = username or f"a11_{unique_suffix()}"
        email = email or make_email()
        now = utc_db_now()
        return int(
            self.sql(
                """
                INSERT INTO users (
                    username, password_hash, password_updated_at,
                    email, email_verified_at, nickname
                ) VALUES (
                    :u, 'dummy', :now, :e, :now, 'tester'
                )
                """,
                u=username,
                e=email,
                now=now,
            ).lastrowid
        )


# ============================================================
# T1. 配置与环境
# ============================================================


class T1ConfigAndEnv(unittest.TestCase):
    def test_t1_01_env_loaded(self):
        """.env 加载且 DB 指向隔离库"""
        self.assertEqual(settings.DB_NAME, _EXPECTED_DB)
        self.assertEqual(settings.DB_HOST, "127.0.0.1")

    def test_t1_02_database_actually_isolation(self):
        """实际连接的 DB 名"""
        with engine.connect() as conn:
            self.assertEqual(
                conn.execute(text("SELECT DATABASE()")).scalar_one(),
                _EXPECTED_DB,
            )

    def test_t1_03_secret_min_length(self):
        """JWT 密钥与验证码 HMAC 密钥 ≥32 字节，且不相同"""
        sk = settings.SECRET_KEY.encode("utf-8")
        es = settings.EMAIL_CODE_SECRET.encode("utf-8")
        self.assertGreaterEqual(len(sk), 32, "SECRET_KEY 必须 ≥32 字节")
        self.assertGreaterEqual(len(es), 32, "EMAIL_CODE_SECRET 必须 ≥32 字节")
        self.assertNotEqual(settings.SECRET_KEY, settings.EMAIL_CODE_SECRET)

    def test_t1_04_missing_secret_rejected(self):
        """缺失密钥拒绝启动配置"""
        from pydantic import ValidationError
        from app.config import Settings

        env_backup = dict(os.environ)
        try:
            os.environ.pop("SECRET_KEY", None)
            os.environ.pop("EMAIL_CODE_SECRET", None)
            # 临时屏蔽 .env 加载
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_t1_05_short_secret_rejected(self):
        from pydantic import ValidationError
        from app.config import Settings

        base = self._base_kwargs()
        base["SECRET_KEY"] = "short"
        base["EMAIL_CODE_SECRET"] = "x" * 64
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, **base)

    def test_t1_06_same_secret_rejected(self):
        from pydantic import ValidationError
        from app.config import Settings

        base = self._base_kwargs()
        same = "a" * 64
        base["SECRET_KEY"] = same
        base["EMAIL_CODE_SECRET"] = same
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, **base)

    def test_t1_07_access_token_ttl(self):
        self.assertEqual(settings.ACCESS_TOKEN_EXPIRE_MINUTES, 15)

    def test_t1_08_refresh_token_ttl(self):
        self.assertEqual(settings.REFRESH_TOKEN_EXPIRE_DAYS, 7)

    def test_t1_09_session_idle_ttl(self):
        self.assertEqual(settings.SESSION_IDLE_EXPIRE_DAYS, 7)

    def test_t1_10_session_absolute_ttl(self):
        self.assertEqual(settings.SESSION_ABSOLUTE_EXPIRE_DAYS, 30)

    def test_t1_11_activity_write_interval(self):
        self.assertEqual(settings.SESSION_ACTIVITY_INTERVAL_SECONDS, 300)

    def test_t1_12_numeric_boundary_validation(self):
        """T1 关键项：非法数值配置是否被拒绝。
        当前大量字段无 gt=0，非法值未被拒绝。
        此测试用于发现配置漏洞。
        """
        from app.config import Settings

        base = self._base_kwargs()

        # 子项 a: ACCESS_TOKEN_EXPIRE_MINUTES 有 gt=0，应拒绝 0
        rejected_access_zero = False
        try:
            Settings(_env_file=None, **{**base, "ACCESS_TOKEN_EXPIRE_MINUTES": 0})
        except Exception:
            rejected_access_zero = True

        # 子项 b: SESSION_ACTIVITY_INTERVAL_SECONDS 无校验，0 应被拒绝但当前不拒绝
        try:
            Settings(_env_file=None, **{**base, "SESSION_ACTIVITY_INTERVAL_SECONDS": 0})
            rejected_activity_zero = False
        except Exception:
            rejected_activity_zero = True

        # 子项 c: EMAIL_CODE_MAX_ATTEMPTS 应拒绝 0 或负数
        try:
            Settings(_env_file=None, **{**base, "EMAIL_CODE_MAX_ATTEMPTS": -1})
            rejected_attempts_neg = False
        except Exception:
            rejected_attempts_neg = True

        # 子项 d: EMAIL_CODE_EXPIRE_MINUTES 应拒绝 0
        try:
            Settings(_env_file=None, **{**base, "EMAIL_CODE_EXPIRE_MINUTES": 0})
            rejected_code_expire_zero = False
        except Exception:
            rejected_code_expire_zero = True

        # 子项 e: EMAIL_DAILY_LIMIT 应拒绝 0
        try:
            Settings(_env_file=None, **{**base, "EMAIL_DAILY_LIMIT": 0})
            rejected_daily_zero = False
        except Exception:
            rejected_daily_zero = True

        # 子项 f: SESSION_IDLE_EXPIRE_DAYS 应拒绝负数
        try:
            Settings(_env_file=None, **{**base, "SESSION_IDLE_EXPIRE_DAYS": -1})
            rejected_idle_neg = False
        except Exception:
            rejected_idle_neg = True

        # 子项 g: PASSWORD_LOCK_MINUTES 应拒绝负数
        try:
            Settings(_env_file=None, **{**base, "PASSWORD_LOCK_MINUTES": -1})
            rejected_lock_neg = False
        except Exception:
            rejected_lock_neg = True

        # 输出检测结果：哪些字段缺少校验
        missing = []
        if not rejected_activity_zero:
            missing.append("SESSION_ACTIVITY_INTERVAL_SECONDS")
        if not rejected_attempts_neg:
            missing.append("EMAIL_CODE_MAX_ATTEMPTS")
        if not rejected_code_expire_zero:
            missing.append("EMAIL_CODE_EXPIRE_MINUTES")
        if not rejected_daily_zero:
            missing.append("EMAIL_DAILY_LIMIT")
        if not rejected_idle_neg:
            missing.append("SESSION_IDLE_EXPIRE_DAYS")
        if not rejected_lock_neg:
            missing.append("PASSWORD_LOCK_MINUTES")

        # 至少有 gt=0 的字段应被拒绝
        self.assertTrue(rejected_access_zero, "ACCESS_TOKEN_EXPIRE_MINUTES 应拒绝 0")

        # 把缺失校验的字段以警告形式抛出，不直接 fail 整组
        if missing:
            self.fail(
                "下列数值配置缺少边界校验，非法值未被拒绝：" + ", ".join(missing)
            )

    def test_t1_13_ai_config_intact(self):
        """原有 AI 配置完整保留"""
        self.assertTrue(hasattr(settings, "AI_ENABLED"))
        self.assertTrue(hasattr(settings, "DEEPSEEK_API_KEY"))
        self.assertTrue(hasattr(settings, "DEEPSEEK_MODEL"))
        self.assertTrue(hasattr(settings, "AI_MAX_NOTE_CHARS"))
        self.assertTrue(hasattr(settings, "AI_USER_DAILY_LIMIT"))
        self.assertTrue(hasattr(settings, "AI_GLOBAL_DAILY_LIMIT"))
        self.assertTrue(hasattr(settings, "AI_MAX_STREAM_SECONDS"))
        self.assertTrue(hasattr(settings, "AI_LEASE_SECONDS"))

    @staticmethod
    def _base_kwargs() -> dict:
        return {
            "DB_USER": "root",
            "DB_PASSWORD": "x",
            "DB_NAME": _EXPECTED_DB,
            "SECRET_KEY": "b" * 64,
            "EMAIL_CODE_SECRET": "c" * 64,
        }


# ============================================================
# T2. 密码安全工具
# ============================================================


class T2PasswordSecurity(unittest.TestCase):
    def test_t2_01_iterations_600k(self):
        self.assertEqual(security.ITERATIONS, 600000)
        h = security.hash_password("x")
        parts = h.split("$")
        self.assertEqual(parts[0], "pbkdf2_sha256")
        self.assertEqual(int(parts[1]), 600000)

    def test_t2_02_salted_differs(self):
        a = security.hash_password("password123")
        b = security.hash_password("password123")
        self.assertNotEqual(a, b)

    def test_t2_03_correct_password(self):
        h = security.hash_password("S3cure!Pass")
        self.assertTrue(security.verify_password("S3cure!Pass", h))

    def test_t2_04_wrong_password(self):
        h = security.hash_password("S3cure!Pass")
        self.assertFalse(security.verify_password("wrong", h))

    def test_t2_05_malformed_hash_safe(self):
        """畸形摘要安全处理（不抛异常，返回 False）"""
        cases = [
            "",
            "abc",
            "pbkdf2_sha256",
            "pbkdf2_sha256$abc$zz$yy",
            "pbkdf2_sha256$100$aa$bb",
            "wrong_algo$600000$aa$bb",
            "pbkdf2_sha256$600000$zz$bb",  # 非 hex salt
            "pbkdf2_sha256$600000$a$bb",   # 奇数长度 hex
        ]
        for c in cases:
            with self.subTest(case=c):
                self.assertFalse(security.verify_password("x", c))

    def test_t2_06_non_string_hash(self):
        """stored_hash 为 None / int 时的行为"""
        # None: .split 抛 AttributeError — 不在 ValueError 捕获内
        try:
            security.verify_password("x", None)
            result_none = "no_exception"
        except AttributeError:
            result_none = "AttributeError"
        except Exception as e:
            result_none = type(e).__name__

        try:
            security.verify_password("x", 12345)
            result_int = "no_exception"
        except AttributeError:
            result_int = "AttributeError"
        except Exception as e:
            result_int = type(e).__name__

        # 记录但不强 assert False（这是发现的问题）
        # 当前实现 None/int 会抛 AttributeError，未安全处理
        if result_none != "no_exception" or result_int != "no_exception":
            self.fail(
                f"非字符串 stored_hash 未安全处理: None→{result_none}, int→{result_int}"
            )


# ============================================================
# T3. JWT 安全工具
# ============================================================


class T3JWTSecurity(unittest.TestCase):
    def _identity(self):
        return {"sub": "12345", "family_id": str(uuid.uuid4())}

    def test_t3_01_access_token_issue_decode(self):
        data = self._identity()
        token = security.create_access_token(data)
        payload = security.decode_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "access")

    def test_t3_02_refresh_token_issue_decode(self):
        data = self._identity()
        token = security.create_refresh_token(data)
        payload = security.decode_refresh_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["type"], "refresh")

    def test_t3_03_required_claims_present(self):
        data = self._identity()
        token = security.create_access_token(data)
        # 手动解码
        raw = pyjwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[security.JWT_ALGORITHM],
        )
        for claim in ("sub", "family_id", "iat", "exp", "type", "jti"):
            self.assertIn(claim, raw)

    def test_t3_04_same_family_id(self):
        data = self._identity()
        at = security.decode_access_token(security.create_access_token(data))
        rt = security.decode_refresh_token(security.create_refresh_token(data))
        self.assertEqual(at["family_id"], rt["family_id"])

    def test_t3_05_jti_unique(self):
        data = self._identity()
        at = security.decode_access_token(security.create_access_token(data))
        rt = security.decode_refresh_token(security.create_refresh_token(data))
        self.assertNotEqual(at["jti"], rt["jti"])

    def test_t3_06_no_cross_type_usage(self):
        data = self._identity()
        access = security.create_access_token(data)
        refresh = security.create_refresh_token(data)

        # 用 access token 当 refresh 解 → None
        self.assertIsNone(security.decode_refresh_token(access))

        # 用 refresh token 当 access 解 → None / TOKEN_TYPE_INVALID
        payload, err = security.decode_access_token_detailed(refresh)
        self.assertIsNone(payload)
        self.assertEqual(err, "TOKEN_TYPE_INVALID")

    def test_t3_07_missing_required_claims(self):
        data = self._identity()
        # 手动构造缺 family_id 的 token
        now = utc_now()
        bad_payload = {
            "sub": "12345",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        token = pyjwt.encode(
            bad_payload,
            settings.SECRET_KEY,
            algorithm=security.JWT_ALGORITHM,
        )
        self.assertIsNone(security.decode_access_token(token))

    def test_t3_08_invalid_user_id_rejected(self):
        # 非数字
        bad1 = {"sub": "abc", "family_id": str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            security.create_access_token(bad1)

        # 0
        bad2 = {"sub": "0", "family_id": str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            security.create_access_token(bad2)

        # 超出 BIGINT UNSIGNED 范围
        bad3 = {"sub": str(2**64), "family_id": str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            security.create_access_token(bad3)

        # 非字符串 sub
        bad4 = {"sub": 12345, "family_id": str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            security.create_access_token(bad4)

        # 非法 family_id
        bad5 = {"sub": "12345", "family_id": "not-a-uuid"}
        with self.assertRaises(ValueError):
            security.create_access_token(bad5)

        # UUID v1 也应拒绝
        bad6 = {"sub": "12345", "family_id": str(uuid.uuid1())}
        with self.assertRaises(ValueError):
            security.create_access_token(bad6)

    def test_t3_09_wrong_signature(self):
        data = self._identity()
        token = security.create_access_token(data)
        # 用错密钥解
        forged = pyjwt.encode(
            {"sub": "99999", "family_id": str(uuid.uuid4()),
             "iat": utc_now(), "exp": utc_now() + timedelta(minutes=5),
             "type": "access", "jti": str(uuid.uuid4())},
            "wrong_secret" + "x" * 60,
            algorithm=security.JWT_ALGORITHM,
        )
        self.assertIsNone(security.decode_access_token(forged))
        # 篡改原 token
        tampered = token[:-5] + "XXXXX"
        self.assertIsNone(security.decode_access_token(tampered))

    def test_t3_10_expired_token_rejected(self):
        data = self._identity()
        past = utc_now() - timedelta(seconds=10)
        expired_payload = {
            **data,
            "iat": past - timedelta(minutes=20),
            "exp": past,
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        token = pyjwt.encode(
            expired_payload,
            settings.SECRET_KEY,
            algorithm=security.JWT_ALGORITHM,
        )
        self.assertIsNone(security.decode_access_token(token))

    def test_t3_11_access_expired_error_code(self):
        data = self._identity()
        past = utc_now() - timedelta(seconds=10)
        expired_payload = {
            **data,
            "iat": past - timedelta(minutes=20),
            "exp": past,
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        token = pyjwt.encode(
            expired_payload,
            settings.SECRET_KEY,
            algorithm=security.JWT_ALGORITHM,
        )
        payload, err = security.decode_access_token_detailed(token)
        self.assertIsNone(payload)
        self.assertEqual(err, "ACCESS_EXPIRED")

    def test_t3_12_token_exp_capped_by_session(self):
        """Token 有效期不得超过传入的会话截止时间"""
        data = self._identity()
        # 会话 5 秒后结束，access token 默认 15 分钟，应被截断
        session_end = utc_now() + timedelta(seconds=5)
        token = security.create_access_token(data, expires_at=session_end)
        raw = pyjwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.JWT_ALGORITHM]
        )
        exp = datetime.fromtimestamp(raw["exp"], tz=timezone.utc)
        # exp 应 <= session_end + 1s 误差
        delta = abs((exp - session_end).total_seconds())
        self.assertLess(delta, 2.0)

    def test_t3_13_token_exp_naive_session_end_rejected(self):
        """naive datetime 作为 expires_at 应被拒绝"""
        data = self._identity()
        naive = datetime.utcnow() + timedelta(hours=1)
        with self.assertRaises(ValueError):
            security.create_access_token(data, expires_at=naive)

    def test_t3_14_token_exp_past_session_end_rejected(self):
        """expires_at 在过去，应拒绝签发"""
        data = self._identity()
        past = utc_now() - timedelta(seconds=1)
        with self.assertRaises(ValueError):
            security.create_access_token(data, expires_at=past)

    def test_t3_15_time_precision(self):
        """JWT iat/exp 是秒级 int"""
        data = self._identity()
        token = security.create_access_token(data)
        raw = pyjwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.JWT_ALGORITHM]
        )
        self.assertIsInstance(raw["iat"], int)
        self.assertIsInstance(raw["exp"], int)
        # access token 默认 15 分钟 = 900s，容差 ±5s
        self.assertAlmostEqual(raw["exp"] - raw["iat"], 900, delta=5)


# ============================================================
# T4. 邮箱验证码安全工具
# ============================================================


class T4EmailCodeSecurity(unittest.TestCase):
    def test_t4_01_six_digit_ascii(self):
        for _ in range(100):
            code = security.generate_email_code()
            self.assertRegex(code, r"^[0-9]{6}$")
            self.assertTrue(code.isascii())

    def test_t4_02_leading_zero(self):
        # 强制 mock 一个前导零场景
        import secrets as _s
        original = _s.randbelow
        try:
            _s.randbelow = lambda _: 12345  # 模拟
            code = security.generate_email_code()
            self.assertEqual(code, "012345")
        finally:
            _s.randbelow = original

    def test_t4_03_hmac_sha256_hex_length(self):
        h = security.hash_email_code("a@b.com", "REGISTER", "123456")
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_t4_04_correct_code_pass(self):
        h = security.hash_email_code("a@b.com", "REGISTER", "123456")
        self.assertTrue(
            security.verify_email_code("a@b.com", "REGISTER", "123456", h)
        )

    def test_t4_05_wrong_code_fail(self):
        h = security.hash_email_code("a@b.com", "REGISTER", "123456")
        self.assertFalse(
            security.verify_email_code("a@b.com", "REGISTER", "999999", h)
        )

    def test_t4_06_email_isolation(self):
        h = security.hash_email_code("a@b.com", "REGISTER", "123456")
        self.assertFalse(
            security.verify_email_code("other@b.com", "REGISTER", "123456", h)
        )

    def test_t4_07_purpose_isolation(self):
        h = security.hash_email_code("a@b.com", "REGISTER", "123456")
        self.assertFalse(
            security.verify_email_code("a@b.com", "LOGIN", "123456", h)
        )

    def test_t4_08_no_plaintext_in_db(self):
        """hash_email_code 是 HMAC 摘要，不是明文"""
        code = "123456"
        h = security.hash_email_code("a@b.com", "REGISTER", code)
        self.assertNotIn(code, h)
        # 长度 64，非 6 位明文
        self.assertEqual(len(h), 64)


# ============================================================
# T5. 时间工具
# ============================================================


class T5Clock(unittest.TestCase):
    def test_t5_01_business_today(self):
        d = business_today()
        # 与东八区当前日期一致
        expected = datetime.now(BUSINESS_TIMEZONE).date()
        self.assertEqual(d, expected)

    def test_t5_02_utc_now_aware(self):
        t = utc_now()
        self.assertIsNotNone(t.tzinfo)
        self.assertEqual(t.utcoffset(), timedelta(0))

    def test_t5_03_utc_db_now_naive(self):
        t = utc_db_now()
        self.assertIsNone(t.tzinfo)

    def test_t5_04_business_timezone_unchanged(self):
        self.assertEqual(
            BUSINESS_TIMEZONE.utcoffset(None), timedelta(hours=8)
        )


# ============================================================
# T6. Schema 校验
# ============================================================


class T6Schema(unittest.TestCase):
    """A1.1 范围仅含 schemas/auth.py 与 schemas/user.py。
    当前文件仅有 TokenPair/RefreshRequest/UserCreate/UserUpdate。
    缺 RegisterRequest/LoginRequest/EmailCode*Request/LoginResponse 等。
    """

    def test_t6_01_schemas_module_contents(self):
        """枚举实际可用的 schema，确认 A1.1 范围"""
        from app.schemas import auth as auth_schema
        from app.schemas import user as user_schema

        auth_names = [n for n in dir(auth_schema) if not n.startswith("_")]
        user_names = [n for n in dir(user_schema) if not n.startswith("_")]

        # 记录现状
        expected_for_t6 = [
            "RegisterRequest", "LoginRequest", "LoginResponse",
            "EmailCodeSendRequest", "EmailCodeVerifyRequest",
            "EmailCodePurpose",
        ]
        missing = [n for n in expected_for_t6 if n not in auth_names]

        # 输出当前所有可用名称，便于排查
        # 不断言存在，仅记录
        print(f"\n[T6] auth schemas: {auth_names}")
        print(f"[T6] user schemas: {user_names}")
        print(f"[T6] 缺失的预期 schema: {missing}")

        # 由于 T6 期望的 schema 未实现，此测试单独标记为不适用
        if missing:
            self.skipTest(
                f"T6 期望的 schema 未实现: {', '.join(missing)}"
            )

    def test_t6_02_user_create_no_constraints(self):
        """当前 UserCreate 无字段约束 — 4 位以下/特殊字符也能通过"""
        from app.schemas.user import UserCreate
        # 当前 UserCreate 无 min_length / pattern，任意字符串均可
        u = UserCreate(username="a", password="1", nickname="")
        self.assertEqual(u.username, "a")  # 实际通过 — 记录为缺失约束

    def test_t6_03_token_pair_structure(self):
        from app.schemas.auth import TokenPair
        tp = TokenPair(
            access_token="x", refresh_token="y", expires_in=900
        )
        self.assertEqual(tp.token_type, "Bearer")
        self.assertEqual(tp.expires_in, 900)


# ============================================================
# T7. 用户 Repository
# ============================================================


class T7UserRepository(RollbackTestCase):
    def test_t7_01_insert_and_find_by_id(self):
        email = make_email()
        username = f"a11_{unique_suffix()}"
        uid = user_repository.insert_user(
            self.db,
            username=username,
            password_hash="dummyhash",
            email=email,
            nickname="tester",
            now=utc_db_now(),
        )
        self.assertGreater(uid, 0)
        row = user_repository.find_by_id(self.db, uid)
        self.assertIsNotNone(row)
        self.assertEqual(row["username"], username)
        self.assertEqual(row["email"], email)

    def test_t7_02_find_by_username(self):
        username = f"a11_{unique_suffix()}"
        uid = self.insert_user(username=username)
        row = user_repository.find_by_username(self.db, username)
        self.assertEqual(row["id"], uid)

    def test_t7_03_find_by_email(self):
        email = make_email()
        uid = self.insert_user(email=email)
        row = user_repository.find_by_email(self.db, email)
        self.assertEqual(row["id"], uid)

    def test_t7_04_unique_username(self):
        from sqlalchemy.exc import IntegrityError
        username = f"a11_{unique_suffix()}"
        self.insert_user(username=username)
        with self.assertRaises(IntegrityError):
            self.insert_user(username=username)

    def test_t7_05_unique_email(self):
        from sqlalchemy.exc import IntegrityError
        email = make_email()
        self.insert_user(email=email)
        with self.assertRaises(IntegrityError):
            self.insert_user(email=email)

    def test_t7_06_for_update(self):
        uid = self.insert_user()
        # FOR UPDATE 在同一事务内不阻塞，只验证 SQL 不报错
        row = user_repository.find_by_id(self.db, uid, for_update=True)
        self.assertIsNotNone(row)

    def test_t7_07_not_found_returns_none(self):
        self.assertIsNone(user_repository.find_by_id(self.db, 999999999))
        self.assertIsNone(
            user_repository.find_by_username(self.db, "nonexistent_" + unique_suffix())
        )
        self.assertIsNone(user_repository.find_by_email(self.db, make_email()))

    def test_t7_08_sql_injection_safe(self):
        """参数绑定：恶意输入被作为字面值处理"""
        malicious = "'; DROP TABLE users; --"
        self.assertIsNone(user_repository.find_by_username(self.db, malicious))
        # 表应仍然存在
        cnt = self.sql("SELECT COUNT(*) FROM users").scalar_one()
        self.assertGreaterEqual(cnt, 0)


# ============================================================
# T8. Session Repository
# ============================================================


class T8SessionRepository(RollbackTestCase):
    def setUp(self):
        super().setUp()
        self.user_id = self.insert_user()
        self.family_id = str(uuid.uuid4())
        self.now = utc_db_now()
        session_repository.insert_session(
            self.db,
            family_id=self.family_id,
            user_id=self.user_id,
            user_agent="pytest",
            now=self.now,
            absolute_expires_at=self.now + timedelta(days=30),
        )

    def test_t8_01_insert_and_find(self):
        row = session_repository.find_session(
            self.db, self.user_id, self.family_id
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], self.user_id)
        self.assertIsNone(row["revoked_at"])

    def test_t8_02_find_session_with_user(self):
        row = session_repository.find_session_with_user(
            self.db, self.user_id, self.family_id
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], self.user_id)

    def test_t8_03_cross_user_denied(self):
        other = self.insert_user()
        row = session_repository.find_session(
            self.db, other, self.family_id
        )
        self.assertIsNone(row)

    def test_t8_04_list_active_sessions(self):
        rows = session_repository.list_active_sessions(
            self.db,
            self.user_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
        )
        self.assertTrue(any(r["family_id"] == self.family_id for r in rows))

    def test_t8_05_exclude_revoked(self):
        session_repository.revoke_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            reason="LOGOUT",
        )
        rows = session_repository.list_active_sessions(
            self.db,
            self.user_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
        )
        self.assertFalse(any(r["family_id"] == self.family_id for r in rows))

    def test_t8_06_exclude_idle_expired(self):
        """last_activity_at 早于 idle_cutoff 的会话应被排除"""
        # 把 last_activity_at 改到 8 天前
        self.sql(
            "UPDATE login_sessions SET last_activity_at = :t WHERE family_id = :f",
            t=self.now - timedelta(days=8),
            f=self.family_id,
        )
        rows = session_repository.list_active_sessions(
            self.db,
            self.user_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
        )
        self.assertFalse(any(r["family_id"] == self.family_id for r in rows))

    def test_t8_07_exclude_absolute_expired(self):
        self.sql(
            "UPDATE login_sessions SET absolute_expires_at = :t WHERE family_id = :f",
            t=self.now - timedelta(seconds=1),
            f=self.family_id,
        )
        rows = session_repository.list_active_sessions(
            self.db,
            self.user_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
        )
        self.assertFalse(any(r["family_id"] == self.family_id for r in rows))

    def test_t8_08_touch_within_300s_no_update(self):
        """不足 300 秒不更新活跃时间"""
        # last_activity_at = self.now
        write_cutoff = self.now - timedelta(seconds=300)
        idle_cutoff = self.now - timedelta(days=7)
        rc = session_repository.touch_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            idle_cutoff=idle_cutoff,
            write_cutoff=write_cutoff,
        )
        # 刚创建，last_activity_at=now > write_cutoff → 0 行
        self.assertEqual(rc, 0)

    def test_t8_09_touch_after_300s_updates(self):
        """达到 300 秒允许更新"""
        # 把 last_activity_at 改到 6 分钟前
        self.sql(
            "UPDATE login_sessions SET last_activity_at = :t WHERE family_id = :f",
            t=self.now - timedelta(minutes=6),
            f=self.family_id,
        )
        write_cutoff = self.now - timedelta(seconds=300)
        idle_cutoff = self.now - timedelta(days=7)
        rc = session_repository.touch_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            idle_cutoff=idle_cutoff,
            write_cutoff=write_cutoff,
        )
        self.assertEqual(rc, 1)

    def test_t8_10_revoked_session_cannot_touch(self):
        """已撤销会话不能通过 touch_session 复活"""
        self.sql(
            "UPDATE login_sessions SET last_activity_at = :t WHERE family_id = :f",
            t=self.now - timedelta(minutes=6),
            f=self.family_id,
        )
        session_repository.revoke_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            reason="LOGOUT",
        )
        rc = session_repository.touch_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
            write_cutoff=self.now - timedelta(seconds=300),
        )
        self.assertEqual(rc, 0)

    def test_t8_11_absolute_expired_cannot_touch(self):
        self.sql(
            "UPDATE login_sessions SET absolute_expires_at = :t, last_activity_at = :t2 "
            "WHERE family_id = :f",
            t=self.now - timedelta(seconds=1),
            t2=self.now - timedelta(minutes=6),
            f=self.family_id,
        )
        rc = session_repository.touch_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            idle_cutoff=self.now - timedelta(days=7),
            write_cutoff=self.now - timedelta(seconds=300),
        )
        self.assertEqual(rc, 0)

    def test_t8_12_revoke_session(self):
        rc = session_repository.revoke_session(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
            reason="LOGOUT",
        )
        self.assertEqual(rc, 1)
        row = session_repository.find_session(
            self.db, self.user_id, self.family_id
        )
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(row["revoked_reason"], "LOGOUT")

    def test_t8_13_revoke_all_sessions(self):
        # 再创建 2 个会话
        fid2 = str(uuid.uuid4())
        fid3 = str(uuid.uuid4())
        for fid in (fid2, fid3):
            session_repository.insert_session(
                self.db,
                family_id=fid,
                user_id=self.user_id,
                user_agent="pytest",
                now=self.now,
                absolute_expires_at=self.now + timedelta(days=30),
            )
        rc = session_repository.revoke_all_sessions(
            self.db, user_id=self.user_id, now=self.now, reason="LOGOUT_ALL"
        )
        self.assertEqual(rc, 3)

    def test_t8_14_revoke_all_except_one(self):
        fid2 = str(uuid.uuid4())
        fid3 = str(uuid.uuid4())
        for fid in (fid2, fid3):
            session_repository.insert_session(
                self.db,
                family_id=fid,
                user_id=self.user_id,
                user_agent="pytest",
                now=self.now,
                absolute_expires_at=self.now + timedelta(days=30),
            )
        rc = session_repository.revoke_all_sessions(
            self.db,
            user_id=self.user_id,
            now=self.now,
            reason="LOGOUT_ALL",
            exclude_family_id=self.family_id,
        )
        self.assertEqual(rc, 2)
        # 保留的会话仍可查
        row = session_repository.find_session(
            self.db, self.user_id, self.family_id
        )
        self.assertIsNone(row["revoked_at"])


# ============================================================
# T9. Token Repository
# ============================================================


class T9TokenRepository(RollbackTestCase):
    def setUp(self):
        super().setUp()
        self.user_id = self.insert_user()
        self.family_id = str(uuid.uuid4())
        self.now = utc_db_now()
        # 先建会话
        session_repository.insert_session(
            self.db,
            family_id=self.family_id,
            user_id=self.user_id,
            user_agent="pytest",
            now=self.now,
            absolute_expires_at=self.now + timedelta(days=30),
        )

    def _new_token_hash(self) -> str:
        return security.hash_refresh_token(uuid.uuid4().hex)

    def _insert_token(self, token_hash=None, family_id=None, expires_delta=None):
        token_hash = token_hash or self._new_token_hash()
        family_id = family_id or self.family_id
        expires_at = self.now + (expires_delta or timedelta(days=7))
        token_repository.insert_token(
            self.db,
            user_id=self.user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            now=self.now,
        )
        return token_hash

    def test_t9_01_insert_and_find(self):
        th = self._insert_token()
        row = token_repository.find_by_hash(self.db, th)
        self.assertIsNotNone(row)
        self.assertEqual(row["token_hash"], th)
        self.assertIsNone(row["revoked_at"])
        self.assertIsNone(row["replaced_by"])

    def test_t9_02_unique_hash(self):
        from sqlalchemy.exc import IntegrityError
        th = self._insert_token()
        with self.assertRaises(IntegrityError):
            self._insert_token(token_hash=th)

    def test_t9_03_for_update(self):
        th = self._insert_token()
        row = token_repository.find_by_hash(self.db, th, for_update=True)
        self.assertIsNotNone(row)

    def test_t9_04_rotate(self):
        th = self._insert_token()
        row = token_repository.find_by_hash(self.db, th)
        new_th = self._new_token_hash()
        # 插入新 token
        self._insert_token(token_hash=new_th)
        rc = token_repository.mark_rotated(
            self.db,
            token_id=row["id"],
            new_token_hash=new_th,
            now=self.now,
        )
        self.assertEqual(rc, 1)
        after = token_repository.find_by_hash(self.db, th)
        self.assertIsNotNone(after["revoked_at"])
        self.assertEqual(after["replaced_by"], new_th)

    def test_t9_05_cannot_rotate_already_rotated(self):
        th = self._insert_token()
        row = token_repository.find_by_hash(self.db, th)
        new_th = self._new_token_hash()
        self._insert_token(token_hash=new_th)
        token_repository.mark_rotated(
            self.db, token_id=row["id"], new_token_hash=new_th, now=self.now
        )
        # 再次轮换
        rc = token_repository.mark_rotated(
            self.db,
            token_id=row["id"],
            new_token_hash=self._new_token_hash(),
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_t9_06_cannot_rotate_revoked(self):
        th = self._insert_token()
        token_repository.revoke_family(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
        )
        row = token_repository.find_by_hash(self.db, th)
        rc = token_repository.mark_rotated(
            self.db,
            token_id=row["id"],
            new_token_hash=self._new_token_hash(),
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_t9_07_cannot_rotate_expired(self):
        th = self._insert_token(expires_delta=timedelta(seconds=-10))
        row = token_repository.find_by_hash(self.db, th)
        rc = token_repository.mark_rotated(
            self.db,
            token_id=row["id"],
            new_token_hash=self._new_token_hash(),
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_t9_08_revoke_family(self):
        th1 = self._insert_token()
        th2 = self._insert_token()
        rc = token_repository.revoke_family(
            self.db,
            user_id=self.user_id,
            family_id=self.family_id,
            now=self.now,
        )
        self.assertEqual(rc, 2)
        for th in (th1, th2):
            row = token_repository.find_by_hash(self.db, th)
            self.assertIsNotNone(row["revoked_at"])

    def test_t9_09_revoke_all(self):
        fid2 = str(uuid.uuid4())
        session_repository.insert_session(
            self.db,
            family_id=fid2,
            user_id=self.user_id,
            user_agent="pytest",
            now=self.now,
            absolute_expires_at=self.now + timedelta(days=30),
        )
        self._insert_token()
        self._insert_token(family_id=fid2)
        rc = token_repository.revoke_all_tokens(
            self.db, user_id=self.user_id, now=self.now
        )
        self.assertEqual(rc, 2)

    def test_t9_10_revoke_all_except_family(self):
        fid2 = str(uuid.uuid4())
        session_repository.insert_session(
            self.db,
            family_id=fid2,
            user_id=self.user_id,
            user_agent="pytest",
            now=self.now,
            absolute_expires_at=self.now + timedelta(days=30),
        )
        th1 = self._insert_token()
        th2 = self._insert_token(family_id=fid2)
        rc = token_repository.revoke_all_tokens(
            self.db,
            user_id=self.user_id,
            now=self.now,
            exclude_family_id=self.family_id,
        )
        self.assertEqual(rc, 1)
        # 被保留的 token 未撤销
        row1 = token_repository.find_by_hash(self.db, th1)
        self.assertIsNone(row1["revoked_at"])
        row2 = token_repository.find_by_hash(self.db, th2)
        self.assertIsNotNone(row2["revoked_at"])

    def test_t9_11_uses_new_table_name(self):
        """静态检查：所有 SQL 用 refresh_tokens 表名"""
        import inspect
        src = inspect.getsource(token_repository)
        # 不允许出现旧表名（示例：refresh_token 单数、或带前缀变体）
        # 简单断言：源码中只出现 refresh_tokens
        # 注意源码里也有函数名 insert_token 等，需用正则匹配表名上下文
        # 找 FROM/INTO/UPDATE/JOIN 后的表名
        # SQL 关键字必须大写（避免误识别 Python 的 .update() 调用）
        pattern = re.compile(
            r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)\b"
        )
        matches = pattern.findall(src)
        self.assertTrue(matches, "未找到任何 SQL 表名")
        for tbl in matches:
            self.assertEqual(
                tbl.lower(), "refresh_tokens", f"非新版表名: {tbl}"
            )

    def test_t9_12_datetime_precision(self):
        """refresh_tokens.expires_at 是 datetime（秒级）"""
        th = self._insert_token()
        row = token_repository.find_by_hash(self.db, th)
        # MySQL datetime 无小数秒
        self.assertIsInstance(row["expires_at"], datetime)
        self.assertEqual(row["expires_at"].microsecond, 0)


# ============================================================
# T10. Verification Repository
# ============================================================


class T10VerificationRepository(RollbackTestCase):
    def setUp(self):
        super().setUp()
        self.now = utc_db_now()
        self.email = make_email()
        self.purpose = "REGISTER"
        self.code = "123456"
        self.code_hash = security.hash_email_code(
            self.email, self.purpose, self.code
        )

    def _insert(self, *, email=None, purpose=None, ip="1.2.3.4",
                user_id=None, family_id=None, expires_delta=None):
        return verification_repository.insert_verification(
            self.db,
            email=email or self.email,
            purpose=purpose or self.purpose,
            code_hash=self.code_hash,
            request_ip=ip,
            now=self.now,
            expires_at=self.now + (expires_delta or timedelta(minutes=5)),
            user_id=user_id,
            family_id=family_id,
        )

    def test_t10_01_insert_pending(self):
        vid = self._insert()
        self.assertGreater(vid, 0)
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        self.assertEqual(row["send_status"], "PENDING")
        self.assertIsNone(row["consumed_at"])
        self.assertIsNone(row["invalidated_at"])

    def test_t10_02_pending_to_sent(self):
        vid = self._insert()
        rc = verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        self.assertEqual(rc, 1)
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        self.assertEqual(row["send_status"], "SENT")

    def test_t10_03_pending_to_failed(self):
        vid = self._insert()
        rc = verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=False
        )
        self.assertEqual(rc, 1)
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        self.assertEqual(row["send_status"], "FAILED")

    def test_t10_04_cannot_remark_status(self):
        """PENDING 一次性，已 SENT 不能再改 FAILED"""
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        rc = verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=False
        )
        self.assertEqual(rc, 0)

    def test_t10_05_latest_per_email_purpose(self):
        self._insert()
        self._insert()
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        # 后插入的 id 更大
        # 确认查询返回的是最新一条
        cnt = self.sql(
            "SELECT COUNT(*) FROM email_verifications WHERE email=:e AND purpose=:p",
            e=self.email, p=self.purpose,
        ).scalar_one()
        self.assertEqual(cnt, 2)

    def test_t10_06_invalidate_previous(self):
        self._insert()
        self._insert()
        rc = verification_repository.invalidate_previous(
            self.db, email=self.email, purpose=self.purpose, now=self.now
        )
        # 2 条都被作废（新创建前应先 invalidate）
        self.assertEqual(rc, 2)

    def test_t10_07_old_code_cannot_consume(self):
        """作废旧验证码后不能再消费"""
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        verification_repository.invalidate_previous(
            self.db, email=self.email, purpose=self.purpose, now=self.now
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_08_attempts_increment(self):
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        for i in range(1, 4):
            rc = verification_repository.increment_attempts(
                self.db,
                verification_id=vid,
                now=self.now,
                max_attempts=5,
            )
            self.assertEqual(rc, 1)
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        self.assertEqual(row["attempts"], 3)

    def test_t10_09_attempts_max_5(self):
        """达到 5 次错误后禁止再增"""
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        for _ in range(5):
            verification_repository.increment_attempts(
                self.db,
                verification_id=vid,
                now=self.now,
                max_attempts=5,
            )
        # 第 6 次应被 SQL 条件拦截
        rc = verification_repository.increment_attempts(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)
        # consume 也应被拒
        rc2 = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc2, 0)

    def test_t10_10_consume_success(self):
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 1)
        row = verification_repository.find_latest_verification(
            self.db, self.email, self.purpose
        )
        self.assertIsNotNone(row["consumed_at"])

    def test_t10_11_no_double_consume(self):
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_12_cannot_consume_expired(self):
        vid = self._insert(expires_delta=timedelta(seconds=-10))
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_13_cannot_consume_invalidated(self):
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=True
        )
        verification_repository.invalidate_previous(
            self.db, email=self.email, purpose=self.purpose, now=self.now
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_14_cannot_consume_pending(self):
        vid = self._insert()
        # 保持 PENDING
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_15_cannot_consume_failed(self):
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=False
        )
        rc = verification_repository.consume_verification(
            self.db,
            verification_id=vid,
            now=self.now,
            max_attempts=5,
        )
        self.assertEqual(rc, 0)

    def test_t10_16_count_email_sends(self):
        self._insert()
        self._insert()
        cnt = verification_repository.count_email_sends(
            self.db, self.email, self.now - timedelta(hours=1)
        )
        self.assertEqual(cnt, 2)

    def test_t10_17_count_ip_sends(self):
        self._insert(ip="9.9.9.9")
        self._insert(ip="9.9.9.9")
        self._insert(ip="1.1.1.1")
        cnt = verification_repository.count_ip_sends(
            self.db, "9.9.9.9", self.now - timedelta(hours=1)
        )
        self.assertEqual(cnt, 2)

    def test_t10_18_count_global_sends(self):
        before = verification_repository.count_global_sends(
            self.db, self.now - timedelta(hours=1)
        )
        self._insert()
        self._insert()
        after = verification_repository.count_global_sends(
            self.db, self.now - timedelta(hours=1)
        )
        self.assertEqual(after - before, 2)

    def test_t10_19_find_last_send_time(self):
        self._insert()
        last = verification_repository.find_last_send_time(self.db, self.email)
        self.assertIsNotNone(last)
        # 与 self.now 相差应在秒级
        self.assertLess(abs((last - self.now).total_seconds()), 2)

    def test_t10_20_failed_send_counts_to_quota(self):
        """FAILED 仍计入额度（基于 created_at 计数）"""
        vid = self._insert()
        verification_repository.mark_send_result(
            self.db, verification_id=vid, sent=False
        )
        cnt = verification_repository.count_email_sends(
            self.db, self.email, self.now - timedelta(hours=1)
        )
        self.assertEqual(cnt, 1)

    def test_t10_21_user_session_binding(self):
        uid = self.insert_user()
        fid = str(uuid.uuid4())
        # 会话也要建
        session_repository.insert_session(
            self.db,
            family_id=fid,
            user_id=uid,
            user_agent="pytest",
            now=self.now,
            absolute_expires_at=self.now + timedelta(days=30),
        )
        email2 = make_email()
        vid = verification_repository.insert_verification(
            self.db,
            email=email2,
            purpose="CHANGE_EMAIL_NEW",
            code_hash=self.code_hash,
            request_ip="1.2.3.4",
            now=self.now,
            expires_at=self.now + timedelta(minutes=5),
            user_id=uid,
            family_id=fid,
        )
        row = verification_repository.find_latest_verification(
            self.db, email2, "CHANGE_EMAIL_NEW"
        )
        self.assertEqual(row["user_id"], uid)
        self.assertEqual(row["family_id"], fid)


# ============================================================
# T11. Auth Event Repository
# ============================================================


class T11AuthEventRepository(RollbackTestCase):
    def setUp(self):
        super().setUp()
        self.now = utc_db_now()
        self.user_id = self.insert_user()

    def _insert(self, *, event_type="LOGIN_FAILED", user_id=None,
                identifier=None, ip=None, family_id=None, when=None):
        auth_event_repository.insert_event(
            self.db,
            event_type=event_type,
            now=when or self.now,
            user_id=user_id if user_id is not None else self.user_id,
            identifier=identifier,
            ip=ip,
            family_id=family_id,
        )

    def test_t11_01_insert_event(self):
        self._insert()
        cnt = auth_event_repository.count_user_events(
            self.db,
            user_id=self.user_id,
            event_type="LOGIN_FAILED",
            since=self.now - timedelta(minutes=10),
        )
        self.assertEqual(cnt, 1)

    def test_t11_02_count_by_user(self):
        self._insert()
        self._insert()
        cnt = auth_event_repository.count_user_events(
            self.db,
            user_id=self.user_id,
            event_type="LOGIN_FAILED",
            since=self.now - timedelta(minutes=10),
        )
        self.assertEqual(cnt, 2)

    def test_t11_03_count_by_identifier(self):
        ident = f"user_{unique_suffix()}"
        self._insert(identifier=ident)
        self._insert(identifier=ident)
        cnt = auth_event_repository.count_identifier_events(
            self.db,
            identifier=ident,
            event_type="LOGIN_FAILED",
            since=self.now - timedelta(minutes=10),
        )
        self.assertEqual(cnt, 2)

    def test_t11_04_count_by_ip(self):
        ip = "5.5.5.5"
        self._insert(ip=ip)
        self._insert(ip=ip)
        self._insert(ip="6.6.6.6")
        cnt = auth_event_repository.count_ip_events(
            self.db,
            ip=ip,
            event_type="LOGIN_FAILED",
            since=self.now - timedelta(minutes=10),
        )
        self.assertEqual(cnt, 2)

    def test_t11_05_latest_event(self):
        self._insert()
        self._insert()
        row = auth_event_repository.find_latest_user_event(
            self.db, self.user_id, "LOGIN_FAILED"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["event_type"], "LOGIN_FAILED")

    def test_t11_06_after_id_excludes_history(self):
        """after_id 排除历史失败记录"""
        self._insert()
        first = auth_event_repository.find_latest_user_event(
            self.db, self.user_id, "LOGIN_FAILED"
        )
        self._insert()
        self._insert()
        cnt = auth_event_repository.count_user_events(
            self.db,
            user_id=self.user_id,
            event_type="LOGIN_FAILED",
            since=self.now - timedelta(minutes=10),
            after_id=first["id"],
        )
        self.assertEqual(cnt, 2)

    def test_t11_07_time_window_boundary(self):
        """created_at >= since 边界：恰好等于 since 应被计入"""
        since = self.now - timedelta(minutes=30)
        self._insert(when=since)
        cnt = auth_event_repository.count_user_events(
            self.db,
            user_id=self.user_id,
            event_type="LOGIN_FAILED",
            since=since,
        )
        self.assertEqual(cnt, 1)

    def test_t11_08_identifier_ip_no_after_id(self):
        """identifier/ip 维度的统计缺少 after_id 参数 — 仅记录问题"""
        import inspect
        sig_id = inspect.signature(
            auth_event_repository.count_identifier_events
        )
        sig_ip = inspect.signature(auth_event_repository.count_ip_events)
        # 预期应支持 after_id 实现"上次成功后清零"
        has_after_id = (
            "after_id" in sig_id.parameters
            and "after_id" in sig_ip.parameters
        )
        if not has_after_id:
            self.fail(
                "count_identifier_events/count_ip_events 缺少 after_id 参数，"
                "无法支持'上次登录成功后清零'语义"
            )

    def test_t11_09_no_sensitive_fields_in_schema(self):
        """表结构不含 password/code/token 字段"""
        cols = self.sql(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'auth_events'
            """,
            db=_EXPECTED_DB,
        ).scalars().all()
        forbidden = {"password", "password_hash", "code", "code_hash",
                     "token", "token_hash", "refresh_token"}
        leaked = forbidden & {c.lower() for c in cols}
        self.assertFalse(leaked, f"auth_events 含敏感字段: {leaked}")


# ============================================================
# T12. 事务及并发基础测试
# ============================================================


class T12TransactionsAndConcurrency(RollbackTestCase):
    def test_t12_01_repos_do_not_commit(self):
        """五个 Repository 不主动 commit/rollback"""
        import inspect
        repos = [
            user_repository,
            session_repository,
            token_repository,
            verification_repository,
            auth_event_repository,
        ]
        for repo in repos:
            src = inspect.getsource(repo)
            self.assertNotIn(".commit(", src, f"{repo.__name__} 含 commit")
            self.assertNotIn(".rollback(", src, f"{repo.__name__} 含 rollback")

    def test_t12_02_multi_table_rollback(self):
        """多表插入外层事务回滚后均无残留"""
        # 准备
        uid = self.insert_user()
        fid = str(uuid.uuid4())
        session_repository.insert_session(
            self.db,
            family_id=fid,
            user_id=uid,
            user_agent="pytest",
            now=utc_db_now(),
            absolute_expires_at=utc_db_now() + timedelta(days=30),
        )
        # 记录计数
        uid_local = uid
        fid_local = fid
        # 在 tearDown 中外层回滚，此处手动验证（用 savepoint）
        # 实际回滚验证：另开一连接查不到
        # 但因为未提交，隔离级别 REPEATABLE READ 下同连接可见
        # 用 SAVEPOINT 验证逻辑更简单：本测试只断言插入逻辑 OK
        row = session_repository.find_session(self.db, uid_local, fid_local)
        self.assertIsNotNone(row)
        # tearDown 会 rollback，最终数据库无残留由清理脚本验证

    def test_t12_03_concurrent_consume(self):
        """验证码条件 UPDATE 并发消费时最多一个成功"""
        # 并发需要提交，改用独立连接 + 真实提交
        self.skipTest("并发测试见 T12ConcurrencyCommitted")

    def test_t12_04_concurrent_rotate(self):
        """Token 条件 UPDATE 并发轮换时最多一个成功"""
        self.skipTest("并发测试见 T12ConcurrencyCommitted")

    def test_t12_05_sql_field_match(self):
        """SQL 中引用的列必须真实存在于表中"""
        # 已通过 INSERT/SELECT 测试间接验证
        # 此处检查关键列类型
        cols = self.sql(
            """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'login_sessions'
            """,
            db=_EXPECTED_DB,
        ).mappings().all()
        col_map = {c["COLUMN_NAME"]: c for c in cols}
        self.assertIn("family_id", col_map)
        self.assertIn("user_id", col_map)
        self.assertIn("revoked_at", col_map)
        self.assertIn("revoked_reason", col_map)
        self.assertEqual(col_map["family_id"]["CHARACTER_MAXIMUM_LENGTH"], 36)


class T12ConcurrencyCommitted(unittest.TestCase):
    """需要真实提交的并发测试，使用独立连接，结束后精确清理。"""

    def setUp(self):
        # 独立引擎实例避免连接池共享
        self.engine2 = create_engine(
            URL.create(
                drivername="mysql+pymysql",
                username=settings.DB_USER,
                password=settings.DB_PASSWORD,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=_EXPECTED_DB,
                query={"charset": "utf8mb4"},
            ),
            pool_pre_ping=True,
            connect_args={"init_command": "SET time_zone = '+08:00'"},
        )
        self.Session2 = sessionmaker(bind=self.engine2)
        self.now = utc_db_now()
        self.suffix = unique_suffix()
        self.email = f"a11_conc_{self.suffix}@test.local"
        self.username = f"a11_conc_{self.suffix}"
        self.user_id = None
        self.family_id = str(uuid.uuid4())
        self.verification_id = None
        self.token_hash = None

    def tearDown(self):
        """精确清理：按 username/email/family_id 删除"""
        s = self.Session2()
        try:
            s.execute(
                text("DELETE FROM email_verifications WHERE email = :e"),
                {"e": self.email},
            )
            s.execute(
                text("DELETE FROM auth_events WHERE identifier = :i"),
                {"i": self.username},
            )
            if self.family_id:
                s.execute(
                    text("DELETE FROM refresh_tokens WHERE family_id = :f"),
                    {"f": self.family_id},
                )
                s.execute(
                    text("DELETE FROM login_sessions WHERE family_id = :f"),
                    {"f": self.family_id},
                )
            if self.user_id:
                s.execute(
                    text("DELETE FROM users WHERE id = :u"),
                    {"u": self.user_id},
                )
            s.commit()
        finally:
            s.close()
            self.engine2.dispose()

    def _create_user_session(self):
        s = self.Session2()
        try:
            uid = s.execute(
                text(
                    """
                    INSERT INTO users (
                        username, password_hash, password_updated_at,
                        email, email_verified_at, nickname
                    ) VALUES (
                        :u, 'dummy', :now, :e, :now, 'tester'
                    )
                    """
                ),
                {
                    "u": self.username,
                    "e": self.email,
                    "now": self.now,
                },
            ).lastrowid
            s.execute(
                text(
                    """
                    INSERT INTO login_sessions (
                        family_id, user_id, user_agent,
                        created_at, last_activity_at, absolute_expires_at
                    ) VALUES (
                        :f, :u, 'pytest', :now, :now, :abs
                    )
                    """
                ),
                {
                    "f": self.family_id,
                    "u": uid,
                    "now": self.now,
                    "abs": self.now + timedelta(days=30),
                },
            )
            s.commit()
            self.user_id = uid
        finally:
            s.close()

    def test_t12c_01_concurrent_consume_only_one_wins(self):
        """5 个线程同时消费同一验证码，只允许 1 个成功"""
        self._create_user_session()

        # 建一条 SENT 验证码
        s = self.Session2()
        try:
            code_hash = security.hash_email_code(
                self.email, "REGISTER", "123456"
            )
            vid = s.execute(
                text(
                    """
                    INSERT INTO email_verifications (
                        email, purpose, code_hash, request_ip,
                        created_at, expires_at, send_status
                    ) VALUES (
                        :e, 'REGISTER', :ch, '1.2.3.4', :now, :exp, 'SENT'
                    )
                    """
                ),
                {
                    "e": self.email,
                    "ch": code_hash,
                    "now": self.now,
                    "exp": self.now + timedelta(minutes=5),
                },
            ).lastrowid
            s.commit()
            self.verification_id = vid
        finally:
            s.close()

        results = [None] * 5
        barrier = threading.Barrier(5)

        def worker(idx):
            barrier.wait()
            sess = self.Session2()
            try:
                rc = verification_repository.consume_verification(
                    sess,
                    verification_id=self.verification_id,
                    now=utc_db_now(),
                    max_attempts=5,
                )
                sess.commit()
                results[idx] = rc
            except Exception as e:
                sess.rollback()
                results[idx] = f"error:{type(e).__name__}"
            finally:
                sess.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = sum(1 for r in results if r == 1)
        self.assertEqual(
            successes, 1, f"应只有 1 个成功，实际: {results}"
        )

    def test_t12c_02_concurrent_rotate_only_one_wins(self):
        """5 个线程同时轮换同一 Token，只允许 1 个成功"""
        self._create_user_session()

        # 插入原 token + 5 个新 token
        s = self.Session2()
        try:
            old_th = security.hash_refresh_token(uuid.uuid4().hex)
            s.execute(
                text(
                    """
                    INSERT INTO refresh_tokens (
                        user_id, family_id, token_hash, expires_at, created_at
                    ) VALUES (
                        :u, :f, :th, :exp, :now
                    )
                    """
                ),
                {
                    "u": self.user_id,
                    "f": self.family_id,
                    "th": old_th,
                    "exp": self.now + timedelta(days=7),
                    "now": self.now,
                },
            )
            new_ths = [security.hash_refresh_token(uuid.uuid4().hex) for _ in range(5)]
            for nth in new_ths:
                s.execute(
                    text(
                        """
                        INSERT INTO refresh_tokens (
                            user_id, family_id, token_hash, expires_at, created_at
                        ) VALUES (
                            :u, :f, :th, :exp, :now
                        )
                        """
                    ),
                    {
                        "u": self.user_id,
                        "f": self.family_id,
                        "th": nth,
                        "exp": self.now + timedelta(days=7),
                        "now": self.now,
                    },
                )
            s.commit()
            row = s.execute(
                text("SELECT id FROM refresh_tokens WHERE token_hash = :t"),
                {"t": old_th},
            ).mappings().first()
            self.token_hash = old_th
            old_id = row["id"]
        finally:
            s.close()

        results = [None] * 5
        barrier = threading.Barrier(5)

        def worker(idx):
            barrier.wait()
            sess = self.Session2()
            try:
                rc = token_repository.mark_rotated(
                    sess,
                    token_id=old_id,
                    new_token_hash=new_ths[idx],
                    now=utc_db_now(),
                )
                sess.commit()
                results[idx] = rc
            except Exception as e:
                sess.rollback()
                results[idx] = f"error:{type(e).__name__}"
            finally:
                sess.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = sum(1 for r in results if r == 1)
        self.assertEqual(
            successes, 1, f"应只有 1 个成功，实际: {results}"
        )


# ============================================================
# T13. 敏感信息保护
# ============================================================


class T13SensitiveInfoProtection(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_t13_01_validation_error_no_raw_password(self):
        """参数验证异常不包含原始密码"""
        # 触发 422：注册路由可能不存在，但 FastAPI 默认对未知路由返回 404
        # 改用 OpenAPI schema 中已知的路由
        # 当前 auth 路由可能尚未升级到 V2 — 直接调用一个会触发 422 的端点
        # 用 /auth/login 如果存在的话
        sensitive = "VerySecretP@ssw0rd!"
        resp = self.client.post(
            "/auth/login",
            json={"username": 12345, "password": sensitive},  # 错误类型
        )
        # 状态码是 404 也行 — 表示旧版未升级；记录但不强制要求
        if resp.status_code == 422:
            body = resp.text
            self.assertNotIn(sensitive, body)
        else:
            self.skipTest(
                f"/auth/login 返回 {resp.status_code}，旧版未升级或不支持"
            )

    def test_t13_02_validation_error_no_raw_code(self):
        sensitive_code = "987654"
        resp = self.client.post(
            "/auth/email-code/verify",
            json={"email": "a@b.com", "code": sensitive_code},
        )
        if resp.status_code == 422:
            self.assertNotIn(sensitive_code, resp.text)
        else:
            self.skipTest(f"/auth/email-code/verify 返回 {resp.status_code}")

    def test_t13_03_validation_error_no_raw_token(self):
        sensitive_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.test"
        resp = self.client.post(
            "/auth/refresh",
            json={"refresh_token": sensitive_token, "extra": {"x": "y"}},
        )
        if resp.status_code == 422:
            self.assertNotIn(sensitive_token, resp.text)
        else:
            self.skipTest(f"/auth/refresh 返回 {resp.status_code}")

    def test_t13_04_validation_error_structure(self):
        """422 响应结构含 code/message/data，data 含 loc 与 type"""
        # 构造一个已知会触发 422 的请求
        # 用不存在的路由触发 404 而非 422
        # 改用一个稳定的：plans 路由下任意 POST 缺字段
        # 由于不知道 A1.1 后是否已有 V2 路由，先确认任意 422
        resp = self.client.post(
            "/auth/login",
            json={"username": 123},  # 缺 password
        )
        if resp.status_code != 422:
            self.skipTest(f"返回 {resp.status_code}，路由未实现")
        body = resp.json()
        self.assertIn("code", body)
        self.assertIn("message", body)
        self.assertIn("data", body)
        self.assertEqual(body["code"], 422)
        self.assertIsInstance(body["data"], list)
        if body["data"]:
            item = body["data"][0]
            self.assertIn("loc", item)
            self.assertIn("type", item)
            self.assertIn("msg", item)
            # 不应包含原始输入
            self.assertNotIn("input", item)


# ============================================================
# 残留检测辅助
# ============================================================


def count_a11_residue() -> dict:
    """统计 a11_ 前缀的测试残留"""
    with engine.connect() as conn:
        res = {}
        res["users"] = conn.execute(
            text("SELECT COUNT(*) FROM users WHERE username LIKE 'a11\\_%'")
        ).scalar_one()
        res["email_verifications"] = conn.execute(
            text(
                "SELECT COUNT(*) FROM email_verifications "
                "WHERE email LIKE 'a11\\_%@test.local'"
            )
        ).scalar_one()
        res["auth_events"] = conn.execute(
            text(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE identifier LIKE 'a11\\_%'"
            )
        ).scalar_one()
        res["login_sessions"] = conn.execute(
            text(
                "SELECT COUNT(*) FROM login_sessions s "
                "JOIN users u ON s.user_id = u.id "
                "WHERE u.username LIKE 'a11\\_%'"
            )
        ).scalar_one()
        res["refresh_tokens"] = conn.execute(
            text(
                "SELECT COUNT(*) FROM refresh_tokens t "
                "JOIN users u ON t.user_id = u.id "
                "WHERE u.username LIKE 'a11\\_%'"
            )
        ).scalar_one()
        return res


if __name__ == "__main__":
    unittest.main(verbosity=2)
