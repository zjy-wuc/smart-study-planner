"""Auth V2.0 A2.3 / A2.4 集中验收测试（只读业务源码，不修改源码）。

覆盖：
- T1 头像格式与尺寸校验
- T2 头像文件与数据库一致性
- T3 头像权限及静态资源
- T4 个人资料
- T5 认证数据清理
- T6 孤儿头像清理
- T7 Worker 集成
- T8 验证码安全时间边界
- T9 当前退出修复
- T10 历史回归（P1-1 / P1-2 / P1-3）

约束：
- 仅使用隔离库 ssp_a0_migrate2（SELECT DATABASE() 守卫）。
- 头像写入独立临时目录，绝不使用正式 storage/avatars。
- 邮件全部 Mock，不真实发送。
- 不输出密码、验证码、Token、密钥。
- 测试数据在 tearDownClass 精确清理。
"""

import atexit
import hashlib
import importlib
import importlib.util
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import uuid

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

import jwt
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import SessionTransaction

# ======================================================================
# 关键：必须在导入 app.main 之前把头像目录指向独立临时目录
# ======================================================================

from app.config import settings  # noqa: E402

TMP_AVATAR_ROOT = Path(tempfile.mkdtemp(prefix="ssp_a23_avatar_"))
settings.AVATAR_DIR = TMP_AVATAR_ROOT / "avatars"
settings.AVATAR_DIR.mkdir(parents=True, exist_ok=True)

atexit.register(lambda: shutil.rmtree(TMP_AVATAR_ROOT, ignore_errors=True))

from app.core import security  # noqa: E402
from app.core.clock import utc_db_now  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


# ----------------------------------------------------------------------
# 全量执行时，其他测试用例可能已先导入 app.main，StaticFiles 的 directory
# 会被绑定到仓库 storage/avatars。这里把挂载重建到本次临时目录，并在进程
# 退出时恢复原挂载，保证夹具与静态资源指向一致（不修改 main.py 的生产架构）。
# ----------------------------------------------------------------------

from fastapi.staticfiles import StaticFiles as _StaticFiles  # noqa: E402

_ORIGINAL_AVATAR_MOUNT = next(
    (
        route
        for route in app.router.routes
        if getattr(route, "path", None) == "/media/avatars"
    ),
    None,
)


def _rebind_avatar_static() -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) != "/media/avatars"
    ]
    app.mount(
        "/media/avatars",
        _StaticFiles(
            directory=str(settings.AVATAR_DIR),
            follow_symlink=False,
        ),
        name="avatars",
    )


def _restore_avatar_static() -> None:
    if _ORIGINAL_AVATAR_MOUNT is None:
        return
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) != "/media/avatars"
    ] + [_ORIGINAL_AVATAR_MOUNT]


_rebind_avatar_static()
atexit.register(_restore_avatar_static)
from app.repositories.auth import (  # noqa: E402
    cleanup_repository,
    user_repository,
    verification_repository,
)
from app.schemas.auth import (  # noqa: E402
    EmailChangeRequest,
    EmailCodePurpose,
    PasswordChangeRequest,
    PasswordResetRequest,
)
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth import (  # noqa: E402
    account_service,
    auth_service,
    avatar_service,
    session_service,
    verification_service,
)
from app.services.auth.auth_cleanup import run_auth_cleanup  # noqa: E402

from tests.test_auth_a1_3_acceptance import (  # noqa: E402
    CSRF,
    PASSWORD,
    BaseAuthTest,
    assert_isolated_db,
)


NEW_PASSWORD = "NewPass456"
ALT_PASSWORD = "AltPass789"
AVATAR_RE = re.compile(r"^[0-9a-f]{32}\.webp$")
AVATAR_PREFIX = "/media/avatars/"


# ======================================================================
# 工具函数
# ======================================================================


def image_bytes(fmt="PNG", size=(64, 64), mode="RGB", color=(120, 80, 40), **save):
    buf = BytesIO()
    Image.new(mode, size, color).save(buf, format=fmt, **save)
    return buf.getvalue()


