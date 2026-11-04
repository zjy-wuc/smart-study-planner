-- ============================================
-- smart_study_planner 数据库增量迁移脚本 (2026-11-01)
-- 保留 users / plans / tasks，新增 5 张表
-- ============================================

-- 1. users 表：补 email、avatar_url
ALTER TABLE users
    ADD COLUMN email      VARCHAR(100) NULL COMMENT '邮箱（可选）' AFTER password_hash,
    ADD COLUMN avatar_url VARCHAR(255) NULL COMMENT '头像地址（可选）' AFTER nickname,
    ADD UNIQUE KEY uk_users_email (email);

-- 2. plans 表：descriptions -> description 改名
ALTER TABLE plans
    RENAME COLUMN descriptions TO description;

-- 3. tasks 表：加可选的 knowledge_node_id
ALTER TABLE tasks
    ADD COLUMN knowledge_node_id BIGINT UNSIGNED NULL COMMENT '关联知识节点（可选）' AFTER plan_id,
    ADD KEY idx_tasks_knowledge_node (knowledge_node_id);

-- 4. task_rules 任务规则表（与 tasks 1:1）
CREATE TABLE IF NOT EXISTS task_rules (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id          BIGINT UNSIGNED NOT NULL COMMENT '关联 tasks.id',
    frequency        VARCHAR(20)     NOT NULL DEFAULT 'DAILY' COMMENT '重复周期 DAILY/WEEKLY',
    interval_count   INT             NOT NULL DEFAULT 1 COMMENT '重复间隔（如每 1 天）',
    target_value     VARCHAR(50)     NULL COMMENT '目标值（如 50）',
    estimated_minute INT             NULL COMMENT '预计时长（分钟）',
    start_date       DATE            NOT NULL COMMENT '生效开始日期',
    end_date         DATE            NULL COMMENT '生效结束日期',
    created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_rules_task (task_id),
    CONSTRAINT fk_task_rules_task FOREIGN KEY (task_id)
        REFERENCES tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务规则表（1:1 挂在 tasks 下）';

-- 5. daily_tasks 每日任务表（N:1 挂在 tasks 下）
CREATE TABLE IF NOT EXISTS daily_tasks (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id      BIGINT UNSIGNED NOT NULL COMMENT '关联 tasks.id',
    task_date    DATE            NOT NULL COMMENT '任务日期',
    target_value VARCHAR(50)     NULL COMMENT '目标值（如 50）',
    actual_value VARCHAR(50)     NULL COMMENT '实际完成值（可空）',
    status       TINYINT         NOT NULL DEFAULT 0 COMMENT '0未开始 1进行中 2已完成 3已超期',
    remark       TEXT            NULL COMMENT '备注',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_daily_tasks_task (task_id),
    KEY idx_daily_tasks_date (task_date),
    CONSTRAINT fk_daily_tasks_task FOREIGN KEY (task_id)
        REFERENCES tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日任务表（规则自动生成，也可手动建）';

-- 6. checkin_records 打卡记录表（N:1 挂在 daily_tasks 下）
CREATE TABLE IF NOT EXISTS checkin_records (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    daily_task_id    BIGINT UNSIGNED NOT NULL COMMENT '关联 daily_tasks.id',
    checkin_time     DATETIME        NOT NULL COMMENT '打卡时间',
    record_type      VARCHAR(20)     NOT NULL COMMENT '打卡类型（数量/时长/完成）',
    value            VARCHAR(50)     NULL COMMENT '完成值（如 50）',
    duration_minutes INT             NULL COMMENT '学习时长（分钟）',
    note             TEXT            NULL COMMENT '备注',
    created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_checkin_daily_task (daily_task_id),
    CONSTRAINT fk_checkin_daily_task FOREIGN KEY (daily_task_id)
        REFERENCES daily_tasks(id) ON DELETE CASCADE
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
    CONSTRAINT fk_knowledge_parent FOREIGN KEY (parent_id)
        REFERENCES knowledge_nodes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识节点表（独立知识体系树）';

-- 8. daily_reviews 每日复盘表（N:1 挂在 users 下）
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
    CONSTRAINT fk_reviews_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日复盘表';
