"""A6 3.2 真实 Redis 连接故障、503 与进程重启恢复探针。

使用独立临时 Memurai（端口 6391、临时目录），不影响共享实例；
同一个 FastAPI 应用进程贯穿三个阶段，验证无需重启即可恢复。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    $env:REDIS_URL='redis://127.0.0.1:6391/0'
    .\\.venv\\Scripts\\python.exe tests/a6_redis_outage_probe.py
"""

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.core import security
from app.core.clock import utc_db_now
from app.database import SessionLocal, engine
from app.main import app as production_app
from app.repositories.knowledge import ai_guard_repository
from app.services.knowledge import ai_guard_service

MEMURAI = (
    r"C:\Users\REED\AppData\Local\Temp\memurai"
    r"\extract\Memurai\memurai.exe"
)
PORT = int(os.environ.get("A6_REDIS_PORT", "6391"))
PASSWORD = "A6OutagePass123"
ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}


def start_instance(tmp_dir: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            MEMURAI,
            "--port",
            str(PORT),
            "--bind",
            "127.0.0.1",
            "--dir",
            tmp_dir,
            "--appendonly",
            "no",
        ],
        cwd=os.path.dirname(MEMURAI),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_ping(timeout: float = 15.0) -> None:
    from app.core.redis_client import redis_client

    deadline = time.time() + timeout
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            if redis_client.ping():
                return
        except Exception as error:  # noqa: BLE001
            last_error = error

        time.sleep(0.2)

    raise RuntimeError(f"临时 Redis 未就绪: {last_error}")


def wait_down(timeout: float = 10.0) -> None:
    from app.core.redis_client import redis_client

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            redis_client.ping()
        except Exception:  # noqa: BLE001
            return

        time.sleep(0.2)

    raise RuntimeError("临时 Redis 停止后仍然可连接")


def guard_database() -> str:
    with engine.connect() as conn:
        name = conn.execute(text("SELECT DATABASE()")).scalar_one()

    if name != "ssp_v3_admin_test":
        raise RuntimeError(f"非隔离测试库: {name}")

    return name


def main() -> None:
    parsed = urlparse(settings.REDIS_URL)

    if parsed.port != PORT:
        raise RuntimeError(
            "REDIS_URL 未指向独立临时实例："
            f"{settings.REDIS_URL}（期望端口 {PORT}）"
        )

    guard_database()

    tmp_dir = tempfile.mkdtemp(prefix="a6redis_outage_")
    process = start_instance(tmp_dir)
    user_id: int | None = None

    try:
        wait_ping()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ai_runtime_config SET enabled = 1, "
                    "user_daily_limit = 10, global_daily_limit = 80 "
                    "WHERE id = 1"
                )
            )

        settings.DEEPSEEK_API_KEY = "a6-outage-test-key"

        username = f"a6outage{uuid.uuid4().hex[:8]}"

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

        client = TestClient(
            production_app,
            base_url="https://ssp.test",
            client=("127.0.0.1", 52499),
            raise_server_exceptions=False,
        )

        login = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        assert login.status_code == 200, login.text

        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # 阶段 1：正常准入
        with SessionLocal() as db:
            admission = ai_guard_service.admit_request(
                db=db,
                user_id=user_id,
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

        print("PASS phase1 admission=SUCCESS")

        key = f"ssp:{settings.DB_NAME}:ai:rate:v2:{user_id}"
        from app.core.redis_client import redis_client

        zcard_before = redis_client.zcard(key)
        assert zcard_before == 1, zcard_before

        # 阶段 2：停止 Redis
        process.terminate()
        process.wait(timeout=10)
        wait_down()

        provider_calls: list[int] = []
        from app.services.knowledge import ai_note_service

        original_provider = ai_note_service.stream_checked_completion

        def forbidden_provider(*args, **kwargs):
            provider_calls.append(1)
            raise AssertionError("Redis 故障时不应调用 AI Provider")

        ai_note_service.stream_checked_completion = forbidden_provider

        try:
            response = client.post(
                "/notes/ai/generate",
                json={"topic": "A6 Redis outage"},
                headers=auth,
            )
        finally:
            ai_note_service.stream_checked_completion = original_provider

        assert response.status_code == 503, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "AI_RATE_LIMIT_UNAVAILABLE", detail
        assert provider_calls == [], "被拒绝的请求调用了 AI Provider"

        notes = client.get("/notes", headers=auth)
        assert notes.status_code == 200, notes.text

        print(
            "PASS phase2 status=503 code=AI_RATE_LIMIT_UNAVAILABLE "
            f"provider_calls=0 notes_status={notes.status_code}"
        )

        # 阶段 3：重启实例（同一 FastAPI 进程）
        process = start_instance(tmp_dir)
        wait_ping()

        lost = redis_client.exists(key)
        assert lost == 0, "重启后限流历史仍存在，预期为新实例丢失"

        with SessionLocal() as db:
            admission = ai_guard_service.admit_request(
                db=db,
                user_id=user_id,
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

        print(
            "PASS phase3 admission=SUCCESS without-app-restart "
            f"rate_history_lost_before_recovery={lost == 0}"
        )

        redis_client.delete(key)
    finally:
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            process.kill()

        if user_id is not None:
            with engine.begin() as conn:
                for table in (
                    "refresh_tokens",
                    "login_sessions",
                    "auth_events",
                    "email_verifications",
                ):
                    conn.execute(
                        text(
                            f"DELETE FROM {table} WHERE user_id = :i"
                        ),
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

        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("PASS cleanup temp-instance-and-data")


if __name__ == "__main__":
    main()