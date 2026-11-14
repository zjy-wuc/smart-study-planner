# smart_study_planner 数据库表结构

- 数据库：`smart_study_planner`
- MySQL 版本：8.4.9
- 生成时间：2026-11-14 21:59:45
- 表数量：8

## 表清单

| 表名 | 说明 | 字段数 | 行数（快照） |
| --- | --- | --- | --- |
| `daily_tasks` | - | 15 | 20 |
| `plan_steps` | - | 14 | 20 |
| `schedule_entries` | - | 9 | 18 |
| `study_plans` | - | 12 | 11 |
| `study_records` | - | 7 | 0 |
| `task_rollovers` | - | 5 | 0 |
| `tb_refresh_token` | 刷新令牌表 | 8 | 102 |
| `users` | 用户表 | 9 | 27 |

## `daily_tasks`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `plan_id` | bigint unsigned | NO | - | MUL | - |
| `step_id` | bigint unsigned | NO | - | MUL | - |
| `task_date` | date | NO | - | - | - |
| `task_type` | enum('BOOLEAN','NUMERIC') | NO | - | - | - |
| `content` | varchar(255) | NO | - | - | - |
| `target_quantity` | bigint unsigned | YES | - | - | - |
| `actual_quantity` | bigint unsigned | NO | 0 | - | - |
| `rollover_out_quantity` | bigint unsigned | NO | 0 | - | - |
| `status` | enum('PENDING','IN_PROGRESS','COMPLETED','OVERDUE','ENDED') | NO | PENDING | - | - |
| `completed_at` | datetime | YES | - | - | - |
| `deleted_at` | datetime | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |
| `updated_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| `numeric_active_date` | date | YES | - | - | STORED GENERATED；生成表达式：`(case when ((`task_type` = _utf8mb4\'NUMERIC\') and (`deleted_at` is null)) then `task_date` else NULL end)` |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| idx_daily_tasks_plan_date | 否 | BTREE | plan_id,task_date,deleted_at |
| idx_daily_tasks_step_date | 否 | BTREE | step_id,task_date |
| PRIMARY | 是 | BTREE | id |
| uk_daily_tasks_numeric_day | 是 | BTREE | step_id,numeric_active_date |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_daily_tasks_plan | plan_id | `study_plans`.`id` | NO ACTION | NO ACTION |
| fk_daily_tasks_step | step_id | `plan_steps`.`id` | NO ACTION | NO ACTION |

## `plan_steps`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `plan_id` | bigint unsigned | NO | - | MUL | - |
| `parent_id` | bigint unsigned | YES | - | MUL | - |
| `name` | varchar(100) | NO | - | - | - |
| `description` | text | YES | - | - | - |
| `node_type` | enum('GROUP','LEAF') | NO | - | - | - |
| `task_type` | enum('BOOLEAN','NUMERIC') | YES | - | - | - |
| `schedule_mode` | enum('REPEAT','DAILY_CUSTOM','AUTO_DISTRIBUTE','DAILY_MANUAL') | YES | - | - | - |
| `repeat_content` | varchar(255) | YES | - | - | - |
| `total_target` | bigint unsigned | YES | - | - | - |
| `sort_order` | int unsigned | NO | 0 | - | - |
| `deleted_at` | datetime | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |
| `updated_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| fk_plan_steps_parent | 否 | BTREE | parent_id |
| idx_plan_steps_tree | 否 | BTREE | plan_id,parent_id,deleted_at |
| PRIMARY | 是 | BTREE | id |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_plan_steps_parent | parent_id | `plan_steps`.`id` | NO ACTION | NO ACTION |
| fk_plan_steps_plan | plan_id | `study_plans`.`id` | NO ACTION | NO ACTION |

## `schedule_entries`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `step_id` | bigint unsigned | NO | - | MUL | - |
| `task_date` | date | NO | - | - | - |
| `content` | varchar(255) | YES | - | - | - |
| `target_quantity` | bigint unsigned | YES | - | - | - |
| `sort_order` | int unsigned | NO | 0 | - | - |
| `deleted_at` | datetime | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |
| `updated_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| idx_schedule_entries_step_date | 否 | BTREE | step_id,task_date,deleted_at |
| PRIMARY | 是 | BTREE | id |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_schedule_entries_step | step_id | `plan_steps`.`id` | NO ACTION | NO ACTION |

## `study_plans`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `user_id` | bigint unsigned | NO | - | MUL | - |
| `name` | varchar(100) | NO | - | - | - |
| `description` | text | YES | - | - | - |
| `start_date` | date | NO | - | - | - |
| `end_date` | date | NO | - | - | - |
| `status` | enum('DRAFT','ACTIVE','ENDED') | NO | DRAFT | - | - |
| `started_at` | datetime | YES | - | - | - |
| `ended_at` | datetime | YES | - | - | - |
| `deleted_at` | datetime | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |
| `updated_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| idx_study_plans_user_status | 否 | BTREE | user_id,status,deleted_at |
| PRIMARY | 是 | BTREE | id |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_study_plans_user | user_id | `users`.`id` | NO ACTION | NO ACTION |

**CHECK 约束**

- `chk_study_plans_dates`：(`start_date` <= `end_date`)

## `study_records`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `task_id` | bigint unsigned | NO | - | MUL | - |
| `user_id` | bigint unsigned | NO | - | MUL | - |
| `event_type` | enum('BOOLEAN_COMPLETE','NUMERIC_PROGRESS') | NO | - | - | - |
| `recorded_value` | bigint unsigned | YES | - | - | - |
| `task_date` | date | NO | - | - | - |
| `recorded_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| fk_study_records_user | 否 | BTREE | user_id |
| idx_study_records_task_time | 否 | BTREE | task_id,recorded_at |
| PRIMARY | 是 | BTREE | id |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_study_records_task | task_id | `daily_tasks`.`id` | NO ACTION | NO ACTION |
| fk_study_records_user | user_id | `users`.`id` | NO ACTION | NO ACTION |

## `task_rollovers`

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `source_task_id` | bigint unsigned | NO | - | MUL | - |
| `target_task_id` | bigint unsigned | NO | - | MUL | - |
| `quantity` | bigint unsigned | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| fk_task_rollovers_target | 否 | BTREE | target_task_id |
| PRIMARY | 是 | BTREE | id |
| uk_rollover_source_target | 是 | BTREE | source_task_id,target_task_id |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_task_rollovers_source | source_task_id | `daily_tasks`.`id` | NO ACTION | NO ACTION |
| fk_task_rollovers_target | target_task_id | `daily_tasks`.`id` | NO ACTION | NO ACTION |

**CHECK 约束**

- `chk_rollover_not_self`：(`source_task_id` <> `target_task_id`)

## `tb_refresh_token`

> 刷新令牌表

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `user_id` | bigint unsigned | NO | - | MUL | - |
| `token_hash` | char(64) | NO | - | UNI | - |
| `family_id` | char(36) | NO | - | - | - |
| `expires_at` | datetime | NO | - | MUL | - |
| `revoked_at` | datetime | YES | - | - | - |
| `replaced_by` | char(64) | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| idx_refresh_expires_at | 否 | BTREE | expires_at |
| idx_refresh_user_family | 否 | BTREE | user_id,family_id |
| PRIMARY | 是 | BTREE | id |
| uk_refresh_token_hash | 是 | BTREE | token_hash |

**外键**

| 约束名 | 字段 | 引用 | ON UPDATE | ON DELETE |
| --- | --- | --- | --- | --- |
| fk_refresh_token_user | user_id | `users`.`id` | NO ACTION | CASCADE |

## `users`

> 用户表

| 字段 | 类型 | 允许空 | 默认值 | 键 | 附加 |
| --- | --- | --- | --- | --- | --- |
| `id` | bigint unsigned | NO | - | PRI | auto_increment |
| `username` | varchar(50) | NO | - | UNI | - |
| `password_hash` | varchar(255) | NO | - | - | - |
| `email` | varchar(100) | YES | - | UNI | - |
| `nickname` | varchar(50) | YES | - | - | - |
| `avatar_url` | varchar(255) | YES | - | - | - |
| `created_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED |
| `updated_at` | datetime | NO | CURRENT_TIMESTAMP | - | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| `is_active` | tinyint | NO | 1 | - | - |

**索引**

| 索引名 | 唯一 | 类型 | 列 |
| --- | --- | --- | --- |
| PRIMARY | 是 | BTREE | id |
| uk_users_email | 是 | BTREE | email |
| uk_users_username | 是 | BTREE | username |
