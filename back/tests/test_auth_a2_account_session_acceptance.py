"""Auth V2.0 A2.1 / A2.2 集中验收测试（只读业务源码）。

覆盖：忘记密码、主动改密、邮箱换绑、会话列表、指定会话撤销、退出其他/全部设备。
仅使用隔离库 ssp_a0_migrate2；邮件全部 Mock；测试数据在 tearDownClass 精确清理。
"""

import inspect
import threading
import unittest
import uuid

from datetime import timedelta
from unittest import mock

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.clock import utc_db_now
from app.database import SessionLocal, engine
from app.main import app
from app.repositories.auth import session_repository, user_repository
from app.schemas.auth import (
    EmailCodePurpose,
    PasswordResetRequest,
    PasswordChangeRequest,
    EmailChangeRequest,
)
from app.services.auth import (
    account_service,
    session_service,
    auth_service,
    verification_service,
)
from tests.test_auth_a1_3_acceptance import CSRF, PASSWORD, BaseAuthTest


NEW_PASSWORD = "NewPass456"


class BaseA2(BaseAuthTest):
    """在 A1.3 测试基类之上补充 A2 常用操作。"""

    def bearer(self, pair):
        return {"Authorization": f"Bearer {pair['access_token']}"}

    def post_json(self, client, path, payload, extra_headers=None):
        headers = dict(CSRF)
        if extra_headers:
            headers.update(extra_headers)
        return client.post(path, json=payload, headers=headers)

    def reset_code(self, email, code, user_id):
        return self.mk_code(
            email, EmailCodePurpose.RESET_PASSWORD, code, user_id=user_id
        )

    def _family(self, pair):
        return security.decode_access_token(pair["access_token"])["family_id"]

    def run_concurrent(self, fn, n, timeout=30):
        """用独立数据库连接并发执行 fn(i)，返回 [(状态, 结果|异常)]。"""
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            try:
                barrier.wait(timeout=timeout)
                results[i] = ("ok", fn(i))
            except Exception as exc:  # noqa: BLE001
                results[i] = ("err", exc)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(n)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=timeout)
        return results

    def ok_count(self, results):
        return sum(1 for r in results if r[0] == "ok")

    def errors(self, results):
        return [r[1] for r in results if r[0] == "err"]

    def _hash(self, uid):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT password_hash FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()

    def _email_of(self, uid):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT email FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()

    def _prepare(self, suffix, old_code="111111", new_code="222222"):
        uid, username, email = self.make_user(suffix)
        new_email = f"{self.PREFIX}{suffix}n@example.com"
        pair, _ = self.login(username)
        family = self._family(pair)
        self.change_codes(
            email, new_email, uid, old_code, new_code, family_id=family
        )
        return uid, username, email, new_email, pair

    def change_codes(self, old_email, new_email, user_id, old_code, new_code, family_id=None):
        self.mk_code(
            old_email,
            EmailCodePurpose.CHANGE_EMAIL_OLD,
            old_code,
            user_id=user_id,
            family_id=family_id,
        )
        self.mk_code(
            new_email,
            EmailCodePurpose.CHANGE_EMAIL_NEW,
            new_code,
            user_id=user_id,
            family_id=family_id,
        )


# ======================================================================
# T0 模块与契约
# ======================================================================


class TestT0Contract(BaseA2):
    def test_eight_new_routes_registered(self):
        paths = app.openapi()["paths"]
        for path in (
            "/auth/password/reset",
            "/auth/password/change",
            "/auth/email/change",
            "/auth/sessions",
            "/auth/sessions/current",
            "/auth/sessions/revoke-others",
            "/auth/sessions/{family_id}/revoke",
            "/auth/logout-all",
        ):
            self.assertIn(path, paths, f"缺失路由 {path}")

    def test_existing_routes_not_broken(self):
        paths = app.openapi()["paths"]
        for path in (
            "/users",
            "/auth/email-code",
            "/auth/login",
            "/auth/login/email",
            "/auth/refresh",
            "/auth/logout",
        ):
            self.assertIn(path, paths, f"原有路由被破坏：{path}")

    def test_session_service_api_complete(self):
        required = [
            "lock_current_user",
            "revoke_user_sessions",
            "list_sessions",
            "get_current_session",
        ]
        missing = [n for n in required if not hasattr(session_service, n)]
        self.assertEqual(
            missing,
            [],
            f"session_service 缺少被路由/服务调用的函数：{missing}",
        )

    def test_account_service_functions_exist(self):
        for name in (
            "reset_password",
            "change_password",
            "change_email",
            "revoke_other_session",
            "revoke_sessions",
        ):
            self.assertTrue(callable(getattr(account_service, name, None)), name)

    def test_repository_capabilities_exist(self):
        for name in (
            "list_active_sessions_page",
            "count_active_sessions",
            "revoke_all_sessions",
            "revoke_session",
            "find_session",
        ):
            self.assertTrue(callable(getattr(session_repository, name, None)), name)
        for name in ("update_password", "update_email", "find_by_email"):
            self.assertTrue(callable(getattr(user_repository, name, None)), name)

    def test_all_new_routes_do_not_500(self):
        # 使用真实登录会话，确保请求真正进入 Service 层
        uid, username, email = self.make_user("rt")
        self.reset_code(email, "135791", uid)
        pair, _ = self.login(username)
        headers = {**CSRF, **self.bearer(pair)}

        uid2, username2, email2 = self.make_user("rt2")
        pair2, _ = self.login(username2)
        headers2 = {**CSRF, **self.bearer(pair2)}

        client = self.new_client()
        client.cookies.set("ssp_refresh", pair["refresh_token"], path="/auth")

        statuses = {
            "POST /auth/password/reset": client.post(
                "/auth/password/reset",
                json={"email": email, "code": "135791", "new_password": NEW_PASSWORD},
                headers=CSRF,
            ).status_code,
            "POST /auth/password/change": client.post(
                "/auth/password/change",
                json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
                headers=headers,
            ).status_code,
            "POST /auth/email/change": client.post(
                "/auth/email/change",
                json={
                    "password": PASSWORD,
                    "old_email_code": "111111",
                    "new_email": f"{self.PREFIX}rtn@example.com",
                    "new_email_code": "222222",
                },
                headers=headers2,
            ).status_code,
            "GET /auth/sessions": client.get(
                "/auth/sessions", headers=headers
            ).status_code,
            "GET /auth/sessions/current": client.get(
                "/auth/sessions/current", headers=headers
            ).status_code,
            "POST /auth/sessions/revoke-others": client.post(
                "/auth/sessions/revoke-others",
                json={"password": PASSWORD},
                headers=headers,
            ).status_code,
            "POST /auth/sessions/{id}/revoke": client.post(
                f"/auth/sessions/{uuid.uuid4()}/revoke",
                json={"password": PASSWORD},
                headers=headers,
            ).status_code,
            "POST /auth/logout-all": client.post(
                "/auth/logout-all", json={"password": PASSWORD}, headers=headers
            ).status_code,
        }
        broken = {k: v for k, v in statuses.items() if v >= 500}
        self.assertEqual(broken, {}, f"存在 5xx 路由：{broken}")


