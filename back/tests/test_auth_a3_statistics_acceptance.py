"""V3.0 A3 统计模块验收测试。

约束：
- 仅在隔离测试库 ssp_v3_admin_test 执行。
- 不修改业务源码；发现业务缺陷仅由测试断言暴露。
- 覆盖两个接口：GET /admin/dashboard、GET /admin/ai/statistics。
- 共享测试库按前缀精确清理，不执行全库清空。

运行：
    $env:DB_NAME='ssp_v3_admin_test'
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_auth_a3_statistics_acceptance.py -q
"""

import unittest
import uuid
from datetime import date, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.config import settings
from app.core import security
from app.core.clock import business_today, utc_db_now
from app.database import engine
from app.main import app as production_app

ALLOWED_TEST_DBS = {"ssp_v3_admin_test"}


def _guard_database() -> str:
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if db_name not in ALLOWED_TEST_DBS:
        raise RuntimeError(
            f"测试仅允许在隔离测试库执行，当前数据库: {db_name}"
        )
    return db_name


CURRENT_DB = _guard_database()

ORIGIN = settings.AUTH_ALLOWED_ORIGINS[0]
CSRF_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}
PASSWORD = "AdminPass123"

DASHBOARD = "/admin/dashboard"
AI_STATS = "/admin/ai/statistics"

AI_STATUSES = {
    "SUCCESS",
    "ERROR",
    "TIMEOUT",
    "CANCELLED",
    "BLOCKED",
    "STALE",
    "RUNNING",
    "RUNNING_EXPIRED",
    "OTHER",
}

AI_OPERATIONS = {
    "GENERATE",
    "ORGANIZE",
    "SUMMARY",
    "ASK",
    "PRACTICE_GENERATE",
    "PRACTICE_GRADE",
    "OTHER",
}


def _new_client() -> TestClient:
    return TestClient(
        production_app,
        base_url="https://ssp.test",
        client=("127.0.0.1", 52410),
        raise_server_exceptions=False,
    )


def _in(sql: str, key: str = "ids"):
    return text(sql).bindparams(bindparam(key, expanding=True))


