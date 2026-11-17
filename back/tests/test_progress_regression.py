"""Stage 10 progress regression tests. All fixtures roll back after each test."""
import unittest
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import progress as progress_route
from app.core.clock import business_today
from app.database import engine
from app.services.progress import progress_service


class ProgressRegression(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.outer = self.conn.begin()
        self.db = Session(bind=self.conn, join_transaction_mode="create_savepoint")
        self.today = business_today()
        self.user = self.sql(
            "INSERT INTO users (username, password_hash) VALUES (:name, 'test')",
            name="progress_test_" + uuid4().hex,
        ).lastrowid
        self.plan = self.new_plan("ACTIVE")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.outer.rollback()
        self.conn.close()

    def sql(self, query, **params):
        return self.db.execute(text(query), params)

    def new_plan(self, status):
        return self.sql(
            "INSERT INTO study_plans (user_id,name,start_date,end_date,status) "
            "VALUES (:u,'test',:s,:e,:st)",
            u=self.user,
            s=self.today - timedelta(days=5),
            e=self.today + timedelta(days=10),
            st=status,
        ).lastrowid

    def step(self, task_type=None, node_type="LEAF", parent=None, name="test"):
        result = self.sql(
            "INSERT INTO plan_steps (plan_id,parent_id,name,node_type,task_type) "
            "VALUES (:p,:parent,:name,:node_type,:task_type)",
            p=self.plan,
            parent=parent,
            name=name,
            node_type=node_type,
            task_type=task_type,
        ).lastrowid
        self.db.commit()
        return result

    def task(self, step, task_type, day, target=None, actual=0, status="PENDING"):
        result = self.sql(
            "INSERT INTO daily_tasks "
            "(plan_id,step_id,task_date,task_type,content,target_quantity,actual_quantity,status) "
            "VALUES (:p,:s,:d,:t,'test',:q,:a,:st)",
            p=self.plan,
            s=step,
            d=self.today + timedelta(days=day),
            t=task_type,
            q=target,
            a=actual,
            st=status,
        ).lastrowid
        self.db.commit()
        return result

    def link(self, source, target, quantity=None):
        self.sql(
            "INSERT INTO task_rollovers (source_task_id,target_task_id,quantity) "
            "VALUES (:s,:t,:q)",
            s=source,
            t=target,
            q=quantity,
        )
        self.db.commit()

    def progress(self, plan=None):
        return progress_service.get_plan_progress(
            self.db,
            self.plan if plan is None else plan,
            self.user,
        )

    def leaf(self, result, step_id):
        return next(item for item in result["leaves"] if item["step_id"] == step_id)

    def test_P01_boolean_completion_rate(self):
        step = self.step("BOOLEAN")
        for day in range(4):
            self.task(
                step,
                "BOOLEAN",
                day,
                status="COMPLETED" if day < 3 else "PENDING",
            )
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["valid_task_count"], 4)
        self.assertEqual(leaf["completed_task_count"], 3)
        self.assertEqual(leaf["progress_percent"], 75.0)
        self.assertEqual(result["progress_percent"], 75.0)

    def test_P02_boolean_rollover_source_excluded(self):
        step = self.step("BOOLEAN")
        source = self.task(step, "BOOLEAN", 0)
        target = self.task(step, "BOOLEAN", 1, status="COMPLETED")
        self.link(source, target)
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["valid_task_count"], 1)
        self.assertEqual(leaf["progress_percent"], 100.0)
        self.assertEqual(result["progress_percent"], 100.0)

    def test_P03_boolean_rollover_target_deleted(self):
        step = self.step("BOOLEAN")
        source = self.task(step, "BOOLEAN", 0)
        target = self.task(step, "BOOLEAN", 1)
        self.link(source, target)
        self.sql(
            "UPDATE daily_tasks SET deleted_at=NOW() WHERE id=:id",
            id=target,
        )
        self.db.commit()
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertIsNone(leaf["progress_percent"])
        self.assertEqual(leaf["reason"], "NO_VALID_TASKS")
        self.assertIsNone(result["progress_percent"])
        self.assertEqual(result["reason"], "NO_COMPUTABLE_LEAF")

    def test_P04_numeric_completion_rate(self):
        step = self.step("NUMERIC")
        self.task(step, "NUMERIC", 0, 60, 40, "IN_PROGRESS")
        self.task(step, "NUMERIC", 1, 40, 20, "IN_PROGRESS")
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["target_total"], 100)
        self.assertEqual(leaf["actual_total"], 60)
        self.assertEqual(leaf["progress_percent"], 60.0)

    def test_P05_numeric_rollover_rate(self):
        step = self.step("NUMERIC")
        source = self.task(step, "NUMERIC", 0, 100, 60, "COMPLETED")
        target = self.task(step, "NUMERIC", 1, 40, 20, "IN_PROGRESS")
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=40 WHERE id=:id",
            id=source,
        )
        self.link(source, target, 40)
        self.db.commit()
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["target_total"], 100)
        self.assertEqual(leaf["actual_total"], 80)
        self.assertEqual(leaf["progress_percent"], 80.0)

    def test_P06_numeric_chained_rollover(self):
        step = self.step("NUMERIC")
        a = self.task(step, "NUMERIC", 0, 100, 60, "COMPLETED")
        b = self.task(step, "NUMERIC", 1, 40, 15, "COMPLETED")
        c = self.task(step, "NUMERIC", 2, 25, 0, "PENDING")
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=40 WHERE id=:id",
            id=a,
        )
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=25 WHERE id=:id",
            id=b,
        )
        self.link(a, b, 40)
        self.link(b, c, 25)
        self.db.commit()
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["target_total"], 100)
        self.assertEqual(leaf["actual_total"], 75)
        self.assertEqual(leaf["progress_percent"], 75.0)

    def test_P07_delete_middle_task_of_rollover_chain(self):
        step = self.step("NUMERIC")
        a = self.task(step, "NUMERIC", 0, 100, 60, "COMPLETED")
        b = self.task(step, "NUMERIC", 1, 40, 15, "COMPLETED")
        c = self.task(step, "NUMERIC", 2, 25, 0, "PENDING")
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=40 WHERE id=:id",
            id=a,
        )
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=25 WHERE id=:id",
            id=b,
        )
        self.link(a, b, 40)
        self.link(b, c, 25)
        self.sql("UPDATE daily_tasks SET deleted_at=NOW() WHERE id=:id", id=b)
        self.db.commit()
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["target_total"], 85)
        self.assertEqual(leaf["actual_total"], 60)
        self.assertEqual(leaf["progress_percent"], 70.59)
        history = self.sql(
            "SELECT COUNT(*) FROM task_rollovers WHERE source_task_id IN (:a,:b) OR target_task_id IN (:a,:b)",
            a=a,
            b=b,
        ).scalar()
        self.assertEqual(history, 2)

    def test_P08_numeric_over_completion(self):
        step = self.step("NUMERIC")
        self.task(step, "NUMERIC", 0, 100, 120, "COMPLETED")
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertEqual(leaf["progress_percent"], 100.0)
        self.assertEqual(leaf["actual_total"], 120)
        self.assertEqual(leaf["target_total"], 100)

    def test_P09_global_leaf_equal_weight(self):
        for actual in (80, 50, 100):
            step = self.step("NUMERIC")
            self.task(step, "NUMERIC", 0, 100, actual, "COMPLETED")
        result = self.progress()
        self.assertEqual(len(result["leaves"]), 3)
        self.assertEqual(result["progress_percent"], 76.67)

    def test_P10_leaves_at_different_depths(self):
        group = self.step(None, "GROUP")
        subgroup = self.step(None, "GROUP", parent=group)
        deep = self.step("BOOLEAN", parent=subgroup)
        self.task(deep, "BOOLEAN", 0, status="COMPLETED")
        self.task(deep, "BOOLEAN", 1, status="PENDING")
        shallow = self.step("BOOLEAN")
        self.task(shallow, "BOOLEAN", 0, status="COMPLETED")
        result = self.progress()
        self.assertEqual(len(result["leaves"]), 2)
        self.assertEqual(self.leaf(result, deep)["progress_percent"], 50.0)
        self.assertEqual(self.leaf(result, shallow)["progress_percent"], 100.0)
        self.assertEqual(result["progress_percent"], 75.0)

    def test_P11_deleted_leaf_reweights_remaining(self):
        first = self.step("NUMERIC")
        self.task(first, "NUMERIC", 0, 100, 80, "COMPLETED")
        second = self.step("NUMERIC")
        task = self.task(second, "NUMERIC", 1, 100, 50, "COMPLETED")
        self.sql("UPDATE plan_steps SET deleted_at=NOW() WHERE id=:id", id=second)
        self.sql("UPDATE daily_tasks SET deleted_at=NOW() WHERE id=:id", id=task)
        self.db.commit()
        result = self.progress()
        self.assertEqual(result["leaf_count"], 1)
        self.assertEqual(result["computable_leaf_count"], 1)
        self.assertEqual(result["progress_percent"], 80.0)

    def test_P12_no_computable_tasks(self):
        deleted_leaf = self.step("BOOLEAN")
        task = self.task(deleted_leaf, "BOOLEAN", 0, status="COMPLETED")
        self.sql("UPDATE daily_tasks SET deleted_at=NOW() WHERE id=:id", id=task)
        rolled_leaf = self.step("BOOLEAN")
        source = self.task(rolled_leaf, "BOOLEAN", 1)
        target = self.task(rolled_leaf, "BOOLEAN", 2)
        self.link(source, target)
        self.sql("UPDATE daily_tasks SET deleted_at=NOW() WHERE id=:id", id=target)
        self.db.commit()
        result = self.progress()
        self.assertEqual(result["leaf_count"], 2)
        self.assertEqual(result["computable_leaf_count"], 0)
        self.assertIsNone(result["progress_percent"])
        self.assertEqual(result["reason"], "NO_COMPUTABLE_LEAF")
        self.assertIsNone(self.leaf(result, deleted_leaf)["progress_percent"])
        self.assertIsNone(self.leaf(result, rolled_leaf)["progress_percent"])

    def test_P13_numeric_zero_target(self):
        step = self.step("NUMERIC")
        self.task(step, "NUMERIC", 0, 0, 0)
        result = self.progress()
        leaf = self.leaf(result, step)
        self.assertIsNone(leaf["progress_percent"])
        self.assertEqual(leaf["reason"], "ZERO_TARGET")
        self.assertIsNone(result["progress_percent"])

    def test_P14_draft_and_ended_plan(self):
        draft = self.new_plan("DRAFT")
        self.sql(
            "INSERT INTO plan_steps (plan_id,name,node_type,task_type) "
            "VALUES (:p,'test','LEAF','BOOLEAN')",
            p=draft,
        )
        self.db.commit()
        result = self.progress(draft)
        self.assertIsNone(result["progress_percent"])
        self.assertEqual(result["reason"], "PLAN_NOT_ACTIVE")
        self.assertEqual(result["leaves"], [])
        self.sql("UPDATE study_plans SET status='ENDED' WHERE id=:id", id=draft)
        self.db.commit()
        result = self.progress(draft)
        self.assertIsNone(result["progress_percent"])
        self.assertEqual(result["reason"], "PLAN_NOT_ACTIVE")

    def test_P15_other_users_plan_is_hidden(self):
        other = self.sql(
            "INSERT INTO users (username, password_hash) VALUES (:name, 'test')",
            name="progress_other_" + uuid4().hex,
        ).lastrowid
        foreign_plan = self.sql(
            "INSERT INTO study_plans (user_id,name,start_date,end_date,status) "
            "VALUES (:u,'foreign',:s,:e,'ACTIVE')",
            u=other,
            s=self.today,
            e=self.today + timedelta(days=5),
        ).lastrowid
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            progress_service.get_plan_progress(self.db, foreign_plan, self.user)
        self.assertEqual(caught.exception.status_code, 404)

    def test_P16_data_anomaly_is_reported(self):
        first = self.step("NUMERIC")
        self.task(first, "NUMERIC", 0, 50, 20, "COMPLETED")
        self.sql(
            "UPDATE daily_tasks SET rollover_out_quantity=60 "
            "WHERE step_id=:s",
            s=first,
        )
        second = self.step("NUMERIC")
        self.task(second, "NUMERIC", 1, None, 0)
        self.db.commit()
        result = self.progress()
        self.assertEqual(len(result["data_anomalies"]), 2)
        self.assertIsNone(result["progress_percent"])
        self.assertEqual(
            self.leaf(result, first)["reason"],
            "DATA_ANOMALY",
        )
        self.assertEqual(
            self.leaf(result, second)["reason"],
            "DATA_ANOMALY",
        )
        self.assertIsNone(self.leaf(result, first)["progress_percent"])

    def test_route_registered_and_unified_response(self):
        step = self.step("BOOLEAN")
        self.task(step, "BOOLEAN", 0, status="COMPLETED")
        response = progress_route.get_plan_progress(
            plan_id=self.plan,
            user={"id": self.user},
            db=self.db,
        )
        self.assertEqual(response.status_code, 200)
        body = __import__("json").loads(response.body)
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["message"], "计划进度查询成功")
        self.assertEqual(body["data"]["plan_id"], self.plan)
        self.assertEqual(body["data"]["progress_percent"], 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
