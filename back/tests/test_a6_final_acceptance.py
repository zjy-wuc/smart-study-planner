"""V3.0 A6 最终验收：管理员安全、数据边界、Auth 契约与 AI 租约。

约束：
- 仅在隔离库 ssp_v3_admin_test 执行；不修改业务源码。
- 真实 Memurai；不执行 FLUSHALL/FLUSHDB。
- 复用 A4/A4.2/A3 已覆盖的行为，本文件只补 A6 缺口。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_a6_final_acceptance.py -q
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.core import security
from app.core.clock import business_today, utc_db_now
from app.database import SessionLocal, engine
from app.main import app as production_app
from app.repositories.knowledge import ai_guard_repository
from app.services.knowledge import ai_guard_service

ALLOWED_TEST_DBS = {"ssp_v3_admin_test"}
PREFIX = f"a6{uuid.uuid4().hex[:8]}"
PASSWORD = "A6Pass123456"
ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}
BASELINE = {"enabled": 1, "user_daily_limit": 10, "global_daily_limit": 80}


def _guard_database() -> None:
    with engine.connect() as conn:
        name = conn.execute(text("SELECT DATABASE()")).scalar_one()

    if name not in ALLOWED_TEST_DBS:
        raise RuntimeError(f"测试仅允许在隔离测试库执行，当前数据库: {name}")


_guard_database()


def _write_config() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ai_runtime_config SET enabled = :e, "
                "user_daily_limit = :u, global_daily_limit = :g "
                "WHERE id = 1"
            ),
            {
                "e": BASELINE["enabled"],
                "u": BASELINE["user_daily_limit"],
                "g": BASELINE["global_daily_limit"],
            },
        )


def _login(client: TestClient, username: str) -> dict:
    response = client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _error_code(response) -> str | None:
    body = response.json()

    detail = body.get("detail")

    if isinstance(detail, dict):
        return detail.get("code")

    return None


@pytest.fixture(scope="module", autouse=True)
def _raise_auth_ip_limits():
    old_pwd = settings.PASSWORD_IP_MAX_ATTEMPTS
    old_mail = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
    settings.PASSWORD_IP_MAX_ATTEMPTS = 10**9
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 10**9

    yield

    settings.PASSWORD_IP_MAX_ATTEMPTS = old_pwd
    settings.EMAIL_CODE_IP_MAX_ATTEMPTS = old_mail


@pytest.fixture(scope="module")
def world():
    client = TestClient(
        production_app,
        base_url="https://ssp.test",
        client=("127.0.0.1", 52501),
        raise_server_exceptions=False,
    )
    user_ids: list[int] = []
    old_key = settings.DEEPSEEK_API_KEY
    old_rate_limit = settings.AI_USER_RATE_LIMIT
    old_window = settings.AI_RATE_WINDOW_SECONDS

    def make_user(*, role: str = "USER") -> dict:
        username = f"{PREFIX}{uuid.uuid4().hex[:8]}"

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users ("
                    "username, password_hash, password_updated_at, "
                    "email, email_verified_at, nickname, role, created_at"
                    ") VALUES ("
                    ":username, :password_hash, :now, :email, :now, "
                    ":nickname, :role, CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "username": username,
                    "password_hash": security.hash_password(PASSWORD),
                    "now": utc_db_now(),
                    "email": f"{username}@example.com",
                    "nickname": username,
                    "role": role,
                },
            )
            user_id = int(result.lastrowid)

        user_ids.append(user_id)
        return {"id": user_id, "username": username}

    _write_config()
    settings.DEEPSEEK_API_KEY = "a6-sentinel-api-key"
    settings.AI_USER_RATE_LIMIT = 1000
    settings.AI_RATE_WINDOW_SECONDS = 60

    yield client, make_user

    _write_config()
    settings.DEEPSEEK_API_KEY = old_key
    settings.AI_USER_RATE_LIMIT = old_rate_limit
    settings.AI_RATE_WINDOW_SECONDS = old_window

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
                text(
                    "DELETE FROM admin_audit_logs WHERE admin_id = :i "
                    "OR (target_type = 'USER' AND target_id = :i)"
                ),
                {"i": user_id},
            )
            conn.execute(
                text("DELETE FROM users WHERE id = :i"),
                {"i": user_id},
            )


GET_ENDPOINTS = [
    "/admin/users",
    "/admin/audit-logs",
    "/admin/dashboard",
    "/admin/ai/statistics",
    "/admin/ai/config",
]


def test_admin_reads_require_admin_role(world):
    client, make_user = world
    normal = make_user()
    admin = make_user(role="ADMIN")

    normal_token = _login(client, normal["username"])["access_token"]
    admin_token = _login(client, admin["username"])["access_token"]

    for path in [*GET_ENDPOINTS, f"/admin/users/{normal['id']}"]:
        anonymous = client.get(path)
        assert anonymous.status_code == 401, (path, anonymous.text)

        forbidden = client.get(path, headers=_bearer(normal_token))
        assert forbidden.status_code == 403, (path, forbidden.text)
        assert _error_code(forbidden) == "ADMIN_REQUIRED"

        visible = client.get(path, headers=_bearer(admin_token))
        assert visible.status_code == 200, (path, visible.text)


def test_admin_writes_require_csrf_and_role(world):
    client, make_user = world
    normal = make_user()
    admin = make_user(role="ADMIN")

    normal_token = _login(client, normal["username"])["access_token"]
    admin_token = _login(client, admin["username"])["access_token"]
    target = make_user()

    body = {"reason": "A6 security check"}

    anonymous = client.post(
        f"/admin/users/{target['id']}/ban",
        json=body,
        headers=CSRF_HEADERS,
    )
    assert anonymous.status_code == 401, anonymous.text

    normal_write = client.post(
        f"/admin/users/{target['id']}/ban",
        json=body,
        headers={**_bearer(normal_token), **CSRF_HEADERS},
    )
    assert normal_write.status_code == 403, normal_write.text
    assert _error_code(normal_write) == "ADMIN_REQUIRED"

    missing_csrf = client.post(
        f"/admin/users/{target['id']}/ban",
        json=body,
        headers=_bearer(admin_token),
    )
    assert missing_csrf.status_code == 403, missing_csrf.text
    assert _error_code(missing_csrf) == "CSRF_REJECTED"

    patch_missing_csrf = client.patch(
        "/admin/ai/config",
        json={"enabled": True, "reason": "A6 csrf check"},
        headers=_bearer(admin_token),
    )
    assert patch_missing_csrf.status_code == 403
    assert _error_code(patch_missing_csrf) == "CSRF_REJECTED"

    patch_ok = client.patch(
        "/admin/ai/config",
        json={"enabled": True, "reason": "A6 csrf check"},
        headers={**_bearer(admin_token), **CSRF_HEADERS},
    )
    assert patch_ok.status_code == 200, patch_ok.text
    assert patch_ok.json()["data"]["changed"] is False


def test_admin_cannot_ban_admin_and_repeat_semantics(world):
    client, make_user = world
    admin = make_user(role="ADMIN")
    other_admin = make_user(role="ADMIN")
    target = make_user()

    admin_token = _login(client, admin["username"])["access_token"]
    headers = {**_bearer(admin_token), **CSRF_HEADERS}

    blocked = client.post(
        f"/admin/users/{other_admin['id']}/ban",
        json={"reason": "A6 cannot ban admin"},
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    assert _error_code(blocked) == "ADMIN_TARGET_FORBIDDEN"

    banned = client.post(
        f"/admin/users/{target['id']}/ban",
        json={"reason": "A6 ban"},
        headers=headers,
    )
    assert banned.status_code == 200, banned.text
    assert banned.json()["data"]["changed"] is True

    repeated_ban = client.post(
        f"/admin/users/{target['id']}/ban",
        json={"reason": "A6 ban again"},
        headers=headers,
    )
    assert repeated_ban.status_code == 409
    assert _error_code(repeated_ban) == "USER_ALREADY_DISABLED"

    unbanned = client.post(
        f"/admin/users/{target['id']}/unban",
        json={"reason": "A6 unban"},
        headers=headers,
    )
    assert unbanned.status_code == 200, unbanned.text

    repeated_unban = client.post(
        f"/admin/users/{target['id']}/unban",
        json={"reason": "A6 unban again"},
        headers=headers,
    )
    assert repeated_unban.status_code == 409
    assert _error_code(repeated_unban) == "USER_ALREADY_ACTIVE"

    no_session = client.post(
        f"/admin/users/{target['id']}/revoke-sessions",
        json={"reason": "A6 revoke none"},
        headers=headers,
    )
    assert no_session.status_code == 200, no_session.text
    assert no_session.json()["data"]["changed"] is False


def test_banned_and_revoked_tokens_are_rejected(world):
    client, make_user = world
    admin = make_user(role="ADMIN")
    victim = make_user()
    revoked = make_user()

    admin_token = _login(client, admin["username"])["access_token"]
    victim_token = _login(client, victim["username"])["access_token"]
    revoked_token = _login(client, revoked["username"])["access_token"]
    headers = {**_bearer(admin_token), **CSRF_HEADERS}

    assert client.get(
        "/notes", headers=_bearer(victim_token)
    ).status_code == 200

    assert client.post(
        f"/admin/users/{victim['id']}/ban",
        json={"reason": "A6 ban token"},
        headers=headers,
    ).status_code == 200

    banned_access = client.get("/notes", headers=_bearer(victim_token))
    assert banned_access.status_code == 401, banned_access.text
    assert _error_code(banned_access) == "SESSION_REVOKED"

    assert client.post(
        f"/admin/users/{victim['id']}/unban",
        json={"reason": "A6 unban token"},
        headers=headers,
    ).status_code == 200

    still_revoked = client.get("/notes", headers=_bearer(victim_token))
    assert still_revoked.status_code == 401
    assert _error_code(still_revoked) == "SESSION_REVOKED"

    assert client.post(
        f"/admin/users/{revoked['id']}/revoke-sessions",
        json={"reason": "A6 revoke token"},
        headers=headers,
    ).status_code == 200

    revoked_access = client.get("/notes", headers=_bearer(revoked_token))
    assert revoked_access.status_code == 401
    assert _error_code(revoked_access) == "SESSION_REVOKED"


def test_demoted_admin_loses_access_without_jwt_reissue(world):
    client, make_user = world
    admin = make_user(role="ADMIN")

    token = _login(client, admin["username"])["access_token"]

    assert client.get(
        "/admin/users", headers=_bearer(token)
    ).status_code == 200

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET role = 'USER' WHERE id = :i"),
            {"i": admin["id"]},
        )

    demoted = client.get("/admin/users", headers=_bearer(token))
    assert demoted.status_code == 403, demoted.text
    assert _error_code(demoted) == "ADMIN_REQUIRED"


def test_admin_responses_do_not_leak_sensitive_data(world):
    client, make_user = world
    admin = make_user(role="ADMIN")
    target = make_user()

    token = _login(client, admin["username"])["access_token"]
    headers = _bearer(token)

    listing = client.get(
        "/admin/users",
        params={"keyword": target["username"]},
        headers=headers,
    )
    assert listing.status_code == 200, listing.text

    items = listing.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]

    assert item["email"] == f"{target['username'][0]}***@example.com"
    assert "password_hash" not in item
    assert "refresh_token" not in item

    detail = client.get(
        f"/admin/users/{target['id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text

    detail_data = detail.json()["data"]

    assert detail_data["email"] == f"{target['username']}@example.com"
    assert "password_hash" not in detail_data
    assert "refresh_token" not in detail_data
    assert "notes" not in detail_data
    assert set(detail_data) >= {
        "id",
        "username",
        "email",
        "role",
        "is_active",
        "statistics",
    }

    ai_config = client.get("/admin/ai/config", headers=headers)
    assert ai_config.status_code == 200
    assert "a6-sentinel-api-key" not in ai_config.text
    assert "api_key" not in ai_config.text.lower()

    audit = client.get("/admin/audit-logs", headers=headers)
    assert audit.status_code == 200
    audit_text = audit.text.lower()
    assert "password_hash" not in audit_text
    assert "refresh_token" not in audit_text
    assert "access_token" not in audit_text


def test_audit_failure_rolls_back_user_action(world, monkeypatch):
    from app.services.admin import user_service

    client, make_user = world
    admin = make_user(role="ADMIN")
    target = make_user()

    token = _login(client, admin["username"])["access_token"]
    headers = {**_bearer(token), **CSRF_HEADERS}

    def boom(*args, **kwargs):
        raise RuntimeError("A6 forced audit failure")

    monkeypatch.setattr(
        user_service.audit_repository,
        "insert_audit_log",
        boom,
    )

    response = client.post(
        f"/admin/users/{target['id']}/ban",
        json={"reason": "A6 audit rollback"},
        headers=headers,
    )
    assert response.status_code == 500, response.text

    with engine.connect() as conn:
        is_active = conn.execute(
            text("SELECT is_active FROM users WHERE id = :i"),
            {"i": target["id"]},
        ).scalar_one()

        audits = conn.execute(
            text(
                "SELECT COUNT(*) FROM admin_audit_logs "
                "WHERE target_type = 'USER' AND target_id = :i "
                "AND reason = :r"
            ),
            {"i": target["id"], "r": "A6 audit rollback"},
        ).scalar_one()

    assert int(is_active) == 1, "审计失败后封禁未回滚"
    assert int(audits) == 0


def test_cookie_attributes_refresh_rotation_and_replay(world):
    client, make_user = world
    user = make_user()

    login = client.post(
        "/auth/login",
        data={"username": user["username"], "password": PASSWORD},
        headers=CSRF_HEADERS,
    )
    assert login.status_code == 200, login.text

    cookies = login.headers.get_list("set-cookie")
    refresh_cookie = next(
        value for value in cookies if value.startswith("ssp_refresh=")
    )

    lowered = refresh_cookie.lower()
    assert "httponly" in lowered
    assert ("secure" in lowered) is settings.REFRESH_COOKIE_SECURE
    assert "samesite=lax" in lowered
    assert "path=/auth" in lowered
    assert "max-age=" in lowered

    old_refresh = client.cookies.get("ssp_refresh")
    assert old_refresh

    rotated = client.post("/auth/refresh", headers=CSRF_HEADERS)
    assert rotated.status_code == 200, rotated.text

    new_refresh = client.cookies.get("ssp_refresh")
    assert new_refresh and new_refresh != old_refresh

    new_access = rotated.json()["data"]["access_token"]

    replay = client.post(
        "/auth/refresh",
        headers=CSRF_HEADERS,
        cookies={"ssp_refresh": old_refresh},
    )
    assert replay.status_code == 401, replay.text
    # 重放会撤销整个会话族，按既有契约返回 SESSION_REVOKED。
    assert _error_code(replay) == "SESSION_REVOKED"

    after_replay = client.get("/notes", headers=_bearer(new_access))
    assert after_replay.status_code == 401, after_replay.text
    assert _error_code(after_replay) == "SESSION_REVOKED"


def test_logout_clears_cookie_and_revokes_session(world):
    client, make_user = world
    user = make_user()

    data = _login(client, user["username"])
    token = data["access_token"]

    logout = client.post("/auth/logout", headers=CSRF_HEADERS)
    assert logout.status_code == 200, logout.text

    clear_cookie = " ".join(logout.headers.get_list("set-cookie")).lower()
    assert "ssp_refresh=" in clear_cookie
    assert "max-age=0" in clear_cookie

    revoked = client.get("/notes", headers=_bearer(token))
    assert revoked.status_code == 401
    assert _error_code(revoked) == "SESSION_REVOKED"


def test_expired_access_returns_access_expired(world):
    client, make_user = world
    user = make_user()

    _login(client, user["username"])

    with engine.connect() as conn:
        family_id = conn.execute(
            text(
                "SELECT family_id FROM login_sessions "
                "WHERE user_id = :i ORDER BY created_at DESC LIMIT 1"
            ),
            {"i": user["id"]},
        ).scalar_one()

    now = datetime.now(timezone.utc)

    expired = jwt.encode(
        {
            "sub": str(user["id"]),
            "family_id": family_id,
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=1),
            "type": "access",
            "jti": str(uuid.uuid4()),
        },
        settings.SECRET_KEY,
        algorithm=security.JWT_ALGORITHM,
    )

    response = client.get("/notes", headers=_bearer(expired))
    assert response.status_code == 401, response.text
    assert _error_code(response) == "ACCESS_EXPIRED"


def test_profile_update_cannot_escalate_role(world):
    client, make_user = world
    user = make_user()

    token = _login(client, user["username"])["access_token"]

    response = client.put(
        f"/users/{user['id']}",
        json={"nickname": "A6Nick", "role": "ADMIN"},
        headers=_bearer(token),
    )
    assert response.status_code == 200, response.text

    with engine.connect() as conn:
        role = conn.execute(
            text("SELECT role FROM users WHERE id = :i"),
            {"i": user["id"]},
        ).scalar_one()

    assert role == "USER", "个人资料更新可以提升角色"


def test_expired_lease_releases_concurrency(world):
    client, make_user = world
    user = make_user()
    token = _login(client, user["username"])["access_token"]

    expired_id = str(uuid.uuid4())
    valid_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ai_requests ("
                "request_id, user_id, note_id, operation, "
                "request_date, status, leased_until"
                ") VALUES ("
                ":rid, :uid, NULL, 'SUMMARY', :day, 'RUNNING', "
                "DATE_SUB(UTC_TIMESTAMP(6), INTERVAL 5 SECOND)"
                ")"
            ),
            {
                "rid": expired_id,
                "uid": user["id"],
                "day": business_today(),
            },
        )

    with SessionLocal() as db:
        admission = ai_guard_service.admit_request(
            db=db,
            user_id=user["id"],
            note_id=None,
            operation="SUMMARY",
        )

    with SessionLocal() as db:
        ai_guard_repository.finish_request(
            db=db,
            request_id=admission.request_id,
            status="SUCCESS",
            prompt_tokens=None,
            completion_tokens=None,
        )
        db.commit()

    assert client.get("/notes", headers=_bearer(token)).status_code == 200

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ai_requests ("
                "request_id, user_id, note_id, operation, "
                "request_date, status, leased_until"
                ") VALUES ("
                ":rid, :uid, NULL, 'SUMMARY', :day, 'RUNNING', "
                "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL 180 SECOND)"
                ")"
            ),
            {
                "rid": valid_id,
                "uid": user["id"],
                "day": business_today(),
            },
        )

    with pytest.raises(Exception) as caught:
        with SessionLocal() as db:
            ai_guard_service.admit_request(
                db=db,
                user_id=user["id"],
                note_id=None,
                operation="SUMMARY",
            )

    error = caught.value
    assert getattr(error, "status_code", None) == 429
    assert error.detail["code"] == "AI_USER_BUSY"


def test_business_today_uses_beijing_day():
    expected = (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .date()
    )
    assert business_today() == expected