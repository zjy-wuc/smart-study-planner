-- ============================================
-- smart_study_planner 数据库初始化脚本（全新环境）
-- 直接创建最终结构的 8 张表
-- ============================================

USE smart_study_planner;

-- 1. users 用户表（含迁移补充的 email、avatar_url）
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username      VARCHAR(50)     NOT NULL COMMENT '登录用户名',
    password_hash VARCHAR(255)    NOT NULL COMMENT '密码哈希',
    email         VARCHAR(100)    NULL COMMENT '邮箱（可选）',
    nickname      VARCHAR(50)     NULL COMMENT '用户昵称',
    avatar_url    VARCHAR(255)    NULL COMMENT '头像地址（可选）',
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username),
    UNIQUE KEY uk_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 2. plans 学习计划表（直接用 description，不走 rename）
CREATE TABLE IF NOT EXISTS plans (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL COMMENT '所属用户',
    parent_plan_id  BIGINT UNSIGNED NULL COMMENT '父计划 ID',
    title           VARCHAR(100)    NOT NULL COMMENT '计划名称',
    description     TEXT            NULL COMMENT '计划描述',
    planning_mode   VARCHAR(20)     NOT NULL COMMENT 'SUBPLANS / DAILY_TASKS',
    start_date      DATE            NULL COMMENT '开始日期',
    end_date        DATE            NULL COMMENT '结束日期',
    status          VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/PAUSED/ARCHIVED',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_plans_user (user_id),
    KEY idx_plans_parent (parent_plan_id),
    CONSTRAINT fk_plans_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_plans_parent FOREIGN KEY (parent_plan_id) REFERENCES plans(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习计划表';

-- 3. tasks 每日任务表（含迁移补充的 knowledge_node_id）
CREATE TABLE IF NOT EXISTS tasks (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    plan_id          BIGINT UNSIGNED NOT NULL COMMENT '所属计划 ID',
    knowledge_node_id BIGINT UNSIGNED NULL COMMENT '关联知识节点（可选）',
    title            VARCHAR(100)    NOT NULL COMMENT '任务名称',
    description      TEXT            NULL COMMENT '任务说明',
    task_type        VARCHAR(20)     NOT NULL COMMENT 'BOOLEAN / NUMERIC',
    is_completed     TINYINT(1)      NULL COMMENT '布尔型任务完成状态',
    target_value     DECIMAL(10,2)   NULL COMMENT '数值型目标值',
    current_value    DECIMAL(10,2)   NULL COMMENT '数值型当前值',
    unit             VARCHAR(20)     NULL COMMENT '单位',
    due_date         DATE            NOT NULL COMMENT '任务日期',
    created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tasks_plan (plan_id),
    KEY idx_tasks_knowledge_node (knowledge_node_id),
    KEY idx_tasks_plan_due (plan_id, due_date),
    CONSTRAINT fk_tasks_plan FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日任务表';

-- 4. task_rules 任务规则表（与 tasks 1:1）
CREATE TABLE IF NOT EXISTS task_rules (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id          BIGINT UNSIGNED NOT NULL COMMENT '关联 tasks.id',
    frequency        VARCHAR(20)     NOT NULL DEFAULT 'DAILY' COMMENT '重复周期 DAILY/WEEKLY',
    interval_count   INT             NOT NULL DEFAULT 1 COMMENT '重复间隔',
    target_value     VARCHAR(50)     NULL COMMENT '目标值',
    estimated_minute INT             NULL COMMENT '预计时长（分钟）',
    start_date       DATE            NOT NULL COMMENT '生效开始日期',
    end_date         DATE            NULL COMMENT '生效结束日期',
    created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_rules_task (task_id),
    CONSTRAINT fk_task_rules_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务规则表';

-- 5. daily_tasks 每日任务表（N:1 挂在 tasks 下）
CREATE TABLE IF NOT EXISTS daily_tasks (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id      BIGINT UNSIGNED NOT NULL COMMENT '关联 tasks.id',
    task_date    DATE            NOT NULL COMMENT '任务日期',
    target_value VARCHAR(50)     NULL COMMENT '目标值',
    actual_value VARCHAR(50)     NULL COMMENT '实际完成值',
    status       TINYINT         NOT NULL DEFAULT 0 COMMENT '0未开始 1进行中 2已完成 3已超期',
    remark       TEXT            NULL COMMENT '备注',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_daily_tasks_task (task_id),
    KEY idx_daily_tasks_date (task_date),
    CONSTRAINT fk_daily_tasks_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日任务表';

-- 6. checkin_records 打卡记录表
CREATE TABLE IF NOT EXISTS checkin_records (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    daily_task_id    BIGINT UNSIGNED NOT NULL COMMENT '关联 daily_tasks.id',
    checkin_time     DATETIME        NOT NULL COMMENT '打卡时间',
    record_type      VARCHAR(20)     NOT NULL COMMENT '打卡类型',
    value            VARCHAR(50)     NULL COMMENT '完成值',
    duration_minutes INT             NULL COMMENT '学习时长（分钟）',
    note             TEXT            NULL COMMENT '备注',
    created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_checkin_daily_task (daily_task_id),
    CONSTRAINT fk_checkin_daily_task FOREIGN KEY (daily_task_id) REFERENCES daily_tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='打卡记录表';

-- 7. knowledge_nodes 知识节点表（独立树）
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    parent_id   BIGINT UNSIGNED NULL COMMENT '父节点（自关联，根节点为空）',
    name        VARCHAR(100)    NOT NULL COMMENT '节点名称',
    description TEXT            NULL COMMENT '节点描述',
    sort_order  INT             NOT NULL DEFAULT 0 COMMENT '排序',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_knowledge_parent (parent_id),
    CONSTRAINT fk_knowledge_parent FOREIGN KEY (parent_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识节点表';

-- 8. daily_reviews 每日复盘表
CREATE TABLE IF NOT EXISTS daily_reviews (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    review_date DATE            NOT NULL COMMENT '复盘日期',
    content     TEXT            NULL COMMENT '复盘内容',
    problems    TEXT            NULL COMMENT '遇到的问题',
    adjustments TEXT            NULL COMMENT '调整计划',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_reviews_user (user_id),
    KEY idx_reviews_date (review_date),
    CONSTRAINT fk_reviews_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日复盘表';
