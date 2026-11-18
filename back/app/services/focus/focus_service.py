
from datetime import datetime, timedelta
from typing import NoReturn
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories.focus import focus_repository
from app.schemas.focus import FocusStart


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
MAX_STOPWATCH_SECONDS = 24 * 60 * 60


def _now() -> datetime:
    """北京时间，无时区对象，与 MySQL DATETIME(6) 一致。"""
#移除时区信息，但保留北京时间对应的年月日、时分秒
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def _reject(
    message: str,
    status_code: int = 409,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=message,
    )


def _elapsed_seconds(
    start: datetime,
    end: datetime,
) -> int:
    """计算非负整秒，不依赖前端定时器。"""

    return max(
        0,
        int((end - start).total_seconds()),
    )


def _complete(
    db: Session,
    session: dict,
    ended_at: datetime,
    focused_seconds: int,
) -> None:
    """完成并保存一次专注会话。"""

    session["status"] = "COMPLETED"
    session["focused_seconds"] = focused_seconds
    session["running_started_at"] = None
    session["ended_at"] = ended_at

    focus_repository.save_session(
        db=db,
        session=session,
    )


def _auto_settle(
    db: Session,
    session: dict,
    now: datetime,
) -> bool:
    """
    判断当前会话是否应自动完成。

    返回 True：已经完成并更新数据库（尚未 commit）。
    返回 False：保持当前运行状态。
    """

    if session["status"] not in ("RUNNING", "PAUSED"):
        return False

    # 自由正计时：从 started_at 起最长存续 24 小时。
    if session["session_type"] == "STOPWATCH":

        deadline = (
            session["started_at"]
            + timedelta(seconds=MAX_STOPWATCH_SECONDS)
        )

        if now < deadline:
            return False

        focused = session["focused_seconds"]

        if session["status"] == "RUNNING":
            focused += _elapsed_seconds(
                session["running_started_at"],
                deadline,
            )

        _complete(
            db=db,
            session=session,
            ended_at=deadline,
            focused_seconds=focused,
        )
        return True

    # 番茄钟只有在 RUNNING 状态下累计专注。
    if session["status"] != "RUNNING":
        return False

    remaining = (
        session["planned_seconds"]
        - session["focused_seconds"]
    )

    running_seconds = _elapsed_seconds(
        session["running_started_at"],
        now,
    )

    if running_seconds < remaining:
        return False

    # 已达到目标：结束时间是实际达到目标的时间，
    # 而不是用户重新打开网页的时间。
    ended_at = (
        session["running_started_at"]
        + timedelta(seconds=max(0, remaining))
    )

    _complete(
        db=db,
        session=session,
        ended_at=ended_at,
        focused_seconds=session["planned_seconds"],
    )
    return True


def _validate_start(
    db: Session,
    user_id: int,
    data: FocusStart,
) -> None:
    """验证计时模式和可选任务关联。"""

    if data.session_type == "POMODORO":
        if data.planned_seconds is None:
            _reject("番茄钟必须设置计划时长", 422)

    else:
        if data.planned_seconds is not None:
            _reject("自由正计时不能设置计划时长", 422)

    if data.task_id is not None and data.plan_id is None:
        _reject("关联任务时必须同时指定计划", 422)

    if data.plan_id is None:
        return

    if not focus_repository.has_valid_plan(
        db=db,
        plan_id=data.plan_id,
        user_id=user_id,
    ):
        _reject("只能关联当前用户的 ACTIVE 计划")

    if data.task_id is None:
        return

    if not focus_repository.has_valid_task(
        db=db,
        task_id=data.task_id,
        plan_id=data.plan_id,
        user_id=user_id,
    ):
        _reject("关联任务不存在或当前不可用")


def start_session(
    db: Session,
    user_id: int,
    data: FocusStart,
) -> dict:
    """开始专注，保证每个用户最多一个活动会话。"""

    try:
        # 先锁用户，再检查活动会话。
        focus_repository.lock_user(db, user_id)

        now = _now()

        active = focus_repository.find_active_session(
            db=db,
            user_id=user_id,
        )

        if active is not None:
            # 已超时的会话先自动结算。
            if not _auto_settle(db, active, now):
                _reject("你已经有一个正在进行的专注")

        _validate_start(
            db=db,
            user_id=user_id,
            data=data,
        )

        session_id = focus_repository.insert_session(
            db=db,
            user_id=user_id,
            session_type=data.session_type,
            planned_seconds=data.planned_seconds,
            plan_id=data.plan_id,
            task_id=data.task_id,
            now=now,
            focus_date=business_today(),
        )

        session = focus_repository.find_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
        )
        if session is None:
            _reject("创建专注会话后无法读取记录", 500)

        assert session is not None

        db.commit()
        return session

    except Exception:
        db.rollback()
        raise


def sync_current(
    db: Session,
    user_id: int,
) -> dict:
    """同步当前状态，并补结算已到期的会话。"""

    try:
        focus_repository.lock_user(db, user_id)

        current = focus_repository.find_active_session(
            db=db,
            user_id=user_id,
        )

        auto_completed = None

        if current is not None:
            if _auto_settle(db, current, _now()):
                auto_completed = current
                current = None

        db.commit()

        return {
            "current": current,
            "auto_completed": auto_completed,
        }

    except Exception:
        db.rollback()
        raise

#专注状态机
def operate_session(
    db: Session,
    user_id: int,
    session_id: int,
    action: str,
) -> dict:
    """统一处理暂停、继续、结束和取消。"""

    try:
        focus_repository.lock_user(db, user_id)

        session = focus_repository.find_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
            for_update=True,
        )

        if session is None:
            _reject("专注记录不存在", 404)

        now = _now()

        # 先检查是否已经自动达到结束条件。
        if _auto_settle(db, session, now):
            db.commit()
            return session

        status = session["status"]

        # 重复结束 / 取消不会重复结算。
        if action == "finish" and status == "COMPLETED":
            db.commit()
            return session

        if action == "cancel" and status == "CANCELLED":
            db.commit()
            return session

        if status in ("COMPLETED", "CANCELLED"):
            _reject("专注已经结束，不能再次操作")
#暂停专注
        if action == "pause":
            if status != "RUNNING":
                _reject("只有正在运行的专注才能暂停")


            session["focused_seconds"] += _elapsed_seconds(
                session["running_started_at"],
                now,
            )

            session["running_started_at"] = None
            session["status"] = "PAUSED"

        elif action == "resume":
            if status != "PAUSED":
                _reject("只有暂停中的专注才能继续")

            session["running_started_at"] = now
            session["status"] = "RUNNING"

        elif action == "finish":
            if status == "RUNNING":
                session["focused_seconds"] += _elapsed_seconds(
                    session["running_started_at"],
                    now,
                )

            # 提前结束也记录实际专注时长。
            session["status"] = "COMPLETED"
            session["running_started_at"] = None
            session["ended_at"] = now

        elif action == "cancel":
            # 用户明确放弃：不计入有效专注统计。
            session["status"] = "CANCELLED"
            session["focused_seconds"] = 0
            session["running_started_at"] = None
            session["ended_at"] = now

        else:
            _reject("不支持的专注操作", 422)

        focus_repository.save_session(
            db=db,
            session=session,
        )

        db.commit()
        return session

    except Exception:
        db.rollback()
        raise


def get_history(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
) -> dict:
    return focus_repository.list_history(
        db=db,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )
