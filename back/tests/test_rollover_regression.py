"""MySQL regression tests. Fixtures live inside an outer transaction and roll back."""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.database import engine
from app.services import rollover_service, task_service
from app.repositories import rollover_repository, task_repository


class RolloverRegression(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.outer = self.conn.begin()
        self.db = Session(bind=self.conn, join_transaction_mode="create_savepoint")
        self.today = business_today()
        self.clock = patch("app.services.rollover_service.business_today", return_value=self.today)
        self.clock.start()
        self.task_clock = patch("app.services.task_service.business_today", return_value=self.today)
        self.task_clock.start()
        self.user = self.sql("INSERT INTO users (username, password_hash) VALUES (:name, 'test')",
                             name="rollover_test_" + uuid4().hex).lastrowid
        self.plan = self.sql(
            "INSERT INTO study_plans (user_id,name,start_date,end_date,status) VALUES (:u,'test',:s,:e,'ACTIVE')",
            u=self.user, s=self.today-timedelta(days=5), e=self.today+timedelta(days=10)
        ).lastrowid
        self.db.commit()

    def tearDown(self):
        self.clock.stop()
        self.task_clock.stop()
        self.db.close()
        self.outer.rollback()
        self.conn.close()

    def sql(self, query, **params):
        return self.db.execute(text(query), params)

    def step(self, task_type):
        result = self.sql("INSERT INTO plan_steps (plan_id,name,node_type,task_type) VALUES (:p,'test','LEAF',:t)",
                          p=self.plan, t=task_type).lastrowid
        self.db.commit()
        return result

    def task(self, step, task_type, day, target=None, actual=0, status="PENDING"):
        result = self.sql(
            "INSERT INTO daily_tasks (plan_id,step_id,task_date,task_type,content,target_quantity,actual_quantity,status) "
            "VALUES (:p,:s,:d,:t,'test',:q,:a,:st)",
            p=self.plan, s=step, d=day, t=task_type, q=target, a=actual, st=status
        ).lastrowid
        self.db.commit()
        return result

    def row(self, task_id):
        return dict(self.sql("SELECT * FROM daily_tasks WHERE id=:id", id=task_id).mappings().one())

    def rollover(self, task_id, day, user=None):
        return rollover_service.rollover_task(self.db, task_id, self.user if user is None else user, day)

    def reject(self, callback, code=409):
        with self.assertRaises(HTTPException) as caught:
            callback()
        self.assertEqual(caught.exception.status_code, code)

    def test_numeric_chain_and_locks_R01_R02_R03_R04_R13(self):
        step = self.step("NUMERIC")
        a = self.task(step, "NUMERIC", self.today, 100, 60, "IN_PROGRESS")
        b = self.rollover(a, self.today + timedelta(days=1))["target_task_id"]
        source = self.row(a)
        self.assertEqual((source["target_quantity"], source["actual_quantity"], source["rollover_out_quantity"], source["status"]), (100, 60, 40, "COMPLETED"))
        self.assertIsNotNone(source["completed_at"])
        self.assertEqual(self.row(b)["target_quantity"], 40)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM study_records WHERE task_id=:id", id=a).scalar(), 0)
        self.reject(lambda: task_service.update_numeric_task(self.db, a, self.user, 100))
        with self.assertRaises(RuntimeError):
            task_repository.update_numeric_progress(self.db, a, 100, "COMPLETED")
        self.db.rollback()
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=2)))
        with patch("app.services.rollover_service.business_today", return_value=self.today + timedelta(days=1)):
            c = self.rollover(b, self.today + timedelta(days=2))["target_task_id"]
        task_service.delete_task(self.db, b, self.user)
        self.assertIsNone(self.row(a)["deleted_at"])
        self.assertIsNotNone(self.row(b)["deleted_at"])
        self.assertIsNone(self.row(c)["deleted_at"])
        self.assertEqual(self.row(a)["rollover_out_quantity"], 40)
        self.assertEqual(self.row(c)["target_quantity"], 40)
        with patch("app.services.task_service.business_today", return_value=self.today + timedelta(days=1)):
            self.assertNotIn(b, [task["id"] for task in task_service.list_today_tasks(self.db, self.user)])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_rollovers WHERE source_task_id IN (:a,:b)", a=a, b=b).scalar(), 2)

    def test_numeric_zero_merge_history_and_completed_R05_R06_R07_R08_R19(self):
        s0 = self.step("NUMERIC")
        zero = self.task(s0, "NUMERIC", self.today, 0)
        self.reject(lambda: self.rollover(zero, self.today + timedelta(days=1)))
        s = self.step("NUMERIC")
        a = self.task(s, "NUMERIC", self.today - timedelta(days=1), 100, 60, "IN_PROGRESS")
        b = self.task(s, "NUMERIC", self.today, 10)
        target = self.task(s, "NUMERIC", self.today + timedelta(days=1), 50)
        self.assertTrue(self.rollover(a, self.today + timedelta(days=1))["merged"])
        self.assertTrue(self.rollover(b, self.today + timedelta(days=1))["merged"])
        self.assertEqual(self.row(target)["target_quantity"], 100)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_rollovers WHERE target_task_id=:id", id=target).scalar(), 2)
        s2 = self.step("NUMERIC")
        src = self.task(s2, "NUMERIC", self.today, 8)
        dst = self.task(s2, "NUMERIC", self.today + timedelta(days=1), 50)
        with patch("app.services.task_service.business_today", return_value=self.today + timedelta(days=1)):
            task_service.update_numeric_task(self.db, dst, self.user, 10)
            task_service.update_numeric_task(self.db, dst, self.user, 0)
        self.reject(lambda: self.rollover(src, self.today + timedelta(days=1)))
        self.assertEqual(rollover_repository.add_quantity_to_target(self.db, dst, 8), 0)
        self.assertEqual(self.row(dst)["target_quantity"], 50)
        s3 = self.step("NUMERIC")
        src2 = self.task(s3, "NUMERIC", self.today, 8)
        self.task(s3, "NUMERIC", self.today + timedelta(days=1), 10, 10, "COMPLETED")
        self.reject(lambda: self.rollover(src2, self.today + timedelta(days=1)))

    def test_boolean_history_R09_R10_R11_R12_R21(self):
        s = self.step("BOOLEAN")
        a = self.task(s, "BOOLEAN", self.today)
        b = self.rollover(a, self.today + timedelta(days=1))["target_task_id"]
        self.assertEqual(self.row(a)["status"], "PENDING")
        self.assertEqual(self.row(b)["status"], "PENDING")
        self.assertIsNone(self.sql("SELECT quantity FROM task_rollovers WHERE source_task_id=:id", id=a).scalar_one())
        self.assertTrue(task_service.get_task(self.db, a, self.user)["is_rolled_over"])
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=2)))
        self.reject(lambda: task_service.complete_boolean_task(self.db, a, self.user))
        with self.assertRaises(RuntimeError):
            task_repository.mark_boolean_completed(self.db, a)
        self.db.rollback()
        with patch("app.services.rollover_service.business_today", return_value=self.today + timedelta(days=1)):
            c = self.rollover(b, self.today + timedelta(days=2))["target_task_id"]
        task_service.delete_task(self.db, b, self.user)
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=3)))
        self.assertIsNone(self.row(c)["deleted_at"])

    def test_rollback_ownership_and_dates_R14_R15_R16_R17_R18(self):
        s = self.step("NUMERIC")
        a = self.task(s, "NUMERIC", self.today, 20)
        with patch("app.services.rollover_service.rollover_repository.insert_rollover_relation", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.rollover(a, self.today + timedelta(days=1))
        self.assertEqual(self.row(a)["rollover_out_quantity"], 0)
        self.assertEqual(self.row(a)["status"], "PENDING")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM daily_tasks WHERE step_id=:s", s=s).scalar(), 1)
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=1), user=self.user + 999999), 404)
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=11)))
        future = self.task(s, "NUMERIC", self.today + timedelta(days=2), 10)
        self.reject(lambda: self.rollover(future, self.today + timedelta(days=3)))
        self.sql("UPDATE study_plans SET status='ENDED' WHERE id=:id", id=self.plan)
        self.db.commit()
        self.reject(lambda: self.rollover(a, self.today + timedelta(days=1)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