def animated_bytes(fmt, size=(20, 20)):
    frames = [
        Image.new("RGBA", size, (255, 0, 0, 255)),
        Image.new("RGBA", size, (0, 255, 0, 255)),
    ]
    buf = BytesIO()
    frames[0].save(
        buf,
        format=fmt,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    return buf.getvalue()


def open_out(raw):
    return Image.open(BytesIO(raw))


class BaseA23(BaseAuthTest):
    """在 A1.3 基类之上补充头像 / 资料 / 清理辅助能力。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        settings.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        cls._lock_timeout = settings.AUTH_LOCK_TIMEOUT_SECONDS
        settings.AUTH_LOCK_TIMEOUT_SECONDS = 30

    @classmethod
    def tearDownClass(cls):
        settings.AUTH_LOCK_TIMEOUT_SECONDS = cls._lock_timeout
        super().tearDownClass()

    @classmethod
    def cleanup(cls):
        super().cleanup()
        for directory in (
            settings.AVATAR_DIR,
            settings.AVATAR_DIR.with_name(
                settings.AVATAR_DIR.name + "_staging"
            ),
        ):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                try:
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                except OSError:
                    pass

    # ---------- 构造器 ----------

    def setUp(self):
        super().setUp()
        for directory in (
            settings.AVATAR_DIR,
            settings.AVATAR_DIR.with_name(
                settings.AVATAR_DIR.name + "_staging"
            ),
        ):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                try:
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                except OSError:
                    pass

    def new_user(self, **kwargs):
        return self.make_user("u" + uuid.uuid4().hex[:10], **kwargs)

    def bearer(self, pair):
        return {"Authorization": f"Bearer {pair['access_token']}"}

    def auth_headers(self, pair):
        headers = dict(CSRF)
        headers.update(self.bearer(pair))
        return headers

    def family_of(self, pair):
        return security.decode_access_token(pair["access_token"])["family_id"]

    def upload(self, client, pair, raw, filename="avatar.png", ctype="image/png"):
        return client.post(
            "/users/me/avatar",
            files={"file": (filename, raw, ctype)},
            headers=self.auth_headers(pair),
        )

    def delete_req(self, client, pair):
        return client.delete("/users/me/avatar", headers=self.auth_headers(pair))

    def service_upload(self, uid, family, raw):
        return avatar_service.upload_avatar(
            user_id=uid, family_id=family, file=BytesIO(raw)
        )

    def avatar_url_of(self, uid):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT avatar_url FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()

    def set_avatar_url(self, uid, url):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET avatar_url = :u WHERE id = :i"),
                {"u": url, "i": uid},
            )

    def path_of_url(self, url):
        return settings.AVATAR_DIR / url.rsplit("/", 1)[-1]

    def avatar_files(self):
        if not settings.AVATAR_DIR.exists():
            return set()
        return {p.name for p in settings.AVATAR_DIR.iterdir() if p.is_file()}

    # ---------- 断言 ----------

    def assert_rejected(self, fn, status=400, code="INVALID_AVATAR"):
        with self.assertRaises(HTTPException) as ctx:
            fn()
        self.assertEqual(ctx.exception.status_code, status)
        detail = ctx.exception.detail
        if isinstance(detail, dict):
            self.assertEqual(detail.get("code"), code)

    @staticmethod
    def inner_code(resp):
        detail = resp.json().get("detail")
        return detail.get("code") if isinstance(detail, dict) else None

    def run_parallel(self, fns, timeout=60):
        results = [None] * len(fns)
        barrier = threading.Barrier(len(fns))

        def worker(i):
            try:
                barrier.wait(timeout=timeout)
                results[i] = ("ok", fns[i]())
            except Exception as exc:  # noqa: BLE001
                results[i] = ("err", exc)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(len(fns))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=timeout)
        return results

    # ---------- 数据构造 ----------

    def mk_session(
        self,
        uid,
        *,
        family=None,
        created=None,
        last=None,
        absolute=None,
        revoked=None,
        user_agent="test-agent",
    ):
        family = family or str(uuid.uuid4())
        now = utc_db_now()
        created = created or now
        last = last or created
        absolute = absolute or (now + timedelta(days=30))
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO login_sessions (
                        family_id, user_id, user_agent, created_at,
                        last_activity_at, absolute_expires_at,
                        revoked_at, revoked_reason
                    ) VALUES (
                        :f, :u, :ua, :c, :l, :a, :r, :rr
                    )
                    """
                ),
                {
                    "f": family,
                    "u": uid,
                    "ua": user_agent,
                    "c": created,
                    "l": last,
                    "a": absolute,
                    "r": revoked,
                    "rr": "TEST_REVOKED" if revoked else None,
                },
            )
        return family

    def mk_token(
        self,
        uid,
        family,
        *,
        expires=None,
        revoked=None,
        replaced=None,
    ):
        token_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO refresh_tokens (
                        user_id, token_hash, family_id, expires_at,
                        revoked_at, replaced_by, created_at
                    ) VALUES (
                        :u, :h, :f, :e, :r, :rp, :c
                    )
                    """
                ),
                {
                    "u": uid,
                    "h": token_hash,
                    "f": family,
                    "e": expires or (utc_db_now() + timedelta(days=7)),
                    "r": revoked,
                    "rp": replaced,
                    "c": utc_db_now(),
                },
            )
        return token_hash

    def mk_code_at(
        self,
        email,
        purpose,
        code,
        created_at,
        *,
        user_id=None,
        family_id=None,
        expires_at=None,
        status="SENT",
    ):
        purpose_value = purpose.value if hasattr(purpose, "value") else purpose
        expires_at = expires_at or (utc_db_now() + timedelta(minutes=5))
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO email_verifications (
                        email, purpose, user_id, family_id, code_hash,
                        attempts, created_at, expires_at, consumed_at,
                        invalidated_at, request_ip, send_status
                    ) VALUES (
                        :email, :purpose, :user_id, :family_id, :hash,
                        0, :created, :expires, NULL, NULL, '127.0.0.1', :status
                    )
                    """
                ),
                {
                    "email": email,
                    "purpose": purpose_value,
                    "user_id": user_id,
                    "family_id": family_id,
                    "hash": security.hash_email_code(email, purpose_value, code),
                    "created": created_at,
                    "expires": expires_at,
                    "status": status,
                },
            )
            return int(result.lastrowid)

    def insert_event(self, uid, event_type, created_at, ip="127.0.0.1"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO auth_events (
                        user_id, event_type, ip, created_at
                    ) VALUES (:u, :e, :ip, :c)
                    """
                ),
                {"u": uid, "e": event_type, "ip": ip, "c": created_at},
            )

    def set_password_updated_at(self, uid, value):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET password_updated_at = :t WHERE id = :i"),
                {"t": value, "i": uid},
            )

    def set_email_verified_at(self, uid, value):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET email_verified_at = :t WHERE id = :i"),
                {"t": value, "i": uid},
            )

    def code_row(self, email, purpose):
        with engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT * FROM email_verifications
                    WHERE email = :e AND purpose = :p
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """
                ),
                {
                    "e": email,
                    "p": purpose.value if hasattr(purpose, "value") else purpose,
                },
            ).mappings().first()

    def session_row(self, family):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT * FROM login_sessions WHERE family_id = :f"),
                {"f": family},
            ).mappings().first()


# ======================================================================
# T0 契约检查
# ======================================================================


class TestT0Contract(BaseA23):
    def test_avatar_and_profile_routes_registered(self):
        paths = app.openapi()["paths"]
        for expected in (
            "/users/me",
            "/users/{user_id}",
            "/users/me/avatar",
        ):
            self.assertIn(expected, paths, f"缺失路由 {expected}")

    def test_new_modules_import(self):
        for mod in (
            "app.services.auth.avatar_service",
            "app.services.auth.auth_cleanup",
            "app.repositories.auth.cleanup_repository",
            "app.api.routes.users",
            "app.schemas.user",
        ):
            importlib.import_module(mod)


# ======================================================================
# T1 头像格式及尺寸校验
# ======================================================================


class TestT1AvatarValidation(BaseA23):
    def convert(self, raw):
        return avatar_service._convert_image(BytesIO(raw))

    def test_jpg_png_webp_accepted(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            out = self.convert(image_bytes(fmt))
            self.assertTrue(out, f"{fmt} 未被接受")

    def test_output_is_valid_webp(self):
        out = self.convert(image_bytes("JPEG", (120, 60)))
        with open_out(out) as im:
            self.assertEqual(im.format, "WEBP")

    def test_transparency_preserved(self):
        raw = image_bytes("PNG", (32, 32), "RGBA", (200, 10, 10, 0))
        out = self.convert(raw)
        with open_out(out) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((16, 16))[3], 0)

    def test_max_edge_not_exceed_512(self):
        out = self.convert(image_bytes("PNG", (1000, 500)))
        with open_out(out) as im:
            self.assertEqual(max(im.size), 512)

    def test_aspect_ratio_preserved(self):
        out = self.convert(image_bytes("PNG", (1000, 500)))
        with open_out(out) as im:
            self.assertEqual(im.size, (512, 256))

    def test_small_image_not_upscaled(self):
        out = self.convert(image_bytes("PNG", (10, 10)))
        with open_out(out) as im:
            self.assertEqual(im.size, (10, 10))

    def test_exif_orientation_applied(self):
        src = Image.new("RGB", (80, 40), (10, 20, 30))
        exif = src.getexif()
        exif[274] = 6  # 顺时针旋转 90°
        buf = BytesIO()
        src.save(buf, format="JPEG", exif=exif.tobytes())

        out = self.convert(buf.getvalue())
        with open_out(out) as im:
            self.assertEqual(im.size, (40, 80))

    def test_metadata_stripped(self):
        src = Image.new("RGB", (60, 60), (30, 40, 50))
        exif = src.getexif()
        exif[270] = "SSPMetaMarker"
        exif[274] = 1
        buf = BytesIO()
        src.save(buf, format="JPEG", exif=exif.tobytes())

        out = self.convert(buf.getvalue())
        self.assertNotIn(b"SSPMetaMarker", out)
        with open_out(out) as im:
            self.assertEqual(len(im.getexif()), 0)
            self.assertNotIn("exif", im.info)

    def test_empty_file_rejected(self):
        self.assert_rejected(lambda: self.convert(b""))

    def test_oversize_file_rejected(self):
        raw = b"\x00" * (settings.AVATAR_MAX_BYTES + 1)
        self.assert_rejected(lambda: self.convert(raw), status=413)

    def test_pixel_limit_rejected(self):
        original = settings.AVATAR_MAX_PIXELS
        settings.AVATAR_MAX_PIXELS = 10_000
        try:
            self.assert_rejected(
                lambda: self.convert(image_bytes("PNG", (200, 200)))
            )
        finally:
            settings.AVATAR_MAX_PIXELS = original

    def test_animated_webp_rejected(self):
        self.assert_rejected(
            lambda: self.convert(animated_bytes("WEBP"))
        )

    def test_gif_rejected(self):
        self.assert_rejected(
            lambda: self.convert(animated_bytes("GIF"))
        )

    def test_apng_rejected(self):
        self.assert_rejected(
            lambda: self.convert(animated_bytes("PNG"))
        )

    def test_svg_and_pdf_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
        pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        self.assert_rejected(lambda: self.convert(svg))
        self.assert_rejected(lambda: self.convert(pdf))

    def test_fake_extension_and_mime_cannot_bypass(self):
        # 伪造扩展名 + 伪造 MIME，但内容不是图片
        self.assert_rejected(lambda: self.convert(b"not-an-image"))
        # 真实 JPEG 即使扩展名为 .txt，也应按真实内容接受
        out = self.convert(image_bytes("JPEG"))
        self.assertTrue(out)

    def test_corrupted_image_rejected(self):
        broken = b"\x89PNG\r\n\x1a\n" + b"broken-data"
        self.assert_rejected(lambda: self.convert(broken))

    def test_concurrent_decode_memory_risk(self):
        """并发解码不应崩溃；同时记录内存占用风险（无并发解码上限）。"""
        raw = image_bytes("PNG", (800, 600))
        fns = [lambda: self.convert(raw) for _ in range(8)]
        results = self.run_parallel(fns)
        self.assertEqual([r[0] for r in results], ["ok"] * 8)
        # 风险：并发解码在进程内完成，未限制同时解码数量。
        self.assertFalse(
            any(
                token in Path("app/services/auth/avatar_service.py").read_text(
                    encoding="utf-8"
                )
                for token in ("Semaphore", "BoundedSemaphore")
            ),
            "发现并发解码限制，应更新风险结论",
        )