class BaseA3Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.PREFIX = f"a3{uuid.uuid4().hex[:8]}"
        cls.client = _new_client()
        cls._pwd_limit = settings.PASSWORD_IP_MAX_ATTEMPTS
        cls._mail_limit = settings.EMAIL_CODE_IP_MAX_ATTEMPTS
        settings.PASSWORD_IP_MAX_ATTEMPTS = 1000000
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = 1000000

    @classmethod
    def tearDownClass(cls):
        settings.PASSWORD_IP_MAX_ATTEMPTS = cls._pwd_limit
        settings.EMAIL_CODE_IP_MAX_ATTEMPTS = cls._mail_limit
        cls._cleanup()

    @classmethod
    def _cleanup(cls):
        with engine.begin() as conn:
            uids = [
                row[0]
                for row in conn.execute(
                    text("SELECT id FROM users WHERE username LIKE :p"),
                    {"p": cls.PREFIX + "%"},
                )
            ]
            if not uids:
                return

            params = {"ids": uids}
            plan_ids = [
                row[0]
                for row in conn.execute(
                    _in(
                        "SELECT id FROM study_plans WHERE user_id IN :ids"
                    ),
                    params,
                )
            ]

            conn.execute(
                _in(
                    "DELETE FROM admin_audit_logs "
                    "WHERE admin_id IN :ids OR target_id IN :ids"
                ),
                params,
            )
            for table in (
                "refresh_tokens",
                "login_sessions",
                "auth_events",
                "email_verifications",
            ):
                conn.execute(
                    _in(f"DELETE FROM {table} WHERE user_id IN :ids"),
                    params,
                )

            conn.execute(
                _in("DELETE FROM study_records WHERE user_id IN :ids"),
                params,
            )

            if plan_ids:
                plan_params = {"pids": plan_ids}
                conn.execute(
                    _in(
                        "DELETE FROM daily_tasks WHERE plan_id IN :pids",
                        "pids",
                    ),
                    plan_params,
                )
                conn.execute(
                    _in(
                        "DELETE FROM plan_steps WHERE plan_id IN :pids",
                        "pids",
                    ),
                    plan_params,
                )

            conn.execute(
                _in("DELETE FROM knowledge_notes WHERE user_id IN :ids"),
                params,
            )
            conn.execute(
                _in("DELETE FROM ai_requests WHERE user_id IN :ids"),
                params,
            )
            conn.execute(
                _in("DELETE FROM study_plans WHERE user_id IN :ids"),
                params,
            )
            conn.execute(
                _in("DELETE FROM users WHERE id IN :ids"),
                params,
            )

    # ---------- 构造 ----------

    def make_user(
        self,
        suffix: str,
        *,
        role: str = "USER",
        created_at: datetime | None = None,
    ):
        username = f"{self.PREFIX}{suffix}{uuid.uuid4().hex[:4]}"
        email = f"{username}@example.com"

        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users ("
                    "username, password_hash, password_updated_at, "
                    "email, email_verified_at, nickname, role, created_at"
                    ") VALUES ("
                    ":username, :password_hash, :now, :email, :now, "
                    ":nickname, :role, COALESCE(:created_at, CURRENT_TIMESTAMP)"
                    ")"
                ),
                {
                    "username": username,
                    "password_hash": security.hash_password(PASSWORD),
                    "now": utc_db_now(),
                    "email": email,
                    "nickname": username,
                    "role": role,
                    "created_at": created_at,
                },
            )
            user_id = int(result.lastrowid)

        return user_id, username, email

    def make_admin(self, suffix: str = "op"):
        user_id, username, _ = self.make_user(suffix, role="ADMIN")
        token, _ = self.login(username)
        return user_id, username, token

    def login(self, username: str, client: TestClient | None = None):
        client = client or self.client
        response = client.post(
            "/auth/login",
            data={"username": username, "password": PASSWORD},
            headers=CSRF_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return (
            response.json()["data"]["access_token"],
            response.json()["data"]["user"],
        )

    def auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ---------- 数据 ----------

    def create_plan(
        self,
        user_id: int,
        *,
        status: str = "ACTIVE",
        deleted: bool = False,
    ) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO study_plans "
                    "(user_id, name, start_date, end_date, status, deleted_at) "
                    "VALUES (:u, :n, CURDATE(), DATE_ADD(CURDATE(), "
                    "INTERVAL 7 DAY), :s, :d)"
                ),
                {
                    "u": user_id,
                    "n": f"A3 计划 {uuid.uuid4().hex[:4]}",
                    "s": status,
                    "d": utc_db_now() if deleted else None,
                },
            )
            return int(result.lastrowid)

    def create_step(self, plan_id: int) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO plan_steps "
                    "(plan_id, name, node_type, task_type) "
                    "VALUES (:p, :n, 'LEAF', 'BOOLEAN')"
                ),
                {"p": plan_id, "n": f"A3 步骤 {uuid.uuid4().hex[:4]}"},
            )
            return int(result.lastrowid)

    def create_task(
        self,
        plan_id: int,
        step_id: int,
        *,
        task_date: date,
        deleted: bool = False,
    ) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO daily_tasks "
                    "(plan_id, step_id, task_date, task_type, content, "
                    "status, deleted_at) "
                    "VALUES (:p, :s, :d, 'BOOLEAN', :c, 'COMPLETED', :del)"
                ),
                {
                    "p": plan_id,
                    "s": step_id,
                    "d": task_date,
                    "c": f"A3 任务 {uuid.uuid4().hex[:4]}",
                    "del": utc_db_now() if deleted else None,
                },
            )
            return int(result.lastrowid)

    def create_record(
        self,
        task_id: int,
        user_id: int,
        *,
        recorded_at: datetime,
        task_date: date,
    ) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO study_records "
                    "(task_id, user_id, event_type, recorded_value, "
                    "task_date, recorded_at) "
                    "VALUES (:t, :u, 'BOOLEAN_COMPLETE', 1, :d, :r)"
                ),
                {
                    "t": task_id,
                    "u": user_id,
                    "d": task_date,
                    "r": recorded_at,
                },
            )
            return int(result.lastrowid)

    def create_note(self, user_id: int, *, deleted: bool = False) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO knowledge_notes "
                    "(user_id, title, content_md, deleted_at) "
                    "VALUES (:u, :t, 'A3', :d)"
                ),
                {
                    "u": user_id,
                    "t": f"A3 笔记 {uuid.uuid4().hex[:4]}",
                    "d": utc_db_now() if deleted else None,
                },
            )
            return int(result.lastrowid)

    def create_ai_request(
        self,
        user_id: int,
        *,
        operation: str,
        status: str,
        request_date: date,
        leased_until: datetime,
    ) -> str:
        request_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ai_requests "
                    "(request_id, user_id, operation, request_date, "
                    "status, leased_until) "
                    "VALUES (:rid, :u, :op, :d, :s, :lease)"
                ),
                {
                    "rid": request_id,
                    "u": user_id,
                    "op": operation,
                    "d": request_date,
                    "s": status,
                    "lease": leased_until,
                },
            )
        return request_id

    # ---------- 接口 ----------

    def dashboard(self, token: str) -> dict:
        response = self.client.get(DASHBOARD, headers=self.auth(token))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def ai_statistics(self, token: str) -> dict:
        response = self.client.get(AI_STATS, headers=self.auth(token))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    # ---------- DB ----------

    def scalar(self, sql: str, **params):
        with engine.connect() as conn:
            return conn.execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params):
        with engine.connect() as conn:
            return conn.execute(text(sql), params).mappings().all()

    def execute(self, sql: str, **params) -> None:
        with engine.begin() as conn:
            conn.execute(text(sql), params)

    def trend_map(self, data: dict) -> dict:
        return {item["date"]: item for item in data["daily_trend"]}

    def today(self) -> date:
        return business_today()