# ======================================================================
# T1 忘记密码
# ======================================================================


class TestT1ForgotPassword(BaseA2):
    def _user_with_code(self, suffix, code="135791"):
        uid, username, email = self.make_user(suffix)
        self.reset_code(email, code, uid)
        return uid, username, email

    def test_reset_success(self):
        uid, username, email = self._user_with_code("r1")
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_reset_updates_hash_and_time(self):
        uid, _, email = self._user_with_code("r2")
        before = self._user_row(uid)
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        after = self._user_row(uid)
        self.assertNotEqual(before["password_hash"], after["password_hash"])
        self.assertGreaterEqual(after["password_updated_at"], before["password_updated_at"])

    def test_old_password_invalid_new_password_valid(self):
        uid, username, email = self._user_with_code("r3")
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        try:
            self.login(username, PASSWORD)
            old_ok = True
        except Exception:
            old_ok = False
        self.assertFalse(old_ok, "旧密码重置后仍可登录")
        pair, _ = self.login(username, NEW_PASSWORD)
        self.assertTrue(pair["access_token"])

    def test_reset_revokes_all_sessions_and_tokens(self):
        uid, username, email = self._user_with_code("r4")
        self.login(username)
        self.login(username)
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(self._active_session_count(uid), 0)
        self.assertEqual(self._active_token_count(uid), 0)

    def test_old_access_fails_after_reset(self):
        uid, username, email = self._user_with_code("r5")
        old_pair, _ = self.login(username)
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        resp = client.get("/users/me", headers=self.bearer(old_pair))
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_reset_consumes_code_once(self):
        uid, _, email = self._user_with_code("r6")
        client = self.new_client()
        payload = {"email": email, "code": "135791", "new_password": NEW_PASSWORD}
        first = self.post_json(client, "/auth/password/reset", payload)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.post_json(client, "/auth/password/reset", payload)
        self.assertEqual(second.status_code, 400, second.text)

    def test_reset_does_not_create_session(self):
        uid, _, email = self._user_with_code("r7")
        before = self._active_session_count(uid)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self._active_session_count(uid), before)

    def test_reset_nonexistent_email_rejected(self):
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": f"{self.PREFIX}ghost@example.com", "code": "135791",
             "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_reset_disabled_account_rejected(self):
        uid, _, email = self.make_user("r8", active=False)
        self.reset_code(email, "135791", uid)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_reset_rejects_login_purpose_code(self):
        uid, _, email = self.make_user("r9")
        self.mk_code(email, EmailCodePurpose.LOGIN, "135791", user_id=uid)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_reset_wrong_code_attempts_persisted(self):
        uid, _, email = self.make_user("ra")
        vid = self.reset_code(email, "135791", uid)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "000000", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        with engine.connect() as conn:
            attempts = conn.execute(
                text("SELECT attempts FROM email_verifications WHERE id = :i"),
                {"i": vid},
            ).scalar_one()
        self.assertEqual(attempts, 1)

    def test_reset_weak_password_rejected(self):
        uid, _, email = self._user_with_code("rb")
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email, "code": "135791", "new_password": "12345678"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_reset_rollback_on_failure(self):
        uid, _, email = self.make_user("rr")
        vid = self.reset_code(email, "135791", uid)
        before = self._user_row(uid)
        with mock.patch(
            "app.services.auth.session_service.revoke_user_sessions",
            side_effect=RuntimeError("boom"),
        ):
            with SessionLocal() as db:
                with self.assertRaises(RuntimeError):
                    account_service.reset_password(
                        db,
                        data=PasswordResetRequest(
                            email=email, code="135791",
                            new_password=NEW_PASSWORD,
                        ),
                        ip="10.5.0.1",
                    )
        after = self._user_row(uid)
        self.assertEqual(before["password_hash"], after["password_hash"])
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT consumed_at FROM email_verifications WHERE id = :i"),
                {"i": vid},
            ).mappings().first()
        self.assertIsNone(row["consumed_at"])

    def test_reset_does_not_clear_other_account_cookie(self):
        uid_a, _, email_a = self.make_user("ro")
        self.reset_code(email_a, "135791", uid_a)
        uid_b, name_b, _ = self.make_user("ro2")
        pair_b, _ = self.login(name_b)
        client = self.new_client()
        client.cookies.set("ssp_refresh", pair_b["refresh_token"], path="/auth")
        resp = self.post_json(
            client,
            "/auth/password/reset",
            {"email": email_a, "code": "135791", "new_password": NEW_PASSWORD},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            client.cookies.get("ssp_refresh"), pair_b["refresh_token"],
            "重置其他账号不应清除本账号 Cookie",
        )

    def test_reset_concurrent_consume_once(self):
        uid, _, email = self.make_user("rc")
        self.reset_code(email, "135791", uid)

        def do(i):
            with SessionLocal() as db:
                return account_service.reset_password(
                    db,
                    data=PasswordResetRequest(
                        email=email, code="135791",
                        new_password=NEW_PASSWORD,
                    ),
                    ip=f"10.5.1.{i + 1}",
                )

        results = self.run_concurrent(do, 2)
        self.assertEqual(self.ok_count(results), 1, results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM email_verifications "
                "WHERE email = :e AND purpose = 'RESET_PASSWORD' "
                "AND consumed_at IS NOT NULL",
                {"e": email},
            ),
            1,
        )

    # ---- 内部 ----

    def _user_row(self, uid):
        with engine.connect() as conn:
            return dict(
                conn.execute(
                    text("SELECT * FROM users WHERE id = :i"), {"i": uid}
                ).mappings().first()
            )

    def _active_session_count(self, uid):
        with engine.connect() as conn:
            return int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM login_sessions "
                        "WHERE user_id = :i AND revoked_at IS NULL"
                    ),
                    {"i": uid},
                ).scalar_one()
            )

    def _active_token_count(self, uid):
        with engine.connect() as conn:
            return int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM refresh_tokens "
                        "WHERE user_id = :i AND revoked_at IS NULL"
                    ),
                    {"i": uid},
                ).scalar_one()
            )


