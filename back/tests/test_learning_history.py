from datetime import datetime, time, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.history import router
from app.core.clock import business_today
from app.core.deps import get_current_user
from app.database import get_db
from app.services import history_service


def history_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        for statement in (
            "CREATE TABLE study_plans (id INTEGER, user_id INTEGER, name TEXT, deleted_at TEXT)",
            "CREATE TABLE plan_steps (id INTEGER, plan_id INTEGER, parent_id INTEGER, name TEXT, deleted_at TEXT, sort_order INTEGER)",
            "CREATE TABLE daily_tasks (id INTEGER, plan_id INTEGER, step_id INTEGER, content TEXT, deleted_at TEXT)",
            "CREATE TABLE study_records (id INTEGER, task_id INTEGER, user_id INTEGER, event_type TEXT, recorded_value INTEGER, recorded_at TEXT)",
            "CREATE TABLE knowledge_notes (id INTEGER, user_id INTEGER, plan_id INTEGER, title TEXT, deleted_at TEXT)",
            "CREATE TABLE knowledge_review_records (id INTEGER, note_id INTEGER, user_id INTEGER, reviewed_at TEXT)",
        ):
            conn.execute(text(statement))
        today = business_today()
        yesterday_at = datetime.combine(today - timedelta(days=1), time(9)).isoformat(sep=" ")
        today_at = datetime.combine(today, time(9)).isoformat(sep=" ")
        conn.execute(text("INSERT INTO study_plans VALUES (1,1,'Current',NULL),(2,1,'Deleted','x'),(3,2,'Other',NULL)"))
        conn.execute(text("INSERT INTO plan_steps VALUES (10,1,NULL,'Group','x',0),(11,1,10,'Leaf','x',0),(12,1,NULL,'Active',NULL,1),(20,2,NULL,'Hidden',NULL,0),(30,3,NULL,'Other',NULL,0)"))
        conn.execute(text("INSERT INTO daily_tasks VALUES (100,1,11,'Old task','x'),(101,1,12,'New task',NULL),(102,2,20,'Hidden task',NULL),(103,3,30,'Other task',NULL)"))
        conn.execute(text("INSERT INTO study_records VALUES (1,100,1,'BOOLEAN_COMPLETE',NULL,:y),(2,101,1,'NUMERIC_PROGRESS',4,:t),(3,102,1,'BOOLEAN_COMPLETE',NULL,:t),(4,103,2,'BOOLEAN_COMPLETE',NULL,:t),(5,101,2,'BOOLEAN_COMPLETE',NULL,:t)"), {"y": yesterday_at, "t": today_at})
        conn.execute(text("INSERT INTO knowledge_notes VALUES (50,1,1,'Old note','x'),(51,2,3,'Other note',NULL)"))
        conn.execute(text("INSERT INTO knowledge_review_records VALUES (1,50,1,:t),(2,51,2,:t),(3,51,1,:t)"), {"t": today_at})
    return Session(engine)


def test_checkin_history_matches_statistics_soft_delete_scope():
    with history_db() as db:
        result = history_service.list_checkins(db, 1, 7, None, 1, 20)
        assert result["total"] == 2
        assert [item["id"] for item in result["items"]] == [2, 1]
        assert result["items"][1]["task_deleted_at"] == "x"
        assert history_service.list_checkins(db, 1, None, 1, 2, 1)["items"][0]["id"] == 1
        assert history_service.list_checkins(db, 1, None, 3, 1, 20)["total"] == 0
        summary = history_service.get_checkin_summary(db, 1)
        assert [plan["id"] for plan in summary["plans"]] == [1]
        assert {step["id"] for step in summary["steps"]} == {10, 11, 12}
        assert {item["step_id"] for item in summary["dates"]} == {11, 12}


def test_review_history_preserves_deleted_note_and_checks_ownership():
    with history_db() as db:
        result = history_service.list_reviews(db, 1, 1, 20)
        assert result["total"] == 1
        assert result["items"][0]["note_title"] == "Old note"
        assert result["items"][0]["note_deleted_at"] == "x"


def test_checkin_route_accepts_all_display_ranges(monkeypatch):
    seen = []

    def list_checkins(db, user_id, days, plan_id, page, page_size):
        seen.append((user_id, days, plan_id, page, page_size))
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    monkeypatch.setattr(history_service, "list_checkins", list_checkins)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    app.dependency_overrides[get_db] = lambda: None

    with TestClient(app) as client:
        for days in ("7", "30", "all"):
            assert client.get("/history/checkins", params={"days": days}).status_code == 200
        assert client.get("/history/checkins").status_code == 200
        assert client.get("/history/checkins", params={"days": "8"}).status_code == 422

    assert [item[1] for item in seen] == [7, 30, None, 7]


def test_review_route_returns_timestamp_used_by_page():
    seed_session = history_db()
    engine = seed_session.get_bind()
    seed_session.close()

    def test_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    app.dependency_overrides[get_db] = test_db

    with TestClient(app) as client:
        response = client.get("/history/reviews")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["reviewed_at"]
