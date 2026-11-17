
import logging
import sys
from datetime import timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.plans import plan_lifecycle_repository
from app.services.plans import plan_lifecycle_service


logger = logging.getLogger(__name__)


def run_due_plan_check() -> dict:
    """执行一次计划到期检查"""

    today = business_today()

    # 先读取需要处理的计划 ID
    with SessionLocal() as db:
        plan_ids = (
            plan_lifecycle_repository.find_expired_plan_ids(
                db=db,
                today=today,
                limit=500,
            )
        )

    ended_count = 0
    failed_count = 0

    # 每个计划使用独立事务。
    # 某个计划失败，不影响其他计划。
    for plan_id in plan_ids:
        with SessionLocal() as db:
            try:
                changed = (
                    plan_lifecycle_service.expire_due_plan(
                        db=db,
                        plan_id=plan_id,
                        today=today,
                    )
                )

                if changed:
                    ended_count += 1

            except Exception:
                failed_count += 1

                logger.exception(
                    "计划 %s 自动到期处理失败",
                    plan_id,
                )

    result = {
        "checked_count": len(plan_ids),
        "ended_count": ended_count,
        "failed_count": failed_count,
    }

    logger.info("到期检查结果：%s", result)

    if len(plan_ids) == 500:
        logger.warning(
            "本次达到500条处理上限，剩余计划将在下次检查"
        )

    return result


def main():
    """启动独立的定时任务进程"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # 使用 UTC 调度间隔，
    # 业务日期始终由 business_today() 判断。
    scheduler = BlockingScheduler(
        timezone=timezone.utc,
    )

    scheduler.add_job(
        run_due_plan_check,
        trigger="interval",
        minutes=5,
        id="expire_study_plans",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        replace_existing=True,
    )

    # 启动时立即检查一次。
    # 避免程序重启后遗漏已经到期的计划。
    run_due_plan_check()

    logger.info("计划自动到期 Worker 已启动")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 正在停止")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    if "--once" in sys.argv:
        logging.basicConfig(level=logging.INFO)
        print(run_due_plan_check())
    else:
        main()