# ============================================================
# T1 权限
# ============================================================


class TestStatisticsPermissions(BaseA3Test):

    def setUp(self):
        self.admin_id, _, self.admin_token = self.make_admin("op")
        self.user_id, self.user_name, _ = self.make_user("usr")
        self.user_token, _ = self.login(self.user_name)

    def test_t1_01_admin_can_access_both(self):
        for path in (DASHBOARD, AI_STATS):
            with self.subTest(path=path):
                response = self.client.get(
                    path, headers=self.auth(self.admin_token)
                )
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertIn("data", body)

    def test_t1_02_normal_user_forbidden(self):
        for path in (DASHBOARD, AI_STATS):
            with self.subTest(path=path):
                response = self.client.get(
                    path, headers=self.auth(self.user_token)
                )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "ADMIN_REQUIRED",
                )

    def test_t1_03_anonymous_unauthorized(self):
        for path in (DASHBOARD, AI_STATS):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "INVALID_TOKEN",
                )


# ============================================================
# T2 空库 / 趋势连续性
# ============================================================


class TestStatisticsEmptyAndTrend(BaseA3Test):

    def setUp(self):
        self.admin_id, _, self.admin_token = self.make_admin("op")

    def test_t2_01_empty_database_returns_zero(self):
        """空库或无记录时，各统计项为 0。（运行时库为空，直接验证 0）"""
        total_users = int(self.scalar("SELECT COUNT(*) FROM users"))
        total_plans = int(
            self.scalar(
                "SELECT COUNT(*) FROM study_plans "
                "WHERE deleted_at IS NULL"
            )
        )
        total_notes = int(
            self.scalar(
                "SELECT COUNT(*) FROM knowledge_notes "
                "WHERE deleted_at IS NULL"
            )
        )

        db_checkins = int(
            self.scalar(
                "SELECT COUNT(*) FROM study_records sr "
                "JOIN daily_tasks dt ON dt.id = sr.task_id "
                "JOIN study_plans sp ON sp.id = dt.plan_id "
                "AND sp.user_id = sr.user_id "
                "WHERE sp.deleted_at IS NULL"
            )
        )
        db_ai_today = int(
            self.scalar(
                "SELECT COUNT(*) FROM ai_requests "
                "WHERE request_date = :d",
                d=self.today(),
            )
        )

        data = self.dashboard(self.admin_token)
        overview = data["overview"]

        self.assertEqual(overview["total_users"], total_users)
        self.assertEqual(overview["total_plans"], total_plans)
        self.assertEqual(overview["total_notes"], total_notes)
        self.assertEqual(overview["total_checkins"], db_checkins)
        self.assertEqual(overview["today_ai_requests"], db_ai_today)

        if total_plans == 0:
            self.assertEqual(overview["active_plans"], 0)
        if total_notes == 0:
            self.assertEqual(overview["total_notes"], 0)
        if db_checkins == 0:
            self.assertEqual(overview["total_checkins"], 0)
            self.assertEqual(overview["today_checkins"], 0)
        if db_ai_today == 0:
            self.assertEqual(overview["today_ai_requests"], 0)

    def test_t2_02_dashboard_trend_is_continuous_7_days(self):
        today = self.today()
        expected_dates = [
            (today - timedelta(days=offset)).isoformat()
            for offset in range(6, -1, -1)
        ]

        data = self.dashboard(self.admin_token)
        trend = data["daily_trend"]

        self.assertEqual(len(trend), 7)
        self.assertEqual(
            [item["date"] for item in trend],
            expected_dates,
        )
        self.assertEqual(data["as_of_date"], today.isoformat())
        self.assertEqual(trend[-1]["date"], today.isoformat())

        start_at = datetime.combine(
            today - timedelta(days=6), time.min
        )
        end_exclusive = datetime.combine(
            today + timedelta(days=1), time.min
        )

        new_users = {
            str(row["date"]): int(row["new_user_count"])
            for row in self.rows(
                "SELECT DATE(created_at) AS date, COUNT(*) AS new_user_count "
                "FROM users WHERE created_at >= :s AND created_at < :e "
                "GROUP BY DATE(created_at)",
                s=start_at,
                e=end_exclusive,
            )
        }

        learning = {
            str(row["date"]): row
            for row in self.rows(
                "SELECT DATE(sr.recorded_at) AS date, "
                "COUNT(*) AS checkin_count, "
                "COUNT(DISTINCT sr.user_id) AS active_user_count "
                "FROM study_records sr "
                "JOIN daily_tasks dt ON dt.id = sr.task_id "
                "JOIN study_plans sp ON sp.id = dt.plan_id "
                "AND sp.user_id = sr.user_id "
                "WHERE sp.deleted_at IS NULL "
                "AND sr.recorded_at >= :s AND sr.recorded_at < :e "
                "GROUP BY DATE(sr.recorded_at)",
                s=start_at,
                e=end_exclusive,
            )
        }

        for item in trend:
            key = item["date"]
            expected_new = new_users.get(key, 0)
            expected_learning = learning.get(key, {})

            self.assertEqual(item["new_user_count"], expected_new)
            self.assertEqual(
                item["checkin_count"],
                int(expected_learning.get("checkin_count", 0)),
            )
            self.assertEqual(
                item["active_user_count"],
                int(expected_learning.get("active_user_count", 0)),
            )

    def test_t2_03_ai_trend_and_distribution_shape(self):
        today = self.today()
        data = self.ai_statistics(self.admin_token)

        trend = data["daily_trend"]
        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[-1]["date"], today.isoformat())

        self.assertEqual(
            set(data["status_distribution"]), AI_STATUSES
        )
        self.assertEqual(
            set(data["operation_distribution"]), AI_OPERATIONS
        )

        expected_today = int(
            self.scalar(
                "SELECT COUNT(*) FROM ai_requests "
                "WHERE request_date = :d",
                d=today,
            )
        )
        self.assertEqual(data["overview"]["today_used"], expected_today)
        self.assertEqual(
            sum(data["status_distribution"].values()),
            expected_today,
        )

        expected_active = int(
            self.scalar(
                "SELECT COUNT(*) FROM ai_requests "
                "WHERE status = 'RUNNING' "
                "AND leased_until > UTC_TIMESTAMP(6)"
            )
        )
        self.assertEqual(
            data["overview"]["current_active"], expected_active
        )
        runtime_global_limit = min(
            int(
                self.scalar(
                    "SELECT global_daily_limit "
                    "FROM ai_runtime_config WHERE id = 1"
                )
            ),
            settings.AI_GLOBAL_DAILY_HARD_LIMIT,
        )
        self.assertEqual(
            data["overview"]["today_remaining"],
            max(
                runtime_global_limit
                - data["overview"]["today_used"],
                0,
            ),
        )


