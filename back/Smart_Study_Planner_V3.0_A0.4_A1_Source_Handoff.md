# Smart Study Planner V3.0 — A0.4 · A1 源码交接（完整文件）

> 生成时间：2026-11-27　代码基线：`d511f08` + A0.4 修正
> 说明：本文件只读交接，不含密码、Token、密钥、完整 `.env`。
> 用途：A1 管理员系统开发所需的最新完整源码与 role 接入点清单。

## 1. 文件清单与哈希

| 文件 | 行数 | 字节 | SHA256 |
| --- | --- | --- | --- |
| `app\core\deps.py` | 75 | 1727 | `EF4544CEB80700823655665A72DD8D9E5BB943ECFDB72D90B06AA0CF43DBF90F` |
| `app\repositories\auth\session_repository.py` | 306 | 7359 | `105BB9E3BD68CCD134FD122050F51A2686784FFC17D45E69C44EC0F27213BBB0` |
| `app\repositories\auth\user_repository.py` | 267 | 5333 | `DB92611DC268914518A495F712F82218B844180D59966EDC9039B4F57F790A86` |
| `app\schemas\user.py` | 101 | 1882 | `A466FD23CF72D1131156F4667DCD38E4B3453FDED2DEAD55E4CF2A25A90CD884` |

## 2. UserPublic 构造点与相关 SELECT 查询

新增 `users.role` 后，以下位置决定 `role` 是否出现在响应中：

| 位置 | 作用 | role 影响 |
| --- | --- | --- |
| `app/schemas/user.py:94` | `UserPublic` 定义（白名单） | **必须新增 `role` 字段**，否则所有响应丢弃 role |
| `app/services/auth/auth_service.py:58-72` | `public_user()`：`UserPublic.model_validate(user)` | 依赖 `UserPublic`；传入 dict 需含 role |
| `app/services/auth/auth_service.py:223` | 登录成功返回 `(pair, public_user(user))` | `user` 来自 `find_by_username/find_by_email`（SELECT 需加 role） |
| `app/api/routes/users.py:82` | `GET/PUT /users/me` 返回 | `user` 来自 `find_profile`（SELECT 需加 role） |
| `app/services/auth/user_service.py:51` | `**public_user(user)` 组装资料响应 | 同上 |
| `app/services/auth/account_service.py:455` | 修改邮箱/密码后返回 | 同上 |
| `app/schemas/auth.py:83` | `LoginResult.user: UserPublic` | 结构体，随 UserPublic 自动扩展 |
| `app/repositories/auth/session_repository.py:85` | `find_session_with_user`：JOIN users，认证每请求走这里 | **必须加 `u.role`**，否则 `get_current_user` 拿不到角色 |
| `app/repositories/auth/user_repository.py:14/40/66` | `find_by_id` / `find_by_username` / `find_by_email` | 加 `role` 才能支撑管理端与登录响应 |
| `app/repositories/auth/user_repository.py:132-142` | `find_profile` | 加 `role` 才能让 `/users/me` 返回 |
| `app/repositories/auth/user_repository.py:256` | `find_avatar`（只取 avatar_url） | 无需修改 |

### 2.1 最小介入结论

1. **认证必需**：`find_session_with_user` 增加 `u.role`（否则 `require_admin` 不可用）。
2. **响应必需**：`UserPublic` 增加 `role: Literal['USER','ADMIN']`，并同步 `find_profile` 与登录查询的 SELECT。
3. **不需要**：`find_avatar`、token 相关查询、`auth_events` 查询。
4. 若希望 JWT 不携带 role（推荐），则每次请求由 `find_session_with_user` 实时取 role，改角色即时生效。

## 3. 完整源码

### 3.1 `app\core\deps.py`