# ======================================================================
# T2 文件与数据库一致性
# ======================================================================


class TestT2Consistency(BaseA23):
    def setUp(self):
        super().setUp()
        self.client = self.new_client()

    def test_first_upload_updates_avatar_url(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        resp = self.upload(self.client, pair, image_bytes("PNG"))
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["data"]["avatar_url"]
        self.assertTrue(url.startswith(AVATAR_PREFIX))
        self.assertEqual(self.avatar_url_of(uid), url)
        self.assertTrue(self.path_of_url(url).is_file())

    def test_filename_server_generated(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        resp = self.upload(
            self.client, pair, image_bytes("PNG"), filename="evil name.png"
        )
        url = resp.json()["data"]["avatar_url"]
        filename = url[len(AVATAR_PREFIX):]
        self.assertRegex(filename, AVATAR_RE)
        self.assertNotIn("evil", url)

    def test_replace_generates_new_url_and_removes_old(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        url1 = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]
        path1 = self.path_of_url(url1)

        url2 = self.upload(self.client, pair, image_bytes("JPEG")).json()[
            "data"
        ]["avatar_url"]
        self.assertNotEqual(url1, url2)
        self.assertTrue(self.path_of_url(url2).is_file())
        self.assertFalse(path1.exists(), "提交后旧头像未被清理")
        self.assertEqual(self.avatar_url_of(uid), url2)

    def test_new_avatar_exists_and_publicly_readable(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        with Image.open(BytesIO(resp.content)) as im:
            self.assertEqual(im.format, "WEBP")

    def test_update_failure_keeps_old_avatar(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url_old = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]
        before = self.avatar_files()

        with mock.patch.object(user_repository, "update_avatar", return_value=0):
            resp = self.upload(self.client, pair, image_bytes("JPEG"))

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(self.avatar_url_of(uid), url_old)
        self.assertTrue(self.path_of_url(url_old).is_file())
        self.assertEqual(self.avatar_files(), before, "失败后遗留了新的头像文件")

    def test_commit_failure_keeps_new_file_and_old_reference(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url_old = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]
        before = self.avatar_files()

        boom = OperationalError("COMMIT", {}, Exception("commit unsure"))
        with mock.patch.object(Session, "commit", side_effect=boom):
            resp = self.upload(self.client, pair, image_bytes("JPEG"))

        self.assertEqual(resp.status_code, 500)
        # 数据库回滚，引用保持旧值
        self.assertEqual(self.avatar_url_of(uid), url_old)
        self.assertTrue(self.path_of_url(url_old).is_file())
        # 提交结果不确定时不得删除可能是数据库正在引用的新文件
        self.assertEqual(len(self.avatar_files()), len(before) + 1)

    def test_old_delete_failure_does_not_break_update(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url_old = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]

        with mock.patch.object(avatar_service, "_remove_file", return_value=False):
            resp = self.upload(self.client, pair, image_bytes("JPEG"))

        self.assertEqual(resp.status_code, 200)
        url_new = resp.json()["data"]["avatar_url"]
        self.assertEqual(self.avatar_url_of(uid), url_new)
        self.assertTrue(self.path_of_url(url_new).is_file())
        # 删旧失败不影响已提交的新头像；旧文件残留可接受
        self.assertTrue(self.path_of_url(url_old).is_file())

    def test_concurrent_upload_does_not_delete_referenced(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        colors = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (10, 20, 30),
        ]
        fns = [
            (
                lambda c=c: self.service_upload(
                    uid, family, image_bytes("PNG", (40, 40), "RGB", c)
                )
            )
            for c in colors
        ]
        results = self.run_parallel(fns)
        self.assertEqual([r[0] for r in results], ["ok"] * 4)

        final_url = self.avatar_url_of(uid)
        self.assertIsNotNone(final_url)
        self.assertTrue(self.path_of_url(final_url).is_file())
        # 串行化后只保留最终被引用的一个文件
        self.assertEqual(self.avatar_files(), {final_url.rsplit("/", 1)[-1]})

    def test_concurrent_upload_and_delete_consistent(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        def do_upload():
            return self.service_upload(
                uid, family, image_bytes("PNG", (40, 40), "RGB", (9, 9, 9))
            )

        def do_delete():
            return avatar_service.delete_avatar(user_id=uid, family_id=family)

        self.run_parallel([do_upload, do_delete])

        final_url = self.avatar_url_of(uid)
        files = self.avatar_files()
        if final_url is None:
            self.assertEqual(files, set(), "已清空引用但残留头像文件")
        else:
            self.assertTrue(self.path_of_url(final_url).is_file())
            self.assertEqual(files, {final_url.rsplit("/", 1)[-1]})

    def test_delete_sets_null_and_removes_file(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]

        resp = self.delete_req(self.client, pair)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["data"]["avatar_url"])
        self.assertIsNone(self.avatar_url_of(uid))
        self.assertFalse(self.path_of_url(url).exists())

    def test_repeat_delete_safe(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        self.upload(self.client, pair, image_bytes("PNG"))

        self.assertEqual(self.delete_req(self.client, pair).status_code, 200)
        second = self.delete_req(self.client, pair)
        self.assertEqual(second.status_code, 200)
        self.assertIsNone(second.json()["data"]["avatar_url"])

    def test_cannot_delete_outside_avatar_dir(self):
        sentinel = TMP_AVATAR_ROOT / "sentinel.txt"
        sentinel.write_text("keep", encoding="utf-8")
        try:
            with SessionLocal() as db:
                for url in (
                    "/media/avatars/../../sentinel.txt",
                    "/media/avatars/sentinel.txt",
                    str(sentinel),
                    "file:///C:/Windows/win.ini",
                ):
                    avatar_service._remove_unused_avatar(db, url)
            self.assertTrue(sentinel.is_file(), "清理函数删除了头像目录之外的文件")
        finally:
            sentinel.unlink(missing_ok=True)


# ======================================================================
# T3 头像权限及静态资源
# ======================================================================


class TestT3PermissionsStatic(BaseA23):
    def setUp(self):
        super().setUp()
        self.client = self.new_client()

    def test_unauthenticated_upload_rejected(self):
        resp = self.client.post(
            "/users/me/avatar",
            files={"file": ("a.png", image_bytes("PNG"), "image/png")},
            headers=dict(CSRF),
        )
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_delete_rejected(self):
        resp = self.client.delete("/users/me/avatar", headers=dict(CSRF))
        self.assertEqual(resp.status_code, 401)

    def test_revoked_session_cannot_upload(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET revoked_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now(), "f": family},
            )

        resp = self.upload(self.client, pair, image_bytes("PNG"))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.inner_code(resp), "SESSION_REVOKED")

    def test_session_revoked_after_auth_before_txn_rejected(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE login_sessions SET revoked_at = :t "
                    "WHERE family_id = :f"
                ),
                {"t": utc_db_now(), "f": family},
            )

        self.assert_rejected(
            lambda: self.service_upload(uid, family, image_bytes("PNG")),
            status=401,
            code="SESSION_REVOKED",
        )

    def test_cannot_modify_other_user_avatar(self):
        uid_a, username_a, _ = self.new_user()
        uid_b, username_b, _ = self.new_user()
        pair_b, _ = self.login(username_b)

        resp = self.upload(self.client, pair_b, image_bytes("PNG"))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.avatar_url_of(uid_a))
        self.assertIsNotNone(self.avatar_url_of(uid_b))

    def test_csrf_required(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        resp = self.client.post(
            "/users/me/avatar",
            files={"file": ("a.png", image_bytes("PNG"), "image/png")},
            headers=self.bearer(pair),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.inner_code(resp), "CSRF_REJECTED")

    def test_processed_avatar_publicly_accessible(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url = self.upload(self.client, pair, image_bytes("PNG", (700, 300))).json()[
            "data"
        ]["avatar_url"]

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "image/webp")
        with Image.open(BytesIO(resp.content)) as im:
            self.assertEqual(im.format, "WEBP")
            self.assertLessEqual(max(im.size), 512)

    def test_staging_and_storage_not_exposed(self):
        settings.AVATAR_DIR.with_name(
            settings.AVATAR_DIR.name + "_staging"
        ).mkdir(parents=True, exist_ok=True)
        staging_file = settings.AVATAR_DIR.with_name(
            settings.AVATAR_DIR.name + "_staging"
        ) / ("a" * 32 + ".webp")
        staging_file.write_bytes(b"staging")

        try:
            self.assertEqual(
                self.client.get("/media/avatars_staging/" + staging_file.name).status_code,
                404,
            )
            self.assertEqual(
                self.client.get("/storage/avatars/" + staging_file.name).status_code,
                404,
            )
            self.assertEqual(
                self.client.get("/media/avatars/../avatars_staging/" + staging_file.name).status_code,
                404,
            )
        finally:
            staging_file.unlink(missing_ok=True)

    def test_path_traversal_blocked(self):
        for path in (
            "/media/avatars/..%2F..%2F.env",
            "/media/avatars/%2e%2e%2f%2e%2e%2f.env",
        ):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_symlink_not_followed(self):
        outside = TMP_AVATAR_ROOT / "outside-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link = settings.AVATAR_DIR / ("b" * 32 + ".webp")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            outside.unlink(missing_ok=True)
            self.skipTest(f"当前环境无法创建符号链接: {exc}")

        try:
            resp = self.client.get(AVATAR_PREFIX + link.name)
            self.assertEqual(resp.status_code, 404)
            self.assertNotIn(b"secret", resp.content)
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_only_avatar_directory_mounted(self):
        main_src = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn('"/media/avatars"', main_src)
        self.assertIn("follow_symlink=False", main_src)
        self.assertNotIn("/media/storage", main_src)


# ======================================================================
# T4 个人资料
# ======================================================================


class TestT4Profile(BaseA23):
    def setUp(self):
        super().setUp()
        self.client = self.new_client()

    def test_get_me_returns_latest_avatar(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        url = self.upload(self.client, pair, image_bytes("PNG")).json()[
            "data"
        ]["avatar_url"]

        resp = self.client.get("/users/me", headers=self.bearer(pair))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["avatar_url"], url)

    def test_get_me_returns_null_after_delete(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        self.upload(self.client, pair, image_bytes("PNG"))
        self.delete_req(self.client, pair)

        resp = self.client.get("/users/me", headers=self.bearer(pair))
        self.assertIsNone(resp.json()["data"]["avatar_url"])

    def test_get_me_fields_and_no_secrets(self):
        uid, username, email = self.new_user(nickname="NickA23")
        pair, _ = self.login(username)

        data = self.client.get("/users/me", headers=self.bearer(pair)).json()["data"]
        for key in (
            "id",
            "username",
            "nickname",
            "email",
            "avatar_url",
            "email_verified_at",
            "is_active",
        ):
            self.assertIn(key, data)
        self.assertEqual(data["email"], email)
        self.assertEqual(data["nickname"], "NickA23")

        blob = str(data).lower()
        self.assertNotIn("password_hash", blob)
        self.assertNotIn("refresh_token", blob)
        self.assertNotIn("token_hash", blob)

    def test_put_nickname_only_self(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        resp = self.client.put(
            f"/users/{uid}",
            json={"nickname": "UpdatedNick"},
            headers=self.auth_headers(pair),
        )
        self.assertEqual(resp.status_code, 200)
        with engine.connect() as conn:
            nickname = conn.execute(
                text("SELECT nickname FROM users WHERE id = :i"), {"i": uid}
            ).scalar_one()
        self.assertEqual(nickname, "UpdatedNick")

    def test_put_cannot_change_security_fields(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)

        with engine.connect() as conn:
            before = conn.execute(
                text(
                    "SELECT email, password_hash, is_active "
                    "FROM users WHERE id = :i"
                ),
                {"i": uid},
            ).mappings().first()
            before = dict(before)

        resp = self.client.put(
            f"/users/{uid}",
            json={
                "nickname": "Evil",
                "email": "evil@example.com",
                "password_hash": "x",
                "is_active": False,
            },
            headers=self.auth_headers(pair),
        )
        self.assertEqual(resp.status_code, 200)

        with engine.connect() as conn:
            after = conn.execute(
                text(
                    "SELECT email, password_hash, is_active "
                    "FROM users WHERE id = :i"
                ),
                {"i": uid},
            ).mappings().first()
            after = dict(after)

        self.assertEqual(after["email"], before["email"])
        self.assertEqual(after["password_hash"], before["password_hash"])
        self.assertEqual(after["is_active"], before["is_active"])

    def test_put_other_user_forbidden(self):
        uid_a, _, _ = self.new_user()
        uid_b, username_b, _ = self.new_user()
        pair_b, _ = self.login(username_b)

        resp = self.client.put(
            f"/users/{uid_a}",
            json={"nickname": "Hacked"},
            headers=self.auth_headers(pair_b),
        )
        self.assertEqual(resp.status_code, 403)

    def test_profile_timezone_created_updated_utc8(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        data = self.client.get(
            f"/users/{uid}", headers=self.bearer(pair)
        ).json()["data"]

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT created_at, updated_at FROM users WHERE id = :i"),
                {"i": uid},
            ).mappings().first()

        for field in ("created_at", "updated_at"):
            parsed = datetime.fromisoformat(data[field])
            self.assertIsNotNone(parsed.tzinfo)
            self.assertEqual(parsed.utcoffset(), timedelta(hours=8))
            self.assertEqual(
                parsed.replace(tzinfo=None),
                row[field],
                f"{field} 与数据库值不一致",
            )

    def test_email_verified_at_utc(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        data = self.client.get("/users/me", headers=self.bearer(pair)).json()["data"]
        parsed = datetime.fromisoformat(data["email_verified_at"])
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(0))


# ======================================================================
# T5 认证数据清理
# ======================================================================


class TestT5AuthCleanup(BaseA23):
    def test_current_code_not_deleted(self):
        uid, _, email = self.new_user()
        self.mk_code(
            email,
            EmailCodePurpose.RESET_PASSWORD,
            "111111",
            user_id=uid,
        )

        run_auth_cleanup()
        self.assertIsNotNone(self.code_row(email, EmailCodePurpose.RESET_PASSWORD))

    def test_daily_quota_unaffected(self):
        uid, _, email = self.new_user()
        self.mk_code(email, EmailCodePurpose.LOGIN, "111111", user_id=uid)
        self.mk_code(email, EmailCodePurpose.LOGIN, "222222", user_id=uid)

        day_start = utc_db_now().replace(hour=0, minute=0, second=0, microsecond=0)
        with engine.connect() as conn:
            with SessionLocal() as db:
                before = verification_repository.count_email_sends(
                    db, email=email, since=day_start
                )

        run_auth_cleanup()

        with SessionLocal() as db:
            after = verification_repository.count_email_sends(
                db, email=email, since=day_start
            )
        self.assertEqual(before, after)
        self.assertEqual(after, 2)

    def test_rotated_unexpired_token_kept(self):
        uid, _, _ = self.new_user()
        family = self.mk_session(uid)
        token_hash = self.mk_token(
            uid,
            family,
            expires=utc_db_now() + timedelta(days=1),
            replaced="c" * 64,
        )

        run_auth_cleanup()

        with engine.connect() as conn:
            found = conn.execute(
                text("SELECT COUNT(*) FROM refresh_tokens WHERE token_hash = :h"),
                {"h": token_hash},
            ).scalar_one()
        self.assertEqual(int(found), 1)

    def test_replay_detection_still_works_after_cleanup(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        with SessionLocal() as db:
            auth_service.rotate_refresh_token(
                db, refresh_token=pair["refresh_token"], ip="127.0.0.1"
            )

        run_auth_cleanup()

        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as ctx:
                auth_service.rotate_refresh_token(
                    db, refresh_token=pair["refresh_token"], ip="127.0.0.1"
                )
        self.assertEqual(ctx.exception.detail["code"], "SESSION_REVOKED")

        family = self.family_of(pair)
        self.assertIsNotNone(self.session_row(family)["revoked_at"])

    def test_session_with_tokens_kept(self):
        uid, _, _ = self.new_user()
        old = utc_db_now() - timedelta(days=40)
        family = self.mk_session(uid, absolute=old, revoked=old)
        self.mk_token(uid, family, expires=utc_db_now() + timedelta(days=1))

        run_auth_cleanup()
        self.assertIsNotNone(self.session_row(family))

    def test_active_session_kept(self):
        uid, _, _ = self.new_user()
        family = self.mk_session(uid)

        run_auth_cleanup()
        self.assertIsNotNone(self.session_row(family))

    def test_old_auth_events_retained_30_days(self):
        uid, _, _ = self.new_user()
        old_event = utc_db_now() - timedelta(days=40)
        recent_event = utc_db_now() - timedelta(days=10)
        self.insert_event(uid, "TEST_A23_OLD", old_event)
        self.insert_event(uid, "TEST_A23_RECENT", recent_event)

        run_auth_cleanup()

        with engine.connect() as conn:
            old_left = conn.execute(
                text(
                    "SELECT COUNT(*) FROM auth_events "
                    "WHERE user_id = :u AND event_type = 'TEST_A23_OLD'"
                ),
                {"u": uid},
            ).scalar_one()
            recent_left = conn.execute(
                text(
                    "SELECT COUNT(*) FROM auth_events "
                    "WHERE user_id = :u AND event_type = 'TEST_A23_RECENT'"
                ),
                {"u": uid},
            ).scalar_one()
        self.assertEqual(int(old_left), 0)
        self.assertEqual(int(recent_left), 1)

    def test_rate_limit_and_lock_events_not_prematurely_deleted(self):
        uid, _, _ = self.new_user()
        two_days = utc_db_now() - timedelta(days=2)
        for event_type in ("PASSWORD_LOCKED", "PASSWORD_FAILED", "EMAIL_CODE_ATTEMPT"):
            self.insert_event(uid, event_type, two_days)

        run_auth_cleanup()

        with engine.connect() as conn:
            left = conn.execute(
                text(
                    "SELECT COUNT(*) FROM auth_events "
                    "WHERE user_id = :u AND created_at = :t"
                ),
                {"u": uid, "t": two_days},
            ).scalar_one()
        self.assertEqual(int(left), 3)

    def test_max_500_per_category(self):
        uid, _, _ = self.new_user()
        old = utc_db_now() - timedelta(days=40)
        rows = [
            {"u": uid, "e": "TEST_A23_BULK", "ip": "127.0.0.1", "c": old}
            for _ in range(505)
        ]
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO auth_events (user_id, event_type, ip, created_at) "
                    "VALUES (:u, :e, :ip, :c)"
                ),
                rows,
            )

        first = run_auth_cleanup()
        self.assertEqual(first["auth_events"], 500)

        with engine.connect() as conn:
            remaining = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM auth_events "
                        "WHERE user_id = :u AND event_type = 'TEST_A23_BULK'"
                    ),
                    {"u": uid},
                ).scalar_one()
            )
        self.assertGreater(remaining, 0)

        run_auth_cleanup()
        with engine.connect() as conn:
            remaining2 = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM auth_events "
                        "WHERE user_id = :u AND event_type = 'TEST_A23_BULK'"
                    ),
                    {"u": uid},
                ).scalar_one()
            )
        self.assertLess(remaining2, remaining)
        self.assertEqual(remaining2, 0)

    def test_repeat_execution_safe(self):
        uid, _, email = self.new_user()
        self.mk_code(email, EmailCodePurpose.LOGIN, "111111", user_id=uid)

        first = run_auth_cleanup()
        second = run_auth_cleanup()

        self.assertFalse(first["failed"])
        self.assertFalse(second["failed"])
        self.assertIsNotNone(self.code_row(email, EmailCodePurpose.LOGIN))

    def test_concurrent_cleanup_consistent(self):
        uid, _, _ = self.new_user()
        family = self.mk_session(uid)

        results = self.run_parallel(
            [lambda: run_auth_cleanup(), lambda: run_auth_cleanup()]
        )
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertTrue(all(r[1]["failed"] is False for r in results))
        self.assertIsNotNone(self.session_row(family))

    def test_cleanup_with_refresh_and_login_no_deadlock(self):
        uid, username, _ = self.new_user()

        def cleaner():
            return [run_auth_cleanup() for _ in range(3)]

        def operator():
            pair, _ = self.login(username)
            with SessionLocal() as db:
                new_pair = auth_service.rotate_refresh_token(
                    db, refresh_token=pair["refresh_token"], ip="127.0.0.1"
                )
            with SessionLocal() as db:
                revoked = auth_service.revoke_current_session(
                    db,
                    refresh_token=new_pair.refresh_token,
                    access_token=new_pair.access_token,
                    ip="127.0.0.1",
                )
            return revoked

        results = self.run_parallel([cleaner, operator])
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertTrue(results[1][1])


