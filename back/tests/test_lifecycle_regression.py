"""Stage 11 plan lifecycle regression tests. All fixtures roll back after each test."""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.database import engine
from app.jobs import plan_expiration_worker
from app.repositories.plans import plan_lifecycle_repository
from app.schemas.active_step import ActiveStepNode, ActiveStepTreeCreate
from app.schemas.active_task import ActiveTaskUpdate
from app.schemas.step import StepRule
from app.api.routes import plan_lifecycle as plan_lifecycle_route
from app.services.steps import active_step_service
from app.services.tasks import active_task_service, task_service
from app.services.plans import plan_lifecycle_service
from app.services.rollovers import rollover_service


class PlanLifecycleRegression(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.outer = self.conn.begin()
        self.db = Session(bind=self.conn, join_transaction_mode="create_savepoint")
        self.today = business_today()
        self.user = self.sql(
            "INSERT INTO users (username, password_hash) VALUES (:name, 'test')",
            name="lifecycle_test_" + uuid4().hex,
        ).lastrowid
        self.plan = self.new_plan("ACTIVE", -2, 5)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.conn.close()

    def sql(self, query, **params):
        return self.db.execute(text(query), params)

    def new_plan(self, status, start_offset, end_offset):
        return self.sql(
            "INSERT INTO study_plans (user_id,name,start_date,end_date,status) "
            "VALUES (:u,'test',:s,:e,:st)",
            u=self.user,
            s=self.today + timedelta(days=start_offset),
            e=self.today + timedelta(days=end_offset),
            st=status,
        ).lastrowid

    def step(self, task_type="BOOLEAN", plan=None):
        result = self.sql(
            "INSERT INTO plan_steps (plan_id,name,node_type,task_type) "
            "VALUES (:p,'test','LEAF',:t)",
            p=self.plan if plan is None else plan,
            t=task_type,
        ).lastrowid
        self.db.commit()
        return result

    def task(self, step, task_type, day, target=None, actual=0,
             status="PENDING", plan=None):
        result = self.sql(
            "INSERT INTO daily_tasks "
            "(plan_id,step_id,task_date,task_type,content,target_quantity,actual_quantity,status) "
            "VALUES (:p,:s,:d,:t,'test',:q,:a,:st)",
            p=self.plan if plan is None else plan,
            s=step,
            d=self.today + timedelta(days=day),
            t=task_type,
            q=target,
            a=actual,
            st=status,
        ).lastrowid
        self.db.commit()
        return result

    def record(self, task_id, event_type="BOOLEAN_COMPLETE", value=None, day=0):
        self.sql(
            "INSERT INTO study_records (task_id,user_id,event_type,recorded_value,task_date) "
            "VALUES (:t,:u,:e,:v,:d)",
            t=task_id,
            u=self.user,
            e=event_type,
            v=value,
            d=self.today + timedelta(days=day),
        )
        self.db.commit()

    def link(self, source, target, quantity=None):
        self.sql(
            "INSERT INTO task_rollovers (source_task_id,target_task_id,quantity) "
            "VALUES (:s,:t,:q)",
            s=source,
            t=target,
            q=quantity,
        )
        self.db.commit()

    def row(self, task_id):
        return dict(
            self.sql("SELECT * FROM daily_tasks WHERE id=:id", id=task_id)
            .mappings().one()
        )

    def plan_row(self, plan_id=None):
        return dict(
            self.sql(
                "SELECT * FROM study_plans WHERE id=:id",
                id=self.plan if plan_id is None else plan_id,
            ).mappings().one()
        )

    def reject(self, callback, code=409):
        with self.assertRaises(HTTPException) as caught:
            callback()
        self.assertEqual(caught.exception.status_code, code)

    def test_L01_active_plan_ended_early(self):
        step = self.step()
        completed = self.task(step, "BOOLEAN", -1, status="COMPLETED")
        started = self.task(step, "BOOLEAN", 0, status="IN_PROGRESS")
        pending = self.task(step, "BOOLEAN", 1)
        result = plan_lifecycle_service.end_plan_early(
            self.db, self.plan, self.user,
        )
        self.assertEqual(result["status"], "ENDED")
        self.assertEqual(result["end_mode"], "EARLY")
        self.assertEqual(result["ended_task_count"], 1)
        self.assertEqual(result["deleted_task_count"], 1)
        self.assertEqual(self.plan_row()["status"], "ENDED")
        self.assertEqual(self.row(completed)["status"], "COMPLETED")
        self.assertIsNone(self.row(completed)["deleted_at"])
        self.assertEqual(self.row(started)["status"], "ENDED")
        self.assertIsNone(self.row(started)["deleted_at"])
        self.assertIsNotNone(self.row(pending)["deleted_at"])

    def test_L02_numeric_history_with_zero_actual_is_ended(self):
        step = self.step("NUMERIC")
        task = self.task(step, "NUMERIC", 0, 50, 0, "PENDING")
        self.record(task, "NUMERIC_PROGRESS", 30)
        result = plan_lifecycle_service.end_plan_early(
            self.db, self.plan, self.user,
        )
        self.assertEqual(result["ended_task_count"], 1)
        self.assertEqual(result["deleted_task_count"], 0)
        row = self.row(task)
        self.assertEqual(row["status"], "ENDED")
        self.assertIsNone(row["deleted_at"])
        self.assertEqual(row["actual_quantity"], 0)

    def test_L03_numeric_rollover_source_is_untouched(self):
        step = self.step("NUMERIC")
        source = self.task(step, "NUMERIC", -1, 100, 60, "COMPLETED")
        target = self.task(step, "NUMERIC", 1, 40)
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=40 WHERE id=:id",
            id=source,
        )
        self.link(source, target, 40)
        self.db.commit()
        plan_lifecycle_service.end_plan_early(self.db, self.plan, self.user)
        row = self.row(source)
        self.assertEqual(row["status"], "COMPLETED")
        self.assertEqual(row["target_quantity"], 100)
        self.assertEqual(row["actual_quantity"], 60)
        self.assertEqual(row["rollover_out_quantity"], 40)
        self.assertIsNone(row["deleted_at"])
        self.assertEqual(
            self.sql(
                "SELECT COUNT(*) FROM task_rollovers WHERE source_task_id=:id",
                id=source,
            ).scalar(),
            1,
        )

    def test_L04_boolean_rollover_history_preserved(self):
        step = self.step()
        source = self.task(step, "BOOLEAN", 0)
        target = self.task(step, "BOOLEAN", 1)
        self.link(source, target)
        plan_lifecycle_service.end_plan_early(self.db, self.plan, self.user)
        self.assertIsNotNone(self.row(source)["deleted_at"])
        self.assertIsNotNone(self.row(target)["deleted_at"])
        self.assertEqual(self.row(source)["status"], "PENDING")
        self.assertEqual(
            self.sql(
                "SELECT COUNT(*) FROM task_rollovers WHERE source_task_id=:id",
                id=source,
            ).scalar(),
            1,
        )

    def test_L05_completed_history_unchanged(self):
        step = self.step("NUMERIC")
        task = self.task(step, "NUMERIC", -1, 100, 100, "COMPLETED")
        self.sql(
            "UPDATE daily_tasks SET completed_at='2026-01-02 03:04:05' WHERE id=:id",
            id=task,
        )
        self.record(task, "NUMERIC_PROGRESS", 100, -1)
        self.db.commit()
        before = self.row(task)
        records_before = self.sql(
            "SELECT COUNT(*) FROM study_records WHERE task_id=:id", id=task,
        ).scalar()
        plan_lifecycle_service.end_plan_early(self.db, self.plan, self.user)
        after = self.row(task)
        for field in ("status", "completed_at", "actual_quantity", "deleted_at"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(
            self.sql(
                "SELECT COUNT(*) FROM study_records WHERE task_id=:id", id=task,
            ).scalar(),
            records_before,
        )

    def test_L06_ended_plan_cannot_be_ended_twice(self):
        plan_lifecycle_service.end_plan_early(self.db, self.plan, self.user)
        pending = self.task(self.step(), "BOOLEAN", 2)
        self.reject(
            lambda: plan_lifecycle_service.end_plan_early(
                self.db, self.plan, self.user,
            )
        )
        self.assertIsNone(self.row(pending)["deleted_at"])
        self.assertEqual(
            plan_lifecycle_repository.mark_plan_ended(self.db, self.plan),
            0,
        )

    def test_L07_draft_plan_cannot_be_ended(self):
        draft = self.new_plan("DRAFT", 0, 5)
        self.db.commit()
        self.reject(
            lambda: plan_lifecycle_service.end_plan_early(
                self.db, draft, self.user,
            )
        )
        self.assertEqual(self.plan_row(draft)["status"], "DRAFT")

    def test_L08_normal_expiration_keeps_tasks(self):
        plan = self.new_plan("ACTIVE", -10, -3)
        step = self.step("BOOLEAN", plan=plan)
        pending = self.task(step, "BOOLEAN", -5, plan=plan)
        started = self.task(step, "BOOLEAN", -4, status="IN_PROGRESS", plan=plan)
        self.db.commit()
        records_before = self.sql("SELECT COUNT(*) FROM study_records").scalar()
        changed = plan_lifecycle_service.expire_due_plan(
            self.db, plan, self.today,
        )
        self.assertTrue(changed)
        self.assertEqual(self.plan_row(plan)["status"], "ENDED")
        self.assertIsNotNone(self.plan_row(plan)["ended_at"])
        for task_id in (pending, started):
            row = self.row(task_id)
            self.assertIsNone(row["deleted_at"])
        self.assertEqual(self.row(pending)["status"], "PENDING")
        self.assertEqual(self.row(started)["status"], "IN_PROGRESS")
        self.assertEqual(
            self.sql("SELECT COUNT(*) FROM study_records").scalar(),
            records_before,
        )

    def test_L09_end_date_boundary(self):
        plan = self.new_plan("ACTIVE", -5, 0)
        self.db.commit()
        expired = plan_lifecycle_repository.find_expired_plan_ids(
            self.db, self.today,
        )
        self.assertNotIn(plan, expired)
        self.assertFalse(
            plan_lifecycle_service.expire_due_plan(self.db, plan, self.today)
        )
        self.assertEqual(self.plan_row(plan)["status"], "ACTIVE")
        self.sql("UPDATE study_plans SET end_date=:d WHERE id=:id",
                 d=self.today - timedelta(days=1), id=plan)
        self.db.commit()
        self.assertIn(
            plan,
            plan_lifecycle_repository.find_expired_plan_ids(self.db, self.today),
        )
        self.assertTrue(
            plan_lifecycle_service.expire_due_plan(self.db, plan, self.today)
        )
        self.assertEqual(self.plan_row(plan)["status"], "ENDED")

    def test_L10_worker_is_idempotent(self):
        plan = self.new_plan("ACTIVE", -6, -2)
        self.db.commit()

        def session_factory():
            return Session(
                bind=self.conn,
                join_transaction_mode="create_savepoint",
            )

        with patch.object(
            plan_expiration_worker, "SessionLocal", new=session_factory,
        ), patch.object(
            plan_expiration_worker, "business_today", return_value=self.today,
        ):
            first = plan_expiration_worker.run_due_plan_check()
            second = plan_expiration_worker.run_due_plan_check()

        self.assertGreaterEqual(first["checked_count"], 1)
        self.assertGreaterEqual(first["ended_count"], 1)
        self.assertEqual(self.plan_row(plan)["status"], "ENDED")
        self.assertEqual(second["ended_count"], 0)
        self.assertEqual(second["failed_count"], 0)

    def test_L11_ended_plan_rejects_checkin(self):
        plan = self.new_plan("ENDED", -2, 5)
        boolean_step = self.step("BOOLEAN", plan=plan)
        boolean_task = self.task(
            boolean_step, "BOOLEAN", 0, status="PENDING", plan=plan,
        )
        numeric_step = self.step("NUMERIC", plan=plan)
        numeric_task = self.task(
            numeric_step, "NUMERIC", 0, 100, 0, "PENDING", plan=plan,
        )
        self.db.commit()
        self.reject(
            lambda: task_service.complete_boolean_task(
                self.db, boolean_task, self.user,
            )
        )
        self.reject(
            lambda: task_service.update_numeric_task(
                self.db, numeric_task, self.user, 10,
            )
        )

    def test_L12_ended_plan_rejects_rollover(self):
        plan = self.new_plan("ENDED", -2, 5)
        step = self.step("BOOLEAN", plan=plan)
        task = self.task(step, "BOOLEAN", 0, status="PENDING", plan=plan)
        self.db.commit()
        self.reject(
            lambda: rollover_service.rollover_task(
                self.db, task, self.user, self.today + timedelta(days=1),
            )
        )

    def test_L13_ended_plan_rejects_edits(self):
        plan = self.new_plan("ENDED", -2, 5)
        step = self.step("BOOLEAN", plan=plan)
        task = self.task(step, "BOOLEAN", 2, status="PENDING", plan=plan)
        self.db.commit()
        self.reject(
            lambda: active_task_service.update_active_task(
                self.db, task, self.user, ActiveTaskUpdate(content="changed"),
            )
        )
        data = ActiveStepTreeCreate(
            parent_id=None,
            node=ActiveStepNode(
                name="new leaf",
                node_type="LEAF",
                rule=StepRule(
                    task_type="BOOLEAN",
                    schedule_mode="REPEAT",
                    repeat_content="reading",
                ),
            ),
        )
        self.reject(
            lambda: active_step_service.create_active_tree(
                self.db, plan, self.user, data,
            )
        )
        self.assertEqual(self.row(task)["content"], "test")

    def test_L14_other_users_plan_is_hidden(self):
        other = self.sql(
            "INSERT INTO users (username, password_hash) VALUES (:name, 'test')",
            name="lifecycle_other_" + uuid4().hex,
        ).lastrowid
        foreign = self.sql(
            "INSERT INTO study_plans (user_id,name,start_date,end_date,status) "
            "VALUES (:u,'foreign',:s,:e,'ACTIVE')",
            u=other,
            s=self.today,
            e=self.today + timedelta(days=5),
        ).lastrowid
        self.db.commit()
        self.reject(
            lambda: plan_lifecycle_service.end_plan_early(
                self.db, foreign, self.user,
            ),
            404,
        )
        self.assertEqual(self.plan_row(foreign)["status"], "ACTIVE")

    def test_L15_failure_rolls_back_task_updates(self):
        step = self.step()
        started = self.task(step, "BOOLEAN", 0, status="IN_PROGRESS")
        pending = self.task(step, "BOOLEAN", 1)
        with patch(
            "app.services.plans.plan_lifecycle_service.plan_lifecycle_repository"
            ".mark_plan_ended",
            side_effect=RuntimeError("injected"),
        ):
            with self.assertRaises(RuntimeError):
                plan_lifecycle_service.end_plan_early(
                    self.db, self.plan, self.user,
                )
        self.assertEqual(self.plan_row()["status"], "ACTIVE")
        self.assertEqual(self.row(started)["status"], "IN_PROGRESS")
        self.assertIsNone(self.row(started)["deleted_at"])
        self.assertIsNone(self.row(pending)["deleted_at"])

    def test_L16_overdue_early_end_uses_normal_mode(self):
        plan = self.new_plan("ACTIVE", -10, -2)
        step = self.step("BOOLEAN", plan=plan)
        pending = self.task(step, "BOOLEAN", -5, plan=plan)
        started = self.task(step, "BOOLEAN", -4, status="IN_PROGRESS", plan=plan)
        self.db.commit()
        result = plan_lifecycle_service.end_plan_early(
            self.db, plan, self.user,
        )
        self.assertEqual(result["end_mode"], "NORMAL_EXPIRED")
        self.assertEqual(result["ended_task_count"], 0)
        self.assertEqual(result["deleted_task_count"], 0)
        self.assertEqual(self.plan_row(plan)["status"], "ENDED")
        self.assertIsNone(self.row(pending)["deleted_at"])
        self.assertEqual(self.row(pending)["status"], "PENDING")
        self.assertEqual(self.row(started)["status"], "IN_PROGRESS")

    def test_route_contract_unified_response(self):
        import json

        response = plan_lifecycle_route.end_plan_early(
            plan_id=self.plan,
            user={"id": self.user},
            db=self.db,
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["message"], "计划已结束")
        self.assertEqual(body["data"]["status"], "ENDED")
        self.assertEqual(body["data"]["end_mode"], "EARLY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
