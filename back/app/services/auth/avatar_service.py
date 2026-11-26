import logging
import os
import re
import time

from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import settings
from app.repositories.auth import user_repository

from app.services.auth import (
    session_service,
    rate_limit_service,
)


logger = logging.getLogger(__name__)

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

AVATAR_URL_PREFIX = "/media/avatars/"

AVATAR_LOCK_SCOPE = "avatar-storage"

AVATAR_FILENAME_PATTERN = re.compile(
    r"^[0-9a-f]{32}\.webp$"
)


#  图片校验与转换


def _reject_image(
    message: str,
    status_code: int = 400,
) -> None:

    session_service.reject_auth(
        "INVALID_AVATAR",
        message,
        status_code=status_code,
    )


def _convert_image(file: BinaryIO) -> bytes:
    """校验图片并转换为 WebP，不操作数据库"""

    raw = file.read(
        settings.AVATAR_MAX_BYTES + 1,
    )

    if not raw:
        _reject_image("请选择有效的图片")

    if len(raw) > settings.AVATAR_MAX_BYTES:
        _reject_image(
            "头像文件不能超过允许的大小",
            status_code=413,
        )

    try:
        with Image.open(BytesIO(raw)) as source:

            # 根据真实文件内容判断格式，
            # 不信任客户端传来的文件扩展名。
            if source.format not in ALLOWED_FORMATS:
                _reject_image(
                    "仅支持 JPG、PNG 和 WebP 图片"
                )

            if getattr(source, "n_frames", 1) != 1:
                _reject_image("不支持动态图片")

            width, height = source.size

            if (
                width <= 0
                or height <= 0
                or width * height
                > settings.AVATAR_MAX_PIXELS
            ):
                _reject_image("图片解码像素数过大")

            # 完成实际解码
            source.load()

            # 根据 EXIF 修正手机照片的方向
            image = ImageOps.exif_transpose(
                source,
            )

            # 等比例缩放
            image.thumbnail(
                (
                    settings.AVATAR_MAX_SIZE,
                    settings.AVATAR_MAX_SIZE,
                ),
                Image.Resampling.LANCZOS,
            )

            # 保留透明通道
            image = image.convert("RGBA")

            # 不保留原图附带的元数据
            image.info.clear()

            output = BytesIO()

            image.save(
                output,
                format="WEBP",
                quality=85,
            )

            return output.getvalue()

    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        SyntaxError,
    ):
        _reject_image("图片文件损坏或格式不正确")

    raise RuntimeError("头像转换异常")


# ==================== 文件操作 ====================


def _avatar_path(
    avatar_url: str | None,
) -> Path | None:
    """仅接受系统生成的头像路径"""

    if not avatar_url:
        return None

    if not avatar_url.startswith(
        AVATAR_URL_PREFIX,
    ):
        return None

    filename = avatar_url[
        len(AVATAR_URL_PREFIX):
    ]

    if not AVATAR_FILENAME_PATTERN.fullmatch(
        filename,
    ):
        return None

    return settings.AVATAR_DIR / filename


def _staging_dir() -> Path:

    return settings.AVATAR_DIR.with_name(
        settings.AVATAR_DIR.name + "_staging"
    )


def _write_avatar(
    filename: str,
    content: bytes,
) -> Path:
    """先写临时文件，再发布完整图片"""

    settings.AVATAR_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging = _staging_dir()

    staging.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = staging / filename
    destination = settings.AVATAR_DIR / filename

    try:
        # xb：仅允许创建新文件
        with temporary.open("xb") as file:
            file.write(content)

        # 同一文件系统内原子移动
        os.replace(
            temporary,
            destination,
        )

    finally:
        temporary.unlink(missing_ok=True)

    return destination


def _remove_file(path: Path) -> bool:

    try:
        if path.is_symlink():
            return False

        path.unlink(missing_ok=True)

        return True

    except OSError:
        logger.warning(
            "Avatar file cleanup failed"
        )

        return False


def _remove_unused_avatar(
    db: Session,
    avatar_url: str | None,
) -> None:

    path = _avatar_path(avatar_url)

    if path is None:
        return

    try:
        references = (
            user_repository.list_avatar_urls(db)
        )

        if avatar_url not in references:
            _remove_file(path)

    except Exception:
        # 数据库提交已经完成。
        # 清理失败交给定时任务处理。
        logger.warning(
            "Old avatar cleanup failed"
        )


# ==================== 上传与更换头像 ====================


def upload_avatar(
    *,
    user_id: int,
    family_id: str,
    file: BinaryIO,
) -> dict:

    # 较耗时的图片处理不占用数据库锁
    content = _convert_image(file)

    filename = f"{uuid4().hex}.webp"

    avatar_url = (
        AVATAR_URL_PREFIX + filename
    )

    # 上传、更换、删除和孤儿文件清理
    # 使用相同的跨进程命名锁
    with rate_limit_service.admission_session(
        AVATAR_LOCK_SCOPE,
    ) as db:

        user, _ = (
            session_service.lock_current_user(
                db,
                user_id=user_id,
                family_id=family_id,
            )
        )

        old_avatar = user["avatar_url"]

        destination = _write_avatar(
            filename,
            content,
        )

        try:
            affected = (
                user_repository.update_avatar(
                    db,
                    user_id=user_id,
                    avatar_url=avatar_url,
                )
            )

            if affected != 1:
                raise RuntimeError(
                    "头像数据库更新失败"
                )

        except Exception:
            # 尚未尝试提交事务，
            # 可以安全清理本次新文件。
            _remove_file(destination)
            raise

        # 如果 commit 结果不确定，
        # 暂时保留新文件，交给定时清理。
        db.commit()

        # 只有成功提交后才删除旧头像
        _remove_unused_avatar(
            db,
            old_avatar,
        )

    return {
        "avatar_url": avatar_url,
    }


# ==================== 删除头像 ====================


def delete_avatar(
    *,
    user_id: int,
    family_id: str,
) -> dict:

    with rate_limit_service.admission_session(
        AVATAR_LOCK_SCOPE,
    ) as db:

        user, _ = (
            session_service.lock_current_user(
                db,
                user_id=user_id,
                family_id=family_id,
            )
        )

        old_avatar = user["avatar_url"]

        if old_avatar is not None:

            user_repository.update_avatar(
                db,
                user_id=user_id,
                avatar_url=None,
            )

        db.commit()

        _remove_unused_avatar(
            db,
            old_avatar,
        )

    return {
        "avatar_url": None,
    }


# ==================== 清理孤儿头像 ====================


def cleanup_orphan_avatars() -> int:

    removed = 0

    with rate_limit_service.admission_session(
        AVATAR_LOCK_SCOPE,
    ) as db:

        referenced_urls = (
            user_repository.list_avatar_urls(db)
        )

        # 至少保留24小时安全宽限期
        cutoff = time.time() - 86400

        directories = (
            (settings.AVATAR_DIR, True),
            (_staging_dir(), False),
        )

        for directory, is_public in directories:

            if not directory.exists():
                continue

            for path in directory.iterdir():

                if not AVATAR_FILENAME_PATTERN.fullmatch(
                    path.name,
                ):
                    continue

                if path.is_symlink():
                    continue

                if not path.is_file():
                    continue

                url = (
                    AVATAR_URL_PREFIX + path.name
                )

                if (
                    is_public
                    and url in referenced_urls
                ):
                    continue

                try:
                    if path.stat().st_mtime >= cutoff:
                        continue

                except FileNotFoundError:
                    continue

                if _remove_file(path):
                    removed += 1

    return removed