# ============================================================
# T3 Dashboard 口径
# ============================================================


class TestDashboardAccuracy(BaseA3Test):

    def setUp(self):
        self.admin_id, _, self.admin_token = self.make_admin("op")

    def test_t3_01_user_counts(self):
        active_id, _, _ = self.make_user("active")
        disabled_id, _, _ = self.make_user("disabled")
        self.execute(
            "UPDATE users SET is_active = 0 WHERE id = :i",
            i=disabled_id,
        )

        db_total = int(self.scalar("SELECT COUNT(*) FROM users"))
        db_enabled = int(
            self.scalar("SELECT COUNT(*) FROM users WHERE is_active = 1")
        )
        db_disabled = int(
            self.scalar("SELECT COUNT(*) FROM users WHERE is_active = 0")
        )

        overview = self.dashboard(self.admin_token)["overview"]

        self.assertEqual(overview["total_users"], db_total)
        self.assertEqual(overview["enabled_users"], db_enabled)
        self.assertEqual(overview["disabled_users"], db_disabled)
        self.assertGreaterEqual(db_enabled, 1)
        self.assertGreaterEqual(db_disabled, 1)

    def test_t3_02_plan_status_distribution(self):
        user_id, _, _ = self.make_user("plan")
        self.create_plan(user_id, status="DRAFT")
        self.create_plan(user_id, status="ACTIVE")
        self.create_plan(user_id, status="ENDED")
        self.create_plan(user_id, status="ACTIVE", deleted=True)

        db_rows = self.rows(
            "SELECT status, COUNT(*) AS c FROM study_plans "
            "WHERE deleted_at IS NULL GROUP BY status"
        )
        expected = {"DRAFT": 0, "ACTIVE": 0, "ENDED": 0}
        for row in db_rows:
            expected[row["status"]] = int(row["c"])

        data = self.dashboard(self.admin_token)
        self.assertEqual(
            data["plan_status_distribution"], expected
        )
        self.assertEqual(
            data["overview"]["total_plans"], sum(expected.values())
        )
        self.assertEqual(
            data["overview"]["active_plans"], expected["ACTIVE"]
        )

    def test_t3_03_note_count_excludes_deleted(self):
        user_id, _, _ = self.make_user("note")
        self.create_note(user_id)
        self.create_note(user_id)
        self.create_note(user_id, deleted=True)

        db_notes = int(
            self.scalar(
                "SELECT COUNT(*) FROM knowledge_notes "
                "WHERE deleted_at IS NULL"
            )
        )
        data = self.dashboard(self.admin_token)
        self.assertEqual(data["overview"]["total_notes"], db_notes)

    def test_t3_04_same_user_same_day_counts_once_as_active(self):
        user_id, _, _ = self.make_user("multi")
        plan_id = self.create_plan(user_id)
        step_id = self.create_step(plan_id)
        task_id = self.create_task(
            plan_id, step_id, task_date=self.today()
        )

        today = self.today()
        baseline = self.trend_map(
            self.dashboard(self.admin_token)
        )[today.isoformat()]

        for hour in (9, 10, 11):
            self.create_record(
                task_id,
                user_id,
                recorded_at=datetime.combine(
                    today, time(hour, 0, 0)
                ),
                task_date=today,
            )

        after = self.trend_map(
            self.dashboard(self.admin_token)
        )[today.isoformat()]

        self.assertEqual(
            after["checkin_count"] - baseline["checkin_count"], 3
        )
        self.assertEqual(
            after["active_user_count"]
            - baseline["active_user_count"],
            1,
        )

    def test_t3_05_soft_delete_semantics(self):
        user_id, _, _ = self.make_user("soft")
        today = self.today()

        # 正常计划 + 正常任务
        plan_ok = self.create_plan(user_id)
        step_ok = self.create_step(plan_ok)
        task_ok = self.create_task(
            plan_ok, step_ok, task_date=today
        )

        # 正常计划 + 已删除任务（历史打卡应保留）
        task_deleted = self.create_task(
            plan_ok, step_ok, task_date=today, deleted=True
        )

        # 已删除计划（打卡应排除）
        plan_deleted = self.create_plan(user_id, deleted=True)
        step_deleted = self.create_step(plan_deleted)
        task_in_deleted_plan = self.create_task(
            plan_deleted, step_deleted, task_date=today
        )

        baseline = self.trend_map(
            self.dashboard(self.admin_token)
        )[today.isoformat()]

        for task_id in (task_ok, task_deleted, task_in_deleted_plan):
            self.create_record(
                task_id,
                user_id,
                recorded_at=datetime.combine(
                    today, time(12, 0, 0)
                ),
                task_date=today,
            )

        after = self.trend_map(
            self.dashboard(self.admin_token)
        )[today.isoformat()]

        # 正常任务 + 已删除任务计入；已删除计划排除
        self.assertEqual(
            after["checkin_count"] - baseline["checkin_count"], 2
        )
        self.assertEqual(
            after["active_user_count"]
            - baseline["active_user_count"],
            1,
        )

    def test_t3_06_beijing_natural_day_boundary(self):
        user_id, _, _ = self.make_user("boundary")
        today = self.today()
        yesterday = today - timedelta(days=1)

        plan_id = self.create_plan(user_id)
        step_id = self.create_step(plan_id)
        task_id = self.create_task(
            plan_id, step_id, task_date=today
        )

        baseline = self.trend_map(
            self.dashboard(self.admin_token)
        )

        # 边界用户：今天 00:00 与昨天 23:59:59 创建
        self.make_user(
            "newtoday",
            created_at=datetime.combine(today, time.min),
        )
        self.make_user(
            "newyesterday",
            created_at=datetime.combine(
                yesterday, time(23, 59, 59)
            ),
        )

        for recorded_at in (
            datetime.combine(today, time.min),
            datetime.combine(today, time(23, 59, 59)),
            datetime.combine(yesterday, time(23, 59, 59)),
        ):
            self.create_record(
                task_id,
                user_id,
                recorded_at=recorded_at,
                task_date=today,
            )

        after = self.trend_map(
            self.dashboard(self.admin_token)
        )
        today_key = today.isoformat()
        yesterday_key = yesterday.isoformat()

        # 今天 00:00:00 与 23:59:59 都算今天；昨天 23:59:59 算昨天
        self.assertEqual(
            after[today_key]["checkin_count"]
            - baseline[today_key]["checkin_count"],
            2,
        )
        self.assertEqual(
            after[yesterday_key]["checkin_count"]
            - baseline[yesterday_key]["checkin_count"],
            1,
        )

        # 用户创建时间同样按北京时间自然日
        self.assertEqual(
            after[today_key]["new_user_count"]
            - baseline[today_key]["new_user_count"],
            1,
        )
        self.assertEqual(
            after[yesterday_key]["new_user_count"]
            - baseline[yesterday_key]["new_user_count"],
            1,
        )