# ======================================================================
# T2 主动修改密码
# ======================================================================


class TestT2ChangePassword(BaseA2):
    def test_change_with_correct_old_password(self):
        uid, username, _ = self.make_user("c1")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_change_with_wrong_old_password(self):
        uid, username, _ = self.make_user("c2")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": "WrongPass999", "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertIn(resp.status_code, (400, 401), resp.text)
        self.assertEqual(resp.json().get("detail", {}).get("code"), "INVALID_PASSWORD")

    def test_change_wrong_password_records_failure(self):
        uid, username, _ = self.make_user("c3")
        pair, _ = self.login(username)
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/change",
            {"old_password": "WrongPass999", "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events WHERE user_id = :i "
                "AND event_type = 'PASSWORD_FAILED'",
                {"i": uid},
            ),
            1,
        )

    def test_change_shares_failure_counter_with_login(self):
        uid, username, _ = self.make_user("c4")
        pair, _ = self.login(username)
        client = self.new_client()
        for _ in range(2):
            self.post_json(
                client,
                "/auth/password/change",
                {"old_password": "WrongPass999", "new_password": NEW_PASSWORD},
                self.bearer(pair),
            )
        for _ in range(2):
            try:
                self.login(username, "WrongPass999")
            except Exception:
                pass
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events WHERE user_id = :i "
                "AND event_type = 'PASSWORD_FAILED'",
                {"i": uid},
            ),
            4,
        )

    def test_change_keeps_current_session(self):
        uid, username, _ = self.make_user("c5")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": family},
            ).scalar_one()
        self.assertIsNone(revoked)

    def test_change_tokens_still_valid(self):
        uid, username, _ = self.make_user("c6")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        client.cookies.set("ssp_refresh", pair["refresh_token"], path="/auth")
        self.assertEqual(
            client.get("/users/me", headers=self.bearer(pair)).status_code, 200
        )
        refreshed = client.post("/auth/refresh", headers=CSRF)
        self.assertEqual(refreshed.status_code, 200, refreshed.text)

    def test_change_revokes_other_sessions(self):
        uid, username, _ = self.make_user("c7")
        current, _ = self.login(username)
        other, _ = self.login(username)
        other_family = security.decode_access_token(other["access_token"])["family_id"]
        client = self.new_client()
        self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(current),
        )
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": other_family},
            ).scalar_one()
        self.assertIsNotNone(revoked)

    def test_change_requires_active_session(self):
        uid, username, _ = self.make_user("c8")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family,
                    now=utc_db_now(), reason="TEST",
                )
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_change_disabled_user_denied(self):
        uid, username, _ = self.make_user("c9")
        pair, _ = self.login(username)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET is_active = 0 WHERE id = :i"), {"i": uid}
            )
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/password/change",
            {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
            self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_change_rechecks_session_after_auth(self):
        uid, username, _ = self.make_user("ck")
        pair, _ = self.login(username)
        family = self._family(pair)
        before = self._hash(uid)
        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family,
                    now=utc_db_now(), reason="TEST",
                )
        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as ctx:
                account_service.change_password(
                    db,
                    user_id=uid,
                    family_id=family,
                    data=PasswordChangeRequest(
                        old_password=PASSWORD, new_password=NEW_PASSWORD,
                    ),
                    ip="10.6.0.1",
                )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(self._hash(uid), before)

    def test_change_does_not_leave_partial_state(self):
        uid, username, _ = self.make_user("cp")
        pair, _ = self.login(username)
        family = self._family(pair)
        before = self._hash(uid)
        with mock.patch(
            "app.services.auth.session_service.revoke_user_sessions",
            side_effect=RuntimeError("boom"),
        ):
            with SessionLocal() as db:
                with self.assertRaises(RuntimeError):
                    account_service.change_password(
                        db,
                        user_id=uid,
                        family_id=family,
                        data=PasswordChangeRequest(
                            old_password=PASSWORD, new_password=NEW_PASSWORD,
                        ),
                        ip="10.6.0.2",
                    )
        self.assertEqual(self._hash(uid), before)
        self.assertIsNone(self.get_session_row(family)["revoked_at"])

    def _hash(self, uid):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT password_hash FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()


# ======================================================================
# T3 邮箱换绑
# ======================================================================