# ======================================================================
# T6 孤儿头像清理
# ======================================================================


class TestT6OrphanAvatars(BaseA23):
    def make_file(self, name, *, age_seconds=0, directory=None):
        directory = directory or settings.AVATAR_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(b"data")
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def test_referenced_avatar_kept(self):
        uid, _, _ = self.new_user()
        name = uuid.uuid4().hex + ".webp"
        self.make_file(name, age_seconds=25 * 3600)
        self.set_avatar_url(uid, AVATAR_PREFIX + name)

        avatar_service.cleanup_orphan_avatars()
        self.assertTrue((settings.AVATAR_DIR / name).exists())

    def test_recent_orphan_kept(self):
        name = uuid.uuid4().hex + ".webp"
        self.make_file(name, age_seconds=3600)

        avatar_service.cleanup_orphan_avatars()
        self.assertTrue((settings.AVATAR_DIR / name).exists())

    def test_old_orphan_deleted(self):
        name = uuid.uuid4().hex + ".webp"
        path = self.make_file(name, age_seconds=25 * 3600)

        avatar_service.cleanup_orphan_avatars()
        self.assertFalse(path.exists())

    def test_old_staging_orphan_deleted(self):
        staging = settings.AVATAR_DIR.with_name(
            settings.AVATAR_DIR.name + "_staging"
        )
        path = self.make_file(
            uuid.uuid4().hex + ".webp", age_seconds=25 * 3600, directory=staging
        )

        avatar_service.cleanup_orphan_avatars()
        self.assertFalse(path.exists())

    def test_non_system_named_files_kept(self):
        legacy = self.make_file("photo.webp", age_seconds=25 * 3600)
        other = self.make_file("abc.png", age_seconds=25 * 3600)

        avatar_service.cleanup_orphan_avatars()
        self.assertTrue(legacy.exists())
        self.assertTrue(other.exists())

    def test_symlink_not_followed(self):
        outside = TMP_AVATAR_ROOT / "orphan-target.txt"
        outside.write_text("target", encoding="utf-8")
        link = settings.AVATAR_DIR / (uuid.uuid4().hex + ".webp")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            outside.unlink(missing_ok=True)
            self.skipTest(f"当前环境无法创建符号链接: {exc}")

        old = time.time() - 25 * 3600
        try:
            os.utime(outside, (old, old))
        except OSError:
            pass

        try:
            avatar_service.cleanup_orphan_avatars()
            self.assertTrue(link.is_symlink(), "清理函数删除了符号链接")
            self.assertTrue(outside.exists(), "清理函数跟随符号链接删除了目标文件")
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_concurrent_cleanup_and_upload_no_false_delete(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        def uploader():
            return self.service_upload(
                uid, family, image_bytes("PNG", (48, 48), "RGB", (7, 7, 7))
            )

        results = self.run_parallel(
            [uploader, lambda: avatar_service.cleanup_orphan_avatars()]
        )
        self.assertEqual(results[0][0], "ok")

        final_url = self.avatar_url_of(uid)
        self.assertIsNotNone(final_url)
        self.assertTrue(self.path_of_url(final_url).is_file())


# ======================================================================
# T7 Worker 集成
# ======================================================================


WORKER_SRC = Path("app/jobs/plan_expiration_worker.py")
CONFIG_SRC = Path("app/config.py")


class TestT7Worker(BaseA23):
    def test_cleanup_flag_default_off(self):
        self.assertFalse(settings.AUTH_CLEANUP_ENABLED)

    def test_cleanup_flag_exposed_on_settings(self):
        self.assertTrue(
            hasattr(settings, "AUTH_CLEANUP_ENABLED"),
            "AUTH_CLEANUP_ENABLED 未定义为 Settings 字段，"
            "settings.AUTH_CLEANUP_ENABLED 会抛出 AttributeError",
        )

    def test_worker_module_imports(self):
        try:
            importlib.invalidate_caches()
            importlib.import_module("app.jobs.plan_expiration_worker")
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f"Worker 模块无法导入: {type(exc).__name__}: {exc}"
            )

    def _capture_jobs(self, enabled):
        import app.jobs.plan_expiration_worker as worker

        jobs = []

        class FakeScheduler:
            running = False

            def __init__(self, *args, **kwargs):
                pass

            def add_job(self, func, trigger, id, **kwargs):
                jobs.append((id, trigger, kwargs))

            def start(self):
                raise KeyboardInterrupt

            def shutdown(self, wait=False):
                pass

        with mock.patch.object(worker, "BlockingScheduler", FakeScheduler), \
                mock.patch.object(
                    worker, "run_due_plan_check", return_value={}
                ), \
                mock.patch.object(
                    worker.settings, "AUTH_CLEANUP_ENABLED", enabled
                ):
            worker.main()

        return {job[0]: job for job in jobs}

    def test_enabled_registers_hourly_cleanup(self):
        jobs = self._capture_jobs(enabled=True)

        self.assertIn("expire_study_plans", jobs)
        self.assertIn("auth_cleanup", jobs)
        self.assertEqual(jobs["auth_cleanup"][1], "interval")
        self.assertEqual(jobs["auth_cleanup"][2]["hours"], 1)
        self.assertEqual(jobs["expire_study_plans"][2]["minutes"], 5)

    def test_disabled_registers_only_plan_job(self):
        jobs = self._capture_jobs(enabled=False)

        self.assertIn("expire_study_plans", jobs)
        self.assertNotIn("auth_cleanup", jobs)

    def test_plan_job_interval_still_5min(self):
        source = WORKER_SRC.read_text(encoding="utf-8")
        self.assertIn('id="expire_study_plans"', source)
        self.assertIn("minutes=5", source)

    def test_once_cli_compatible(self):
        source = WORKER_SRC.read_text(encoding="utf-8")
        self.assertIn('"--once"', source)
        self.assertIn("run_due_plan_check()", source)

    def test_no_separate_background_process_required(self):
        source = WORKER_SRC.read_text(encoding="utf-8")
        self.assertNotIn("multiprocessing", source)
        self.assertNotIn("subprocess", source)

    def test_ai_guard_and_business_untouched(self):
        source = WORKER_SRC.read_text(encoding="utf-8")
        for token in ("ai_", "knowledge", "ai_guard", "quiz"):
            self.assertNotIn(token, source)

    def test_cleanup_failure_does_not_block_other_jobs(self):
        with mock.patch.object(
            cleanup_repository,
            "delete_expired_verifications",
            side_effect=RuntimeError("cleanup boom"),
        ):
            result = run_auth_cleanup()
        self.assertTrue(result["failed"])
        # 失败被吞掉，不向上抛出，不会阻断其他定时任务
        self.assertIsInstance(result, dict)


