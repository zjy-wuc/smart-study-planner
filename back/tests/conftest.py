"""全量测试会话级数据库安全防线。

在任何测试执行前校验实际连接的数据库；不满足时立即中止整个会话。
"""

import pytest

from app.database import engine
from tests.db_guard import ensure_isolated_database


@pytest.fixture(scope="session", autouse=True)
def _enforce_isolated_test_database():
    try:
        ensure_isolated_database(engine)
    except RuntimeError as error:
        pytest.exit(str(error), returncode=2)

    yield