class TestT3ChangeEmail(BaseA2):
    def _prepare(self, suffix, old_code="111111", new_code="222222"):
        uid, username, email = self.make_user(suffix)
        new_email = f"{self.PREFIX}{suffix}n@example.com"
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.change_codes(email, new_email, uid, old_code, new_code, family_id=family)
        return uid, username, email, new_email, pair

    def _change(self, client, pair, payload):
        return self.post_json(client, "/auth/email/change", payload, self.bearer(pair))

    def test_change_email_success(self):
        uid, _, email, new_email, pair = self._prepare("m1")
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_change_email_updates_verified_at(self):
        uid, _, email, new_email, pair = self._prepare("m2")
        client = self.new_client()
        self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT email, email_verified_at FROM users WHERE id = :i"),
                {"i": uid},
            ).mappings().first()
        self.assertEqual(row["email"], new_email)
        self.assertIsNotNone(row["email_verified_at"])

    def test_change_email_keeps_current_session_and_revokes_others(self):
        uid, username, email, new_email, pair = self._prepare("m3")
        other, _ = self.login(username)
        other_family = security.decode_access_token(other["access_token"])["family_id"]
        client = self.new_client()
        self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        with engine.connect() as conn:
            current_revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": security.decode_access_token(pair["access_token"])["family_id"]},
            ).scalar_one()
            other_revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": other_family},
            ).scalar_one()
        self.assertIsNone(current_revoked)
        self.assertIsNotNone(other_revoked)

    def test_old_email_login_fails_new_email_works(self):
        uid, username, email, new_email, pair = self._prepare("m4")
        client = self.new_client()
        self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        with SessionLocal() as db:
            with self.assertRaises(Exception):
                from app.services.auth import auth_service

                auth_service.login_with_password(
                    db, identifier=email, password=PASSWORD,
                    ip="127.0.0.1", user_agent="ua",
                )
        with SessionLocal() as db:
            from app.services.auth import auth_service

            _, user = auth_service.login_with_password(
                db, identifier=new_email, password=PASSWORD,
                ip="127.0.0.1", user_agent="ua",
            )
        self.assertEqual(user["id"], uid)

    def test_new_email_equals_old_rejected(self):
        uid, username, email = self.make_user("m5")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.mk_code(email, EmailCodePurpose.CHANGE_EMAIL_OLD, "111111", user_id=uid, family_id=family)
        self.mk_code(email, EmailCodePurpose.CHANGE_EMAIL_NEW, "222222", user_id=uid, family_id=family)
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_new_email_taken_rejected(self):
        uid, username, email = self.make_user("m6")
        other_uid, _, other_email = self.make_user("m6o")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.change_codes(email, other_email, uid, "111111", "222222", family_id=family)
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": other_email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    def test_code_bound_to_other_user_rejected(self):
        uid, username, email = self.make_user("m7")
        other_uid, _, other_email = self.make_user("m7o")
        new_email = f"{self.PREFIX}m7n@example.com"
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        # 旧邮箱验证码绑定到其他用户
        self.mk_code(
            email, EmailCodePurpose.CHANGE_EMAIL_OLD, "111111", user_id=other_uid, family_id=family
        )
        self.mk_code(
            new_email, EmailCodePurpose.CHANGE_EMAIL_NEW, "222222", user_id=uid, family_id=family
        )
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_purposes_cannot_be_mixed(self):
        uid, username, email = self.make_user("m8")
        new_email = f"{self.PREFIX}m8n@example.com"
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        # 旧邮箱使用 NEW 用途、新邮箱使用 OLD 用途
        self.mk_code(
            email, EmailCodePurpose.CHANGE_EMAIL_NEW, "111111", user_id=uid, family_id=family
        )
        self.mk_code(
            new_email, EmailCodePurpose.CHANGE_EMAIL_OLD, "222222", user_id=uid, family_id=family
        )
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_wrong_old_code_records_attempts(self):
        uid, username, email = self.make_user("m9")
        new_email = f"{self.PREFIX}m9n@example.com"
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.change_codes(email, new_email, uid, "111111", "222222", family_id=family)
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "999999",
                "new_email": new_email,
                "new_email_code": "222222",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM email_verifications "
                "WHERE email = :e AND purpose = 'CHANGE_EMAIL_OLD' AND attempts >= 1",
                {"e": email},
            ),
            1,
        )

    def test_wrong_new_code_keeps_old_code_unconsumed(self):
        uid, username, email = self.make_user("ma")
        new_email = f"{self.PREFIX}man@example.com"
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.change_codes(email, new_email, uid, "111111", "222222", family_id=family)
        client = self.new_client()
        resp = self._change(
            client,
            pair,
            {
                "password": PASSWORD,
                "old_email_code": "111111",
                "new_email": new_email,
                "new_email_code": "999999",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        with engine.connect() as conn:
            consumed = conn.execute(
                text(
                    "SELECT consumed_at FROM email_verifications "
                    "WHERE email = :e AND purpose = 'CHANGE_EMAIL_OLD'"
                ),
                {"e": email},
            ).scalar_one()
        self.assertIsNone(consumed)

    def test_both_codes_in_same_transaction(self):
        uid, username, email, new_email, pair = self._prepare("tt")
        family = self._family(pair)
        with mock.patch(
            "app.services.auth.account_service.user_repository.update_email",
            side_effect=RuntimeError("boom"),
        ):
            with SessionLocal() as db:
                with self.assertRaises(RuntimeError):
                    account_service.change_email(
                        db,
                        user_id=uid,
                        family_id=family,
                        data=EmailChangeRequest(
                            password=PASSWORD,
                            old_email_code="111111",
                            new_email=new_email,
                            new_email_code="222222",
                        ),
                        ip="10.7.0.1",
                    )
        self.assertEqual(self._email_of(uid), email)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM email_verifications "
                "WHERE email IN (:o, :n) AND purpose LIKE 'CHANGE_EMAIL%' "
                "AND consumed_at IS NOT NULL",
                {"o": email, "n": new_email},
            ),
            0,
        )

    def test_concurrent_same_new_email_only_one(self):
        target = f"{self.PREFIX}race@example.com"
        u1, n1, e1 = self.make_user("ra1")
        p1, _ = self.login(n1)
        f1 = self._family(p1)
        u2, n2, e2 = self.make_user("ra2")
        p2, _ = self.login(n2)
        f2 = self._family(p2)
        pairs = {0: (u1, e1, f1), 1: (u2, e2, f2)}
        for i, (uid, old_email, fam) in pairs.items():
            self.mk_code(
                old_email, EmailCodePurpose.CHANGE_EMAIL_OLD, "111111",
                user_id=uid, family_id=fam,
            )
            self.mk_code(
                target, EmailCodePurpose.CHANGE_EMAIL_NEW, "222222",
                user_id=uid, family_id=fam,
            )

        def do(i):
            uid, _, fam = pairs[i]
            with SessionLocal() as db:
                return account_service.change_email(
                    db,
                    user_id=uid,
                    family_id=fam,
                    data=EmailChangeRequest(
                        password=PASSWORD,
                        old_email_code="111111",
                        new_email=target,
                        new_email_code="222222",
                    ),
                    ip=f"10.7.1.{i + 1}",
                )

        results = self.run_concurrent(do, 2)
        self.assertEqual(self.ok_count(results), 1, results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM users WHERE email = :e", {"e": target}
            ),
            1,
        )

    def test_unique_conflict_maps_409(self):
        uid, username, email, new_email, pair = self._prepare("uc")
        family = self._family(pair)
        fake_orig = Exception(1062, "Duplicate entry 'x' for key 'uk_users_email'")
        fake_ie = IntegrityError("UPDATE users SET email = :e", {}, fake_orig)
        with mock.patch(
            "app.services.auth.account_service.user_repository.update_email",
            side_effect=fake_ie,
        ):
            with SessionLocal() as db:
                with self.assertRaises(HTTPException) as ctx:
                    account_service.change_email(
                        db,
                        user_id=uid,
                        family_id=family,
                        data=EmailChangeRequest(
                            password=PASSWORD,
                            old_email_code="111111",
                            new_email=new_email,
                            new_email_code="222222",
                        ),
                        ip="10.7.2.1",
                    )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["code"], "EMAIL_UNAVAILABLE")

    def test_old_email_code_cannot_bypass_binding(self):
        uid, username, email, new_email, pair = self._prepare("by")
        family = self._family(pair)
        with SessionLocal() as db:
            account_service.change_email(
                db,
                user_id=uid,
                family_id=family,
                data=EmailChangeRequest(
                    password=PASSWORD,
                    old_email_code="111111",
                    new_email=new_email,
                    new_email_code="222222",
                ),
                ip="10.7.3.1",
            )
        self.assertEqual(self._email_of(uid), new_email)
        # 再为“原邮箱”签发一枚旧邮箱验证码
        self.mk_code(
            email, EmailCodePurpose.CHANGE_EMAIL_OLD, "999999",
            user_id=uid, family_id=family,
        )
        second_new = f"{self.PREFIX}byn2@example.com"
        self.mk_code(
            second_new, EmailCodePurpose.CHANGE_EMAIL_NEW, "888888",
            user_id=uid, family_id=family,
        )
        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as ctx:
                account_service.change_email(
                    db,
                    user_id=uid,
                    family_id=family,
                    data=EmailChangeRequest(
                        password=PASSWORD,
                        old_email_code="999999",
                        new_email=second_new,
                        new_email_code="888888",
                    ),
                    ip="10.7.3.2",
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self._email_of(uid), new_email)

    def _email_of(self, uid):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT email FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()