# ============================================================
# T4 AI 统计
# ============================================================


class TestAiStatisticsAccuracy(BaseA3Test):

    def setUp(self):
        self.admin_id, _, self.admin_token = self.make_admin("op")
        self.user_id, _, _ = self.make_user("ai")

    def _baseline(self) -> dict:
        return self.ai_statistics(self.admin_token)

    def test_t4_01_all_admission_statuses_count_toward_quota(self):
        today = self.today()
        future = utc_db_now() + timedelta(hours=1)
        past = utc_db_now() - timedelta(minutes=5)

        baseline = self._baseline()

        created = [
            ("SUCCESS", future),
            ("ERROR", future),
            ("TIMEOUT", future),
            ("CANCELLED", future),
            ("BLOCKED", future),
            ("STALE", future),
            ("RUNNING", future),
            ("RUNNING", past),
            ("WEIRD", future),
        ]
        for status, lease in created:
            self.create_ai_request(
                self.user_id,
                operation="SUMMARY",
                status=status,
                request_date=today,
                leased_until=lease,
            )

        after = self._baseline()
        before_overview = baseline["overview"]
        after_overview = after["overview"]

        self.assertEqual(
            after_overview["today_used"]
            - before_overview["today_used"],
            9,
        )

        expected_delta = {
            "SUCCESS": 1,
            "ERROR": 1,
            "TIMEOUT": 1,
            "CANCELLED": 1,
            "BLOCKED": 1,
            "STALE": 1,
            "RUNNING": 1,
            "RUNNING_EXPIRED": 1,
            "OTHER": 1,
        }
        for status, delta in expected_delta.items():
            self.assertEqual(
                after["status_distribution"][status]
                - baseline["status_distribution"][status],
                delta,
                status,
            )

        self.assertEqual(
            sum(after["status_distribution"].values()),
            after_overview["today_used"],
        )

        self.assertEqual(
            after_overview["today_success"]
            - before_overview["today_success"],
            1,
        )
        self.assertEqual(
            after_overview["today_failed"]
            - before_overview["today_failed"],
            2,
        )
        self.assertEqual(
            after_overview["today_cancelled"]
            - before_overview["today_cancelled"],
            1,
        )

    def test_t4_02_six_operations_and_other(self):
        today = self.today()
        future = utc_db_now() + timedelta(hours=1)

        baseline = self._baseline()

        for operation in (
            "GENERATE",
            "ORGANIZE",
            "SUMMARY",
            "ASK",
            "PRACTICE_GENERATE",
            "PRACTICE_GRADE",
            "EXPERIMENT",
        ):
            self.create_ai_request(
                self.user_id,
                operation=operation,
                status="SUCCESS",
                request_date=today,
                leased_until=future,
            )

        after = self._baseline()

        for operation in (
            "GENERATE",
            "ORGANIZE",
            "SUMMARY",
            "ASK",
            "PRACTICE_GENERATE",
            "PRACTICE_GRADE",
            "OTHER",
        ):
            self.assertEqual(
                after["operation_distribution"][operation]
                - baseline["operation_distribution"][operation],
                1,
                operation,
            )

    def test_t4_03_expired_vs_valid_running_and_cross_day(self):
        today = self.today()
        yesterday = today - timedelta(days=1)
        future = utc_db_now() + timedelta(hours=1)
        past = utc_db_now() - timedelta(minutes=5)

        baseline = self._baseline()

        # 今天有效 / 今天过期 / 昨天有效 / 昨天过期
        self.create_ai_request(
            self.user_id,
            operation="ASK",
            status="RUNNING",
            request_date=today,
            leased_until=future,
        )
        self.create_ai_request(
            self.user_id,
            operation="ASK",
            status="RUNNING",
            request_date=today,
            leased_until=past,
        )
        self.create_ai_request(
            self.user_id,
            operation="ASK",
            status="RUNNING",
            request_date=yesterday,
            leased_until=future,
        )
        self.create_ai_request(
            self.user_id,
            operation="ASK",
            status="RUNNING",
            request_date=yesterday,
            leased_until=past,
        )

        after = self._baseline()

        # 跨日仍有效的 RUNNING 计入并发
        self.assertEqual(
            after["overview"]["current_active"]
            - baseline["overview"]["current_active"],
            2,
        )

        # 今日状态分布：有效 RUNNING 1，过期归 RUNNING_EXPIRED 1
        self.assertEqual(
            after["status_distribution"]["RUNNING"]
            - baseline["status_distribution"]["RUNNING"],
            1,
        )
        self.assertEqual(
            after["status_distribution"]["RUNNING_EXPIRED"]
            - baseline["status_distribution"]["RUNNING_EXPIRED"],
            1,
        )

        # 昨天的两条计入昨日趋势
        before_trend = {
            item["date"]: item["request_count"]
            for item in baseline["daily_trend"]
        }
        after_trend = {
            item["date"]: item["request_count"]
            for item in after["daily_trend"]
        }
        self.assertEqual(
            after_trend[yesterday.isoformat()]
            - before_trend[yesterday.isoformat()],
            2,
        )

    def test_t4_04_config_and_remaining(self):
        """A4 起额度来自 ai_runtime_config 动态配置，不再是静态 settings。"""
        data = self.ai_statistics(self.admin_token)
        config = data["config"]

        runtime = self.rows(
            "SELECT enabled, user_daily_limit, global_daily_limit "
            "FROM ai_runtime_config WHERE id = 1"
        )[0]

        self.assertEqual(
            config["configured_enabled"],
            bool(runtime["enabled"]),
        )
        self.assertEqual(
            config["enabled"],
            bool(runtime["enabled"])
            and bool(settings.DEEPSEEK_API_KEY),
        )
        self.assertEqual(
            config["user_daily_limit"],
            min(
                int(runtime["user_daily_limit"]),
                settings.AI_USER_DAILY_HARD_LIMIT,
            ),
        )
        self.assertEqual(
            config["global_daily_limit"],
            min(
                int(runtime["global_daily_limit"]),
                settings.AI_GLOBAL_DAILY_HARD_LIMIT,
            ),
        )
        self.assertEqual(
            config["user_concurrency"],
            settings.AI_USER_CONCURRENCY,
        )
        self.assertEqual(
            config["global_concurrency"],
            settings.AI_GLOBAL_CONCURRENCY,
        )