```python
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.core.security import (
    decode_access_token_detailed,
)

from app.database import SessionLocal

from app.services.auth import session_service


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def authenticate_access(
    token: str | None,
) -> dict:
    """验证 Access Token 和对应登录会话"""

    if not token:
        session_service.reject_auth(
            "INVALID_TOKEN",
            "缺少 Access Token",
        )

    payload, error_code = (
        decode_access_token_detailed(token)
    )

    if payload is None:

        if error_code == "ACCESS_EXPIRED":

            session_service.reject_auth(
                "ACCESS_EXPIRED",
                "Access Token 已过期",
            )

        session_service.reject_auth(
            error_code or "INVALID_TOKEN",
            "Access Token 无效",
        )

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    # 使用独立的短生命周期数据库 Session。
    # 避免认证查询提前开启业务事务。
    with SessionLocal() as db:

        return session_service.get_active_session(
            db,
            user_id=user_id,
            family_id=family_id,
        )


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> dict:

    user = authenticate_access(token)

    # 保存身份，用于请求成功后的活跃时间更新。
    request.state.auth_identity = (
        user["id"],
        user["family_id"],
    )

    return user
```

### 3.2 `app\repositories\auth\session_repository.py`

```python
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_session(
    db: Session,
    *,
    family_id: str,
    user_id: int,
    user_agent: str | None,
    now: datetime,
    absolute_expires_at: datetime,
) -> None:

    db.execute(
        text("""
            INSERT INTO login_sessions (
                family_id,
                user_id,
                user_agent,
                created_at,
                last_activity_at,
                absolute_expires_at
            )
            VALUES (
                :family_id,
                :user_id,
                :user_agent,
                :now,
                :now,
                :absolute_expires_at
            )
        """),
        {
            "family_id": family_id,
            "user_id": user_id,
            "user_agent": user_agent,
            "now": now,
            "absolute_expires_at": absolute_expires_at,
        },
    )


def find_session(
    db: Session,
    user_id: int,
    family_id: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT family_id, user_id, user_agent,
               created_at, last_activity_at,
               absolute_expires_at,
               revoked_at, revoked_reason
        FROM login_sessions
        WHERE family_id = :family_id
          AND user_id = :user_id
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {
            "family_id": family_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return dict(row) if row is not None else None


def find_session_with_user(
    db: Session,
    user_id: int,
    family_id: str,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT u.id,
                   u.username,
                   u.nickname,
                   u.email,
                   u.email_verified_at,
                   u.avatar_url,
                   u.is_active,

                   s.family_id,
                   s.last_activity_at,
                   s.absolute_expires_at,
                   s.revoked_at

            FROM login_sessions AS s

            INNER JOIN users AS u
                ON s.user_id = u.id

            WHERE s.family_id = :family_id
              AND s.user_id = :user_id
        """),
        {
            "family_id": family_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return dict(row) if row is not None else None

#在用户访问网站时，有条件地更新登录会话的最后活跃时间。
def touch_session(
    db: Session,
    *,#表示它后面的参数必须使用关键字传参
    user_id: int,
    family_id: str,
    now: datetime,
    idle_cutoff: datetime,
    write_cutoff: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET last_activity_at = :now
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
              AND last_activity_at <= :write_cutoff
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
            "write_cutoff": write_cutoff,
        },
    )

    return result.rowcount


def list_active_sessions(
    db: Session,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT family_id,
                   user_agent,
                   created_at,
                   last_activity_at,
                   absolute_expires_at
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
            ORDER BY last_activity_at DESC
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def revoke_session(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    now: datetime,
    reason: str,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET revoked_at = :now,
                revoked_reason = :reason
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "now": now,
            "reason": reason,
        },
    )

    return result.rowcount


def revoke_all_sessions(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    reason: str,
    exclude_family_id: str | None = None,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET revoked_at = :now,
                revoked_reason = :reason
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND (
                  :exclude_family_id IS NULL
                  OR family_id <> :exclude_family_id
              )
        """),
        {
            "user_id": user_id,
            "now": now,
            "reason": reason,
            "exclude_family_id": exclude_family_id,
        },
    )

    return result.rowcount





def count_active_sessions(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
        },
    ).scalar_one()

    return int(count)


def list_active_sessions_page(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
    limit: int,
    offset: int,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                family_id,
                user_agent,
                created_at,
                last_activity_at,
                absolute_expires_at
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
            ORDER BY last_activity_at DESC,
                     family_id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]
```