# ======================================================================
# T4 登录会话查询
# ======================================================================


class TestT4SessionList(BaseA2):
    def test_list_sessions(self):
        uid, username, _ = self.make_user("l1")
        pair, _ = self.login(username)
        self.login(username)
        client = self.new_client()
        resp = client.get("/auth/sessions", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertGreaterEqual(len(data["items"]), 2)

    def test_list_excludes_revoked_and_expired(self):
        uid, username, _ = self.make_user("l2")
        pair, _ = self.login(username)
        other, _ = self.login(username)
        other_family = security.decode_access_token(other["access_token"])["family_id"]
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET revoked_at = :t WHERE family_id = :f"
                ),
                {"t": utc_db_now(), "f": other_family},
            )
        client = self.new_client()
        resp = client.get("/auth/sessions", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)
        families = [s["family_id"] for s in resp.json()["data"]["items"]]
        self.assertNotIn(other_family, families)

    def test_total_matches_page(self):
        uid, username, _ = self.make_user("l3")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = client.get(
            "/auth/sessions?page=1&page_size=1", headers=self.bearer(pair)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()["data"]
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["total"], 1)

    def test_page_boundaries(self):
        uid, username, _ = self.make_user("l4")
        pair, _ = self.login(username)
        client = self.new_client()
        self.assertEqual(
            client.get("/auth/sessions?page=0", headers=self.bearer(pair)).status_code,
            422,
        )
        self.assertEqual(
            client.get(
                "/auth/sessions?page_size=101", headers=self.bearer(pair)
            ).status_code,
            422,
        )

    def test_current_flag(self):
        uid, username, _ = self.make_user("l5")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        client = self.new_client()
        resp = client.get("/auth/sessions", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)
        current = [s for s in resp.json()["data"]["items"] if s["is_current"]]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["family_id"], family)

    def test_no_sensitive_fields(self):
        uid, username, _ = self.make_user("l6")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = client.get("/auth/sessions", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)
        text_body = resp.text
        for bad in ("password_hash", "refresh_token", "token_hash"):
            self.assertNotIn(bad, text_body)

    def test_current_session_probe(self):
        uid, username, _ = self.make_user("l7")
        pair, _ = self.login(username)
        client = self.new_client()
        resp = client.get("/auth/sessions/current", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_probe_does_not_touch_activity(self):
        uid, username, _ = self.make_user("l8")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        self.backdate_activity(family, 400)
        before = self.get_session_row(family)["last_activity_at"]
        client = self.new_client()
        resp = client.get("/auth/sessions/current", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200, resp.text)
        after = self.get_session_row(family)["last_activity_at"]
        self.assertEqual(before, after)

    def test_invalid_session_cannot_list(self):
        uid, username, _ = self.make_user("l9")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family,
                    now=utc_db_now(), reason="TEST",
                )
        client = self.new_client()
        resp = client.get("/auth/sessions", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 401, resp.text)