# ============================================================
# T5 审计 admin_username / 分页 / 筛选
# ============================================================


class TestAuditAdminUsername(BaseA3Test):

    def setUp(self):
        self.admin_id, self.admin_name, self.admin_token = (
            self.make_admin("op")
        )

    def _list(self, **params):
        response = self.client.get(
            "/admin/audit-logs",
            params=params,
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _ban(self, user_id: int, reason: str):
        response = self.client.post(
            f"/admin/users/{user_id}/ban",
            json={"reason": reason},
            headers={
                **self.auth(self.admin_token),
                **CSRF_HEADERS,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_t5_01_admin_username_in_items(self):
        user_id, _, _ = self.make_user("target")
        self._ban(user_id, "A3 审计用户名")

        data = self._list(page=1, page_size=100)
        matches = [
            item
            for item in data["items"]
            if item["target_id"] == user_id
            and item["action"] == "BAN_USER"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["admin_username"], self.admin_name
        )
        self.assertEqual(matches[0]["admin_id"], self.admin_id)

    def test_t5_02_pagination_with_admin_username(self):
        for index in range(2):
            user_id, _, _ = self.make_user(f"page{index}")
            self._ban(user_id, f"A3 审计分页 {index}")

        page1 = self._list(page=1, page_size=1)
        page2 = self._list(page=2, page_size=1)

        self.assertGreaterEqual(page1["total"], 2)
        self.assertEqual(len(page1["items"]), 1)
        self.assertEqual(len(page2["items"]), 1)
        self.assertNotEqual(
            page1["items"][0]["id"], page2["items"][0]["id"]
        )
        self.assertEqual(
            page1["items"][0]["admin_username"], self.admin_name
        )

    def test_t5_03_action_filter_with_admin_username(self):
        user_id, _, _ = self.make_user("filter")
        self._ban(user_id, "A3 审计筛选")

        revoke_id, revoke_name, _ = self.make_user("revoke")
        self.login(revoke_name)

        response = self.client.post(
            f"/admin/users/{revoke_id}/revoke-sessions",
            json={"reason": "A3 强制下线"},
            headers={
                **self.auth(self.admin_token),
                **CSRF_HEADERS,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

        data = self._list(
            page=1, page_size=100, action="REVOKE_SESSIONS"
        )
        self.assertTrue(
            all(
                item["action"] == "REVOKE_SESSIONS"
                for item in data["items"]
            )
        )
        expected = int(
            self.scalar(
                "SELECT COUNT(*) FROM admin_audit_logs "
                "WHERE action = 'REVOKE_SESSIONS'"
            )
        )
        self.assertEqual(data["total"], expected)
        if data["items"]:
            self.assertEqual(
                data["items"][0]["admin_username"], self.admin_name
            )


if __name__ == "__main__":
    unittest.main()