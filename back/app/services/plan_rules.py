
from datetime import date, timedelta


def get_plan_days(
    start_date: date,
    end_date: date,
) -> list[date]:
    """
    获取计划的所有执行日期。
    开始和结束日期均包含在内。
    """

    if start_date > end_date:
        raise ValueError(
            "开始日期不能晚于结束日期"
        )

    total_days = (
        end_date - start_date
    ).days + 1

    return [
        start_date + timedelta(days=i)
        for i in range(total_days)
    ]


def distribute_numeric_target(
    total_target: int,
    start_date: date,
    end_date: date,
) -> dict[date, int]:
    """
    NUMERIC 任务自动平均分配。

    前 D-1 天分配相同数量，
    余数全部放在最后一天。
    """

    if (
        type(total_target) is not int
        or total_target < 0
    ):
        raise ValueError(
            "总目标必须是非负整数"
        )

    days = get_plan_days(
        start_date,
        end_date,
    )

    base = total_target // len(days)

    result = {
        day: base
        for day in days[:-1]
    }

    result[days[-1]] = (
        total_target
        - base * (len(days) - 1)
    )

    return result