# ======================================================================
# T5 远程撤销指定设备
# ======================================================================


class TestT5RevokeSession(BaseA2):
    def test_revoke_other_session(self):
        uid, username, _ = self.make_user("v1")
        current, _ = self.login(username)
        target, _ = self.login(username)
        target_family = security.decode_access_token(target["access_token"])[
            "family_id"
        ]
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{target_family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_wrong_password_revokes_nothing(self):
        uid, username, _ = self.make_user("v2")
        current, _ = self.login(username)
        target, _ = self.login(username)
        target_family = security.decode_access_token(target["access_token"])[
            "family_id"
        ]
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{target_family}/revoke",
            {"password": "WrongPass999"},
            self.bearer(current),
        )
        self.assertIn(resp.status_code, (400, 401), resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": target_family},
            ).scalar_one()
        self.assertIsNone(revoked)

    def test_cannot_revoke_other_users_session(self):
        uid, username, _ = self.make_user("v3")
        other_uid, other_name, _ = self.make_user("v3o")
        current, _ = self.login(username)
        other, _ = self.login(other_name)
        other_family = security.decode_access_token(other["access_token"])["family_id"]
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{other_family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertIn(resp.status_code, (403, 404, 400), resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": other_family},
            ).scalar_one()
        self.assertIsNone(revoked)

    def test_cannot_revoke_current_session(self):
        uid, username, _ = self.make_user("v4")
        current, _ = self.login(username)
        family = security.decode_access_token(current["access_token"])["family_id"]
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertGreaterEqual(resp.status_code, 400, resp.text)
        self.assertLess(resp.status_code, 500, resp.text)

    def test_target_old_access_fails(self):
        uid, username, _ = self.make_user("v5")
        current, _ = self.login(username)
        target, _ = self.login(username)
        target_family = security.decode_access_token(target["access_token"])[
            "family_id"
        ]
        client = self.new_client()
        self.post_json(
            client,
            f"/auth/sessions/{target_family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        resp = client.get("/users/me", headers=self.bearer(target))
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_other_sessions_unaffected(self):
        uid, username, _ = self.make_user("v6")
        current, _ = self.login(username)
        target, _ = self.login(username)
        third, _ = self.login(username)
        target_family = security.decode_access_token(target["access_token"])[
            "family_id"
        ]
        third_family = security.decode_access_token(third["access_token"])["family_id"]
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{target_family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": third_family},
            ).scalar_one()
        self.assertIsNone(revoked)

    def test_already_revoked_target_business_error(self):
        uid, username, _ = self.make_user("v7")
        current, _ = self.login(username)
        target, _ = self.login(username)
        target_family = security.decode_access_token(target["access_token"])[
            "family_id"
        ]
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET revoked_at = :t WHERE family_id = :f"
                ),
                {"t": utc_db_now(), "f": target_family},
            )
        client = self.new_client()
        resp = self.post_json(
            client,
            f"/auth/sessions/{target_family}/revoke",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertIn(resp.status_code, (400, 404), resp.text)
        # 当前会话不应被误判失效
        me = client.get("/users/me", headers=self.bearer(current))
        self.assertEqual(me.status_code, 200, me.text)

    def test_concurrent_revoke_and_refresh(self):
        uid, username, _ = self.make_user("cr")
        current, _ = self.login(username)
        target, _ = self.login(username)
        cur_family = self._family(current)
        tgt_family = self._family(target)

        def do(i):
            with SessionLocal() as db:
                if i == 0:
                    account_service.revoke_other_session(
                        db,
                        user_id=uid,
                        current_family_id=cur_family,
                        target_family_id=tgt_family,
                        password=PASSWORD,
                        ip="10.8.0.1",
                    )
                    return "revoked"
                return auth_service.rotate_refresh_token(
                    db, refresh_token=target["refresh_token"], ip="10.8.0.2"
                )

        self.run_concurrent(do, 2)
        self.assertIsNotNone(
            self.get_session_row(tgt_family)["revoked_at"],
            "目标会话最终必须处于撤销状态",
        )
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM refresh_tokens "
                "WHERE family_id = :f AND revoked_at IS NULL",
                {"f": tgt_family},
            ),
            0,
            "撤销后目标会话不应残留可用 Refresh Token",
        )


# ======================================================================
# T6 退出其他设备 / 退出全部设备
# ======================================================================


