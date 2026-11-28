"""A6.1 测试数据库安全守卫自检。"""

import pytest

from app.database import engine
from tests.db_guard import (
    ALLOWED_TEST_DATABASES,
    ensure_isolated_database,
)


class _FakeResult:
    def __init__(self, name: str):
        self._name = name

    def scalar_one(self) -> str:
        return self._name


class _FakeConnection:
    def __init__(self, name: str):
        self._name = name

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return _FakeResult(self._name)


class _FakeEngine:
    def __init__(self, name: str):
        self._name = name

    def connect(self):
        return _FakeConnection(self._name)


def test_allowed_database_is_only_isolated_test_db():
    assert ALLOWED_TEST_DATABASES == frozenset({"ssp_v3_admin_test"})


def test_current_connection_is_isolated_test_db():
    assert ensure_isolated_database(engine) == "ssp_v3_admin_test"


@pytest.mark.parametrize(
    "name",
    ["ssp_a0_migrate2", "ssp_v3_admin_dev", "ssp_production", "mysql"],
)
def test_guard_rejects_non_isolated_databases(name):
    with pytest.raises(RuntimeError) as caught:
        ensure_isolated_database(_FakeEngine(name))

    assert "测试仅允许连接隔离库" in str(caught.value)