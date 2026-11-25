from sqlalchemy import text
from sqlalchemy.engine import Connection


def acquire_lock(
    connection: Connection,
    name: str,
    timeout: int,
) -> bool:

    result = connection.execute(
        text("""
            SELECT GET_LOCK(:name, :timeout)
        """),
        {
            "name": name,
            "timeout": timeout,
        },
    ).scalar_one()

    return result == 1


def release_lock(
    connection: Connection,
    name: str,
) -> bool:

    result = connection.execute(
        text("""
            SELECT RELEASE_LOCK(:name)
        """),
        {"name": name},
    ).scalar_one()

    return result == 1