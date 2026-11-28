"""A6 3.1 真实冷缓存 NOSCRIPT 自动恢复探针。

使用独立临时 Memurai 实例（独立端口/临时目录），不对共享实例执行 SCRIPT FLUSH。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    $env:REDIS_URL='redis://127.0.0.1:6390/0'
    .\\.venv\\Scripts\\python.exe tests/a6_redis_cold_cache_probe.py
"""

import os
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlparse

MEMURAI = (
    r"C:\Users\REED\AppData\Local\Temp\memurai"
    r"\extract\Memurai\memurai.exe"
)
PORT = int(os.environ.get("A6_REDIS_PORT", "6390"))


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


def main() -> None:
    from app.config import settings

    parsed = urlparse(settings.REDIS_URL)

    if parsed.port != PORT:
        raise RuntimeError(
            "REDIS_URL 未指向独立临时实例："
            f"{settings.REDIS_URL}（期望端口 {PORT}）"
        )

    tmp_dir = tempfile.mkdtemp(prefix="a6redis_")
    process = subprocess.Popen(
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

    try:
        wait_ping()

        from app.core.redis_client import redis_client
        from app.services.knowledge import ai_rate_limit_service

        script = ai_rate_limit_service.sliding_window_script

        exists_before = redis_client.script_exists(script.sha)[0]
        assert exists_before is False, (
            f"冷缓存前置失败，脚本已存在: {exists_before}"
        )
        print(f"PASS precondition script_exists={exists_before}")

        load_calls: list[int] = []
        original_script_load = redis_client.script_load

        def recording_script_load(body: str) -> str:
            load_calls.append(1)
            return original_script_load(body)

        redis_client.script_load = recording_script_load

        user_id = 900_000_000 + int(time.time() * 1000) % 100_000_000
        key = f"ssp:{settings.DB_NAME}:ai:rate:v2:{user_id}"
        redis_client.delete(key)

        ai_rate_limit_service.check_ai_rate_limit(user_id)

        assert redis_client.zcard(key) == 1, "首次调用后 ZSET 计数错误"
        assert load_calls == [1], (
            f"首次 EVALSHA 未触发 NOSCRIPT 自动加载: {load_calls}"
        )
        exists_after = redis_client.script_exists(script.sha)[0]
        assert exists_after is True, "脚本未成功写入缓存"

        print(
            "PASS noscript-recovery "
            f"script_load_calls={len(load_calls)} zcard=1 "
            f"script_exists_after={exists_after}"
        )

        load_calls.clear()
        ai_rate_limit_service.check_ai_rate_limit(user_id)

        assert redis_client.zcard(key) == 2, "第二次调用计数错误"
        assert load_calls == [], (
            f"第二次调用仍触发脚本加载: {load_calls}"
        )

        print(
            "PASS cache-reuse "
            f"script_load_calls={len(load_calls)} zcard=2"
        )

        redis_client.delete(key)
    finally:
        process.terminate()

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("PASS cleanup temp-instance")


if __name__ == "__main__":
    main()