class TestT6LogoutDevices(BaseA2):
    def test_revoke_others_keep_current(self):
        uid, username, _ = self.make_user("o1")
        current, _ = self.login(username)
        self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/sessions/revoke-others",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("revoked_count", resp.json()["data"])

    def test_revoke_others_wrong_password(self):
        uid, username, _ = self.make_user("o2")
        current, _ = self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/sessions/revoke-others",
            {"password": "WrongPass999"},
            self.bearer(current),
        )
        self.assertIn(resp.status_code, (400, 401), resp.text)

    def test_logout_all_revokes_everything(self):
        uid, username, _ = self.make_user("o3")
        current, _ = self.login(username)
        self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client, "/auth/logout-all", {"password": PASSWORD}, self.bearer(current)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM login_sessions "
                "WHERE user_id = :i AND revoked_at IS NULL",
                {"i": uid},
            ),
            0,
        )

    def test_revoked_count_matches_db(self):
        uid, username, _ = self.make_user("o4")
        current, _ = self.login(username)
        self.login(username)
        self.login(username)
        client = self.new_client()
        resp = self.post_json(
            client,
            "/auth/sessions/revoke-others",
            {"password": PASSWORD},
            self.bearer(current),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["data"]["revoked_count"], 2)

    def test_cannot_touch_other_user(self):
        uid, username, _ = self.make_user("o5")
        other_uid, other_name, _ = self.make_user("o5o")
        current, _ = self.login(username)
        other, _ = self.login(other_name)
        client = self.new_client()
        resp = self.post_json(
            client, "/auth/logout-all", {"password": PASSWORD}, self.bearer(current)
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text(
                    "SELECT COUNT(*) FROM login_sessions "
                    "WHERE user_id = :i AND revoked_at IS NULL"
                ),
                {"i": other_uid},
            ).scalar_one()
        self.assertEqual(revoked, 1)

    def test_logout_all_requires_password(self):
        uid, username, _ = self.make_user("o6")
        current, _ = self.login(username)
        client = self.new_client()
        resp = client.post(
            "/auth/logout-all", json={}, headers={**CSRF, **self.bearer(current)}
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_old_passwordless_logout_all_gone(self):
        client = self.new_client()
        resp = client.post("/auth/logout-all", headers=CSRF)
        self.assertIn(resp.status_code, (401, 403, 422), resp.text)

    def test_atomicity(self):
        uid, username, _ = self.make_user("at")
        current, _ = self.login(username)
        self.login(username)
        self.login(username)
        family = self._family(current)
        active = "SELECT COUNT(*) FROM login_sessions WHERE user_id = :i AND revoked_at IS NULL"
        self.assertEqual(self.count(active, {"i": uid}), 3)
        with mock.patch(
            "app.services.auth.session_service.revoke_user_sessions",
            side_effect=RuntimeError("boom"),
        ):
            with SessionLocal() as db:
                with self.assertRaises(RuntimeError):
                    account_service.revoke_sessions(
                        db,
                        user_id=uid,
                        current_family_id=family,
                        password=PASSWORD,
                        ip="10.9.0.1",
                        keep_current=False,
                    )
        self.assertEqual(self.count(active, {"i": uid}), 3)


# ======================================================================
# T7 并发与安全审查
# ======================================================================


class TestT7ConcurrencySecurity(BaseA2):
    def test_lock_order_reserve_before_row_lock(self):
        for fn in (account_service.change_password, account_service.change_email):
            src = inspect.getsource(fn)
            reserve = min(
                src.find("reserve_password_attempt"),
                src.find("reserve_email_code_attempt"),
            )
            reserve = reserve if reserve >= 0 else 0
            begin = src.find("with db.begin()")
            self.assertGreater(
                begin,
                reserve,
                f"{fn.__name__}: IP 准入应在用户行锁之前",
            )

    def test_reset_reserve_before_transaction(self):
        src = inspect.getsource(account_service.reset_password)
        self.assertLess(
            src.find("reserve_email_code_attempt"),
            src.find("with db.begin()"),
        )

    def test_error_codes_distinguish_causes(self):
        # 会话失效 → SESSION_REVOKED；普通密码错误 → INVALID_CREDENTIALS
        uid, username, _ = self.make_user("x1")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        with SessionLocal() as db:
            with db.begin():
                session_service.revoke_session(
                    db, user_id=uid, family_id=family,
                    now=utc_db_now(), reason="TEST",
                )
        client = self.new_client()
        revoked = client.get("/users/me", headers=self.bearer(pair))
        self.assertEqual(revoked.status_code, 401)
        self.assertEqual(
            revoked.json()["detail"]["code"], "SESSION_REVOKED"
        )

        bad_login = client.post(
            "/auth/login",
            data={"username": username, "password": "WrongPass999"},
            headers=CSRF,
        )
        self.assertEqual(bad_login.status_code, 401)
        self.assertEqual(
            bad_login.json()["detail"]["code"], "INVALID_CREDENTIALS"
        )

    def test_logout_missing_cookie(self):
        client = self.new_client()
        resp = client.post("/auth/logout", headers=CSRF)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_logout_invalid_cookie(self):
        uid, username, _ = self.make_user("x2")
        pair, _ = self.login(username)
        family = security.decode_access_token(pair["access_token"])["family_id"]
        client = self.new_client()
        client.cookies.set("ssp_refresh", "garbage-token", path="/auth")
        resp = client.post("/auth/logout", headers=CSRF)
        self.assertEqual(resp.status_code, 200, resp.text)
        with engine.connect() as conn:
            revoked = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": family},
            ).scalar_one()
        self.assertIsNone(revoked, "无效 Cookie 不应撤销任何会话")

    def test_logout_cookie_mismatch_with_bearer(self):
        uid_a, name_a, _ = self.make_user("x3")
        uid_b, name_b, _ = self.make_user("x3o")
        pair_a, _ = self.login(name_a)
        pair_b, _ = self.login(name_b)
        family_a = security.decode_access_token(pair_a["access_token"])["family_id"]
        family_b = security.decode_access_token(pair_b["access_token"])["family_id"]

        client = self.new_client()
        client.cookies.set("ssp_refresh", pair_b["refresh_token"], path="/auth")
        resp = client.post(
            "/auth/logout", headers={**CSRF, **self.bearer(pair_a)}
        )
        # 当前实现：Cookie 与 Bearer 会话不一致时拒绝（409），不撤销任何会话
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(
            resp.json().get("detail", {}).get("code"), "SESSION_MISMATCH"
        )
        with engine.connect() as conn:
            a = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": family_a},
            ).scalar_one()
            b = conn.execute(
                text("SELECT revoked_at FROM login_sessions WHERE family_id = :f"),
                {"f": family_b},
            ).scalar_one()
        self.assertIsNone(a)
        self.assertIsNone(b)

    def test_concurrent_password_change_same_user(self):
        uid, username, _ = self.make_user("pc")
        d1, _ = self.login(username)
        d2, _ = self.login(username)
        fams = [self._family(d1), self._family(d2)]
        newps = ["NewPass456", "OtherPass789"]

        def do(i):
            with SessionLocal() as db:
                account_service.change_password(
                    db,
                    user_id=uid,
                    family_id=fams[i],
                    data=PasswordChangeRequest(
                        old_password=PASSWORD, new_password=newps[i],
                    ),
                    ip=f"10.10.0.{i + 1}",
                )

        results = self.run_concurrent(do, 2)
        self.assertEqual(self.ok_count(results), 1, results)
        winner = 0 if results[0][0] == "ok" else 1
        self.assertTrue(security.verify_password(newps[winner], self._hash(uid)))

    def test_concurrent_reset_and_login(self):
        uid, username, email = self.make_user("rl")
        self.reset_code(email, "135791", uid)

        def do(i):
            with SessionLocal() as db:
                if i == 0:
                    return account_service.reset_password(
                        db,
                        data=PasswordResetRequest(
                            email=email, code="135791",
                            new_password=NEW_PASSWORD,
                        ),
                        ip="10.10.1.1",
                    )
                return auth_service.login_with_password(
                    db, identifier=username, password=PASSWORD,
                    ip="10.10.1.2", user_agent="ua",
                )

        results = self.run_concurrent(do, 2)
        self.assertEqual(results[0][0], "ok", results)
        with self.assertRaises(Exception):
            self.login(username, PASSWORD)
        pair, _ = self.login(username, NEW_PASSWORD)
        self.assertTrue(pair["access_token"])

    def test_concurrent_email_change_and_code_login(self):
        uid, username, email, new_email, pair = self._prepare("cl")
        family = self._family(pair)
        self.mk_code(email, EmailCodePurpose.LOGIN, "333333", user_id=uid)

        def do(i):
            with SessionLocal() as db:
                if i == 0:
                    return account_service.change_email(
                        db,
                        user_id=uid,
                        family_id=family,
                        data=EmailChangeRequest(
                            password=PASSWORD,
                            old_email_code="111111",
                            new_email=new_email,
                            new_email_code="222222",
                        ),
                        ip="10.10.2.1",
                    )
                return auth_service.login_with_email(
                    db, email=email, code="333333",
                    ip="10.10.2.2", user_agent="ua",
                )

        results = self.run_concurrent(do, 2)
        self.assertEqual(results[0][0], "ok", results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM login_sessions "
                "WHERE user_id = :i AND revoked_at IS NULL",
                {"i": uid},
            ),
            1,
        )
        pair_new, _ = self.login(new_email, PASSWORD)
        self.assertTrue(pair_new["access_token"])
        with self.assertRaises(Exception):
            self.login(email, PASSWORD)

    def test_concurrent_email_change_and_resend(self):
        uid, username, email, new_email, pair = self._prepare("rs")
        family = self._family(pair)

        def do(i):
            if i == 0:
                with SessionLocal() as db:
                    return account_service.change_email(
                        db,
                        user_id=uid,
                        family_id=family,
                        data=EmailChangeRequest(
                            password=PASSWORD,
                            old_email_code="111111",
                            new_email=new_email,
                            new_email_code="222222",
                        ),
                        ip="10.10.3.1",
                    )
            return verification_service.request_email_code(
                email=new_email,
                purpose=EmailCodePurpose.CHANGE_EMAIL_NEW,
                request_ip="10.10.3.2",
                current_user_id=uid,
                current_family_id=family,
            )

        results = self.run_concurrent(do, 2)
        final = self._email_of(uid)
        self.assertIn(final, (email, new_email))
        if results[0][0] == "ok":
            self.assertEqual(final, new_email)
        else:
            self.assertEqual(final, email)

    def test_concurrent_failure_counter(self):
        uid, username, _ = self.make_user("fc")
        fams = [self._family(self.login(username)[0]) for _ in range(3)]

        def do(i):
            with SessionLocal() as db:
                account_service.change_password(
                    db,
                    user_id=uid,
                    family_id=fams[i],
                    data=PasswordChangeRequest(
                        old_password="WrongPass999", new_password=NEW_PASSWORD,
                    ),
                    ip=f"10.10.4.{i + 1}",
                )

        results = self.run_concurrent(do, 3)
        self.assertEqual(self.ok_count(results), 0, results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM auth_events "
                "WHERE user_id = :i AND event_type = 'PASSWORD_FAILED'",
                {"i": uid},
            ),
            3,
        )

    def test_multi_user_same_new_email_race(self):
        target = f"{self.PREFIX}multi@example.com"
        users = []
        for i in range(3):
            uid, name, email = self.make_user(f"mu{i}")
            fam = self._family(self.login(name)[0])
            self.mk_code(
                email, EmailCodePurpose.CHANGE_EMAIL_OLD, "111111",
                user_id=uid, family_id=fam,
            )
            self.mk_code(
                target, EmailCodePurpose.CHANGE_EMAIL_NEW, "222222",
                user_id=uid, family_id=fam,
            )
            users.append((uid, fam))

        def do(i):
            uid, fam = users[i]
            with SessionLocal() as db:
                return account_service.change_email(
                    db,
                    user_id=uid,
                    family_id=fam,
                    data=EmailChangeRequest(
                        password=PASSWORD,
                        old_email_code="111111",
                        new_email=target,
                        new_email_code="222222",
                    ),
                    ip=f"10.10.5.{i + 1}",
                )

        results = self.run_concurrent(do, 3)
        self.assertEqual(self.ok_count(results), 1, results)
        self.assertEqual(
            self.count(
                "SELECT COUNT(*) FROM users WHERE email = :e", {"e": target}
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)