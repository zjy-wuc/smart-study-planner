from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


AdminAction = Literal[
    "BAN_USER",
    "UNBAN_USER",
    "REVOKE_SESSIONS",
    "UPDATE_AI_CONFIG",
]

AdminUserAction = Literal[
    "BAN_USER",
    "UNBAN_USER",
    "REVOKE_SESSIONS",
]

AdminUserStatus = Literal["ACTIVE", "DISABLED"]

AdminTargetType = Literal["USER", "AI_CONFIG"]

AdminReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]


class AdminActionRequest(BaseModel):
    reason: AdminReason