# ======================================================================
# T8 验证码安全时间边界
# ======================================================================


class TestT8CodeTimeBoundary(BaseA23):
    def do_change_password(self, uid, family, old=PASSWORD, new=NEW_PASSWORD):
        with SessionLocal() as db:
            account_service.change_password(
                db,
                user_id=uid,
                family_id=family,
                data=PasswordChangeRequest(
                    old_password=old, new_password=new
                ),
                ip="127.0.0.1",
            )

    def do_reset(self, email, code, new_password=ALT_PASSWORD):
        with SessionLocal() as db:
            return account_service.reset_password(
                db,
                data=PasswordResetRequest(
                    email=email, code=code, new_password=new_password
                ),
                ip="127.0.0.1",
            )

    def test_reset_code_before_password_change_invalid_after(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        self.mk_code_at(
            email,
            EmailCodePurpose.RESET_PASSWORD,
            "333333",
            utc_db_now() - timedelta(seconds=60),
            user_id=uid,
        )
        self.do_change_password(uid, family)

        self.assert_rejected(
            lambda: self.do_reset(email, "333333"),
            status=400,
            code="EMAIL_CODE_INVALID",
        )

    def test_reset_code_reissued_after_change_works(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        self.do_change_password(uid, family)

        self.mk_code_at(
            email,
            EmailCodePurpose.RESET_PASSWORD,
            "444444",
            utc_db_now() + timedelta(seconds=1),
            user_id=uid,
        )

        self.assertEqual(self.do_reset(email, "444444"), uid)

    def test_login_code_before_change_invalid_after(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        self.mk_code_at(
            email,
            EmailCodePurpose.LOGIN,
            "555555",
            utc_db_now() - timedelta(seconds=60),
            user_id=uid,
        )
        self.do_change_password(uid, family)

        with self.assertRaises(HTTPException) as ctx:
            with SessionLocal() as db:
                auth_service.login_with_email(
                    db,
                    email=email,
                    code="555555",
                    ip="127.0.0.1",
                    user_agent="ua",
                )
        self.assertEqual(ctx.exception.detail["code"], "EMAIL_CODE_INVALID")

    def test_change_email_old_code_not_reusable_after_change(self):
        uid, username, old_email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        new_email = f"{self.PREFIX}n{uuid.uuid4().hex[:6]}@example.com"

        self.mk_code_at(
            old_email,
            EmailCodePurpose.CHANGE_EMAIL_OLD,
            "111111",
            utc_db_now() + timedelta(seconds=1),
            user_id=uid,
            family_id=family,
        )
        self.mk_code_at(
            new_email,
            EmailCodePurpose.CHANGE_EMAIL_NEW,
            "222222",
            utc_db_now() + timedelta(seconds=1),
            user_id=uid,
            family_id=family,
        )
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
                ip="127.0.0.1",
            )

        # 换绑前生成、未消费的另一枚旧邮箱验证码，安全状态变化后不可复用
        pre_code_id = self.mk_code_at(
            old_email,
            EmailCodePurpose.CHANGE_EMAIL_OLD,
            "121212",
            utc_db_now() - timedelta(seconds=5),
            user_id=uid,
            family_id=family,
        )

        newer_email = f"{self.PREFIX}x{uuid.uuid4().hex[:6]}@example.com"
        self.mk_code_at(
            newer_email,
            EmailCodePurpose.CHANGE_EMAIL_NEW,
            "343434",
            utc_db_now() + timedelta(seconds=1),
            user_id=uid,
            family_id=family,
        )
        self.assert_rejected(
            lambda: self._change_email(
                uid, family, "121212", newer_email, "343434"
            ),
            status=400,
            code="EMAIL_CODE_INVALID",
        )
        with engine.connect() as conn:
            consumed = conn.execute(
                text(
                    "SELECT consumed_at FROM email_verifications WHERE id = :i"
                ),
                {"i": pre_code_id},
            ).scalar_one()
        self.assertIsNone(consumed)

    def _change_email(self, uid, family, old_code, new_email, new_code):
        with SessionLocal() as db:
            account_service.change_email(
                db,
                user_id=uid,
                family_id=family,
                data=EmailChangeRequest(
                    password=PASSWORD,
                    old_email_code=old_code,
                    new_email=new_email,
                    new_email_code=new_code,
                ),
                ip="127.0.0.1",
            )

    def test_change_email_codes_bound_to_user_and_family(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        other_family = str(uuid.uuid4())

        self.mk_code_at(
            email,
            EmailCodePurpose.CHANGE_EMAIL_OLD,
            "666666",
            utc_db_now() + timedelta(seconds=1),
            user_id=uid,
            family_id=family,
        )

        with SessionLocal() as db:
            wrong_family = verification_service.check_verification(
                db,
                email=email,
                purpose=EmailCodePurpose.CHANGE_EMAIL_OLD,
                code="666666",
                user_id=uid,
                family_id=other_family,
            )
            wrong_user = verification_service.check_verification(
                db,
                email=email,
                purpose=EmailCodePurpose.CHANGE_EMAIL_OLD,
                code="666666",
                user_id=uid + 1,
                family_id=family,
            )
            right = verification_service.check_verification(
                db,
                email=email,
                purpose=EmailCodePurpose.CHANGE_EMAIL_OLD,
                code="666666",
                user_id=uid,
                family_id=family,
            )

        self.assertIsNone(wrong_family)
        self.assertIsNone(wrong_user)
        self.assertIsNotNone(right)

    def test_register_code_unaffected(self):
        username = self.PREFIX + "r" + uuid.uuid4().hex[:8]
        email = f"{self.PREFIX}reg{uuid.uuid4().hex[:6]}@example.com"
        self.mk_code(
            email,
            EmailCodePurpose.REGISTER,
            "777777",
        )

        with SessionLocal() as db:
            pair, user = auth_service.register(
                db,
                data=UserCreate(
                    username=username,
                    password=PASSWORD,
                    email=email,
                    code="777777",
                ),
                ip="127.0.0.1",
                user_agent="ua",
            )
        self.assertTrue(pair.access_token)
        self.assertEqual(user["email"], email)
        self.assertIsNotNone(self.code_row(email, EmailCodePurpose.REGISTER))

    def test_boundary_equality_and_neighbors(self):
        fixed = utc_db_now() - timedelta(minutes=5)

        # created_at == password_updated_at -> 拒绝
        uid, _, email = self.new_user()
        self.set_password_updated_at(uid, fixed)
        self.set_email_verified_at(uid, fixed)
        self.mk_code_at(
            email,
            EmailCodePurpose.RESET_PASSWORD,
            "101010",
            fixed,
            user_id=uid,
        )
        self.assert_rejected(
            lambda: self.do_reset(email, "101010"),
            status=400,
            code="EMAIL_CODE_INVALID",
        )

        # created_at < password_updated_at -> 拒绝
        uid2, _, email2 = self.new_user()
        self.set_password_updated_at(uid2, fixed)
        self.set_email_verified_at(uid2, fixed)
        self.mk_code_at(
            email2,
            EmailCodePurpose.RESET_PASSWORD,
            "101011",
            fixed - timedelta(seconds=1),
            user_id=uid2,
        )
        self.assert_rejected(
            lambda: self.do_reset(email2, "101011"),
            status=400,
            code="EMAIL_CODE_INVALID",
        )

        # created_at > password_updated_at -> 可用
        uid3, _, email3 = self.new_user()
        self.set_password_updated_at(uid3, fixed)
        self.set_email_verified_at(uid3, fixed)
        self.mk_code_at(
            email3,
            EmailCodePurpose.RESET_PASSWORD,
            "101012",
            fixed + timedelta(seconds=1),
            user_id=uid3,
        )
        self.assertEqual(self.do_reset(email3, "101012"), uid3)

    def test_code_issue_vs_password_change_concurrency(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        def issue():
            verification_service.request_email_code(
                email=email,
                purpose=EmailCodePurpose.RESET_PASSWORD,
                request_ip="127.0.0.1",
            )

        def change():
            self.do_change_password(uid, family)

        results = self.run_parallel([issue, change])
        self.assertEqual([r[0] for r in results], ["ok", "ok"])

        sent = [c for (e, p, c) in self.sent if e == email and p == "RESET_PASSWORD"]
        self.assertTrue(sent)
        code = sent[-1]

        row = self.code_row(email, EmailCodePurpose.RESET_PASSWORD)
        with engine.connect() as conn:
            updated = conn.execute(
                text("SELECT password_updated_at FROM users WHERE id = :i"),
                {"i": uid},
            ).scalar_one()

        if row["created_at"] <= updated:
            self.assert_rejected(
                lambda: self.do_reset(email, code),
                status=400,
                code="EMAIL_CODE_INVALID",
            )
        else:
            self.assertEqual(self.do_reset(email, code), uid)


# ======================================================================
# T9 当前退出修复
# ======================================================================


class TestT9Logout(BaseA23):
    def expired_access(self, uid, family):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(uid),
            "family_id": family,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    def revoke(self, refresh=None, access=None):
        with SessionLocal() as db:
            return auth_service.revoke_current_session(
                db,
                refresh_token=refresh,
                access_token=access,
                ip="127.0.0.1",
            )

    def test_refresh_only_revokes(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        self.assertTrue(self.revoke(refresh=pair["refresh_token"]))
        self.assertIsNotNone(self.session_row(self.family_of(pair))["revoked_at"])

    def test_access_only_revokes(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        self.assertTrue(self.revoke(access=pair["access_token"]))
        self.assertIsNotNone(self.session_row(self.family_of(pair))["revoked_at"])

    def test_expired_access_with_valid_refresh_revokes(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        expired = self.expired_access(uid, family)
        self.assertIsNone(security.decode_access_token(expired))

        self.assertTrue(
            self.revoke(refresh=pair["refresh_token"], access=expired)
        )
        self.assertIsNotNone(self.session_row(family)["revoked_at"])

    def test_mismatched_tokens_return_409_without_revoke(self):
        uid, username, _ = self.new_user()
        pair1, _ = self.login(username)
        pair2, _ = self.login(username)
        family1 = self.family_of(pair1)
        family2 = self.family_of(pair2)

        with self.assertRaises(HTTPException) as ctx:
            self.revoke(
                refresh=pair2["refresh_token"],
                access=pair1["access_token"],
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["code"], "SESSION_MISMATCH")

        self.assertIsNone(self.session_row(family1)["revoked_at"])
        self.assertIsNone(self.session_row(family2)["revoked_at"])

    def test_both_invalid_returns_false(self):
        self.assertFalse(self.revoke(refresh="not-a-token", access="bad-token"))
        self.assertFalse(self.revoke())

    def test_repeat_logout_safe(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)

        self.assertTrue(self.revoke(refresh=pair["refresh_token"]))
        self.assertTrue(self.revoke(refresh=pair["refresh_token"]))

    def test_old_access_fails_after_logout(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        self.revoke(
            refresh=pair["refresh_token"], access=pair["access_token"]
        )

        from app.core.deps import authenticate_access

        with self.assertRaises(HTTPException) as ctx:
            authenticate_access(pair["access_token"])
        self.assertEqual(ctx.exception.detail["code"], "SESSION_REVOKED")

    def test_transaction_failure_does_not_report_success(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)

        client = self.new_client()
        client.cookies.set(
            settings.REFRESH_COOKIE_NAME,
            pair["refresh_token"],
            path=settings.REFRESH_COOKIE_PATH,
        )

        boom = OperationalError("COMMIT", {}, Exception("commit failed"))
        with mock.patch.object(SessionTransaction, "commit", side_effect=boom):
            resp = client.post(
                "/auth/logout",
                headers=self.auth_headers(pair),
            )

        self.assertEqual(resp.status_code, 500)
        self.assertIsNone(self.session_row(family)["revoked_at"])

    def test_route_logout_returns_revoked_flag(self):
        uid, username, _ = self.new_user()
        pair, _ = self.login(username)
        client = self.new_client()
        client.cookies.set(
            settings.REFRESH_COOKIE_NAME,
            pair["refresh_token"],
            path=settings.REFRESH_COOKIE_PATH,
        )

        resp = client.post("/auth/logout", headers=self.auth_headers(pair))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"]["session_revoked"])


# ======================================================================
# T10 历史回归及缺陷复测
# ======================================================================


class TestT10Regression(BaseA23):
    def test_p1_1_unified_error_envelope(self):
        client = self.new_client()
        resp = client.get("/users/me")
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body.get("code"), 401)
        self.assertIn("message", body)
        self.assertIn("data", body)

    def test_p1_2_verify_password_type_guard(self):
        good = security.hash_password(PASSWORD)
        self.assertFalse(security.verify_password(None, good))
        self.assertFalse(security.verify_password(PASSWORD, None))
        self.assertFalse(security.verify_password(PASSWORD, 12345))
        self.assertFalse(security.verify_password(PASSWORD, "bad-format"))
        self.assertTrue(security.verify_password(PASSWORD, good))
        self.assertFalse(security.verify_password("wrong", good))

    def test_p1_3_reset_code_invalidated_after_password_change(self):
        uid, username, email = self.new_user()
        pair, _ = self.login(username)
        family = self.family_of(pair)
        self.mk_code_at(
            email,
            EmailCodePurpose.RESET_PASSWORD,
            "909090",
            utc_db_now() - timedelta(seconds=60),
            user_id=uid,
        )
        with SessionLocal() as db:
            account_service.change_password(
                db,
                user_id=uid,
                family_id=family,
                data=PasswordChangeRequest(
                    old_password=PASSWORD, new_password=NEW_PASSWORD
                ),
                ip="127.0.0.1",
            )

        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as ctx:
                account_service.reset_password(
                    db,
                    data=PasswordResetRequest(
                        email=email,
                        code="909090",
                        new_password=ALT_PASSWORD,
                    ),
                    ip="127.0.0.1",
                )
        self.assertEqual(ctx.exception.detail["code"], "EMAIL_CODE_INVALID")

    def test_a2_acceptance_suite_present(self):
        for name in (
            "tests/test_auth_a1_1_acceptance.py",
            "tests/test_auth_a1_3_acceptance.py",
            "tests/test_auth_a2_account_session_acceptance.py",
        ):
            self.assertTrue(Path(name).is_file(), f"缺少回归测试文件 {name}")

    def test_login_and_profile_do_not_leak_secrets(self):
        uid, username, email = self.new_user()
        pair, user = self.login(username)
        blob = str(user).lower()
        self.assertNotIn("password_hash", blob)
        self.assertNotIn("token", blob)

        client = self.new_client()
        data = client.get("/users/me", headers=self.bearer(pair)).json()["data"]
        blob2 = str(data).lower()
        self.assertNotIn("password_hash", blob2)
        self.assertNotIn("token_hash", blob2)

    def test_remaining_security_surface_review(self):
        """静态审查：确认敏感查询未把密码摘要带入公开 DTO。"""
        src = Path("app/services/auth/auth_service.py").read_text(encoding="utf-8")
        self.assertIn("UserPublic.model_validate", src)
        schema = Path("app/schemas/user.py").read_text(encoding="utf-8")
        self.assertNotIn("password_hash", schema)
        self.assertNotIn("refresh_token", schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)