### 3.3 `app\repositories\auth\user_repository.py`

```python
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_by_id(
    db: Session,
    user_id: int,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE id = :user_id
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row is not None else None


def find_by_username(
    db: Session,
    username: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE username = :username
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"username": username},
    ).mappings().first()

    return dict(row) if row is not None else None


def find_by_email(
    db: Session,
    email: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE email = :email
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"email": email},
    ).mappings().first()

    return dict(row) if row is not None else None


def insert_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    email: str,
    nickname: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            INSERT INTO users (
                username,
                password_hash,
                password_updated_at,
                email,
                email_verified_at,
                nickname
            )
            VALUES (
                :username,
                :password_hash,
                :now,
                :email,
                :now,
                :nickname
            )
        """),
        {
            "username": username,
            "password_hash": password_hash,
            "email": email,
            "nickname": nickname,
            "now": now,
        },
    )

    return int(result.lastrowid)

def find_profile(
    db: Session,
    user_id: int,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT
                id,
                username,
                nickname,
                email,
                avatar_url,
                email_verified_at,
                is_active,
                created_at,
                updated_at
            FROM users
            WHERE id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row is not None else None


def update_nickname(
    db: Session,
    *,
    user_id: int,
    nickname: str,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET nickname = :nickname,
                updated_at = NOW()
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "nickname": nickname,
        },
    )

    return result.rowcount



def update_password(
    db: Session,
    *,
    user_id: int,
    password_hash: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET password_hash = :password_hash,
                password_updated_at = :now
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "password_hash": password_hash,
            "now": now,
        },
    )

    return result.rowcount


def update_email(
    db: Session,
    *,
    user_id: int,
    email: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET email = :email,
                email_verified_at = :now
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "email": email,
            "now": now,
        },
    )

    return result.rowcount





#头像

def update_avatar(
    db: Session,
    *,
    user_id: int,
    avatar_url: str | None,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET avatar_url = :avatar_url
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "avatar_url": avatar_url,
        },
    )

    return result.rowcount


def list_avatar_urls(db: Session) -> set[str]:

    rows = db.execute(
        text("""
            SELECT avatar_url
            FROM users
            WHERE avatar_url IS NOT NULL
        """)
    ).scalars().all()

    return set(rows)



    
    
```

### 3.4 `app\schemas\user.py`

```python
from datetime import datetime
from typing import Annotated

from email_validator import (
    validate_email,
    EmailNotValidError,
)
from pydantic import (
    BaseModel,
    AfterValidator,
    StringConstraints,
)


def normalize_email(value: str) -> str:
    """验证邮箱格式，并统一邮箱存储格式"""

    try:
        result = validate_email(
            value.strip().lower(),
            check_deliverability=False,
        )

    except EmailNotValidError:
        raise ValueError("邮箱格式不正确") from None

    email = result.normalized.lower()

    if len(email) > 254:
        raise ValueError("邮箱长度不能超过254字符")

    return email


# ==================== 公共字段类型 ====================

EmailAddress = Annotated[
    str,
    AfterValidator(normalize_email),
]

Username = Annotated[
    str,
    StringConstraints(
        min_length=4,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
    ),
]

Password = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=64,
    ),
]

Nickname = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=50,
    ),
]

EmailCode = Annotated[
    str,
    StringConstraints(
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]{6}$",
    ),
]


# ==================== 请求模型 ====================

class UserCreate(BaseModel):
    username: Username
    password: Password
    email: EmailAddress
    code: EmailCode
    nickname: Nickname | None = None


class UserUpdate(BaseModel):
    nickname: Nickname


# ==================== 响应模型 ====================

class UserPublic(BaseModel):
    id: int
    username: str
    nickname: str | None
    email: EmailAddress
    avatar_url: str | None = None
    email_verified_at: datetime
    is_active: bool
```

