"""测试数据库安全守卫。

A6.1 起，回归测试仅允许连接隔离库 ssp_v3_admin_test。
任何写入、删除或清理发生前，必须先在模块导入或 conftest 阶段通过本守卫。
"""

from sqlalchemy import text


ALLOWED_TEST_DATABASES = frozenset({"ssp_v3_admin_test"})


def ensure_isolated_database(bind) -> str:
    """校验当前连接指向的数据库，不符合要求时立即中止。"""

    with bind.connect() as conn:
        name = conn.execute(text("SELECT DATABASE()")).scalar_one()

    if name not in ALLOWED_TEST_DATABASES:
        raise RuntimeError(
            "测试仅允许连接隔离库 "
            f"{sorted(ALLOWED_TEST_DATABASES)}，当前数据库: {name}"
        )

    return name