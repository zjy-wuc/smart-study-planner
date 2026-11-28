"""笔记内容 D2：项目进阶、Redis 进阶与 Python 工程化（12 篇）。"""

NOTES = [
    {
        "key": "ssp-05",
        "title": "数值任务、打卡记录与一致性校验",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "打卡", "一致性"],
        "concept": "数值任务的完成量由打卡记录累加得到。任务完成时 actual_quantity 必须等于对应学习记录的数量之和，且加上顺延量不能超过目标量。",
        "principles": [
            "每次打卡写入一条学习记录，记录数量与时间。",
            "任务完成时汇总记录更新 actual_quantity。",
            "actual_quantity + rollover_out_quantity ≤ target_quantity。",
            "布尔任务完成时 actual_quantity 固定为 1。",
        ],
        "example": """```sql
SELECT t.id, t.target_quantity, t.actual_quantity,
       COALESCE(SUM(r.quantity), 0) AS recorded
FROM daily_tasks t
LEFT JOIN study_records r ON r.task_id = t.id
WHERE t.task_type = 'NUMERIC'
GROUP BY t.id
HAVING t.actual_quantity <> recorded;
-- 结果应为空
```""",
        "summary": [
            "打卡记录是数值完成量的唯一事实来源。",
            "一致性校验应覆盖任务、记录与顺延三张表。",
            "完成量绝不能超过目标量。",
        ],
        "key_points": [
            "数值完成量由打卡记录累加",
            "任务完成量应等于记录合计",
            "完成量加顺延量不超过目标",
            "布尔任务完成量为 1",
        ],
        "quizzes": [
            {"q": "数值任务的 actual_quantity 应该等于什么？", "a": "等于该任务所有学习记录 quantity 的合计。"},
            {"q": "为什么 actual_quantity 加顺延量不能超过目标量？", "a": "顺延的是未完成部分，超过目标会导致重复计算与数据不一致。"},
        ],
    },
    {
        "key": "ssp-06",
        "title": "AI 准入、频率限制与并发租约",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "AI", "限流"],
        "concept": "AI 接口需要多层保护：登录鉴权、每日额度、频率限制、全局并发租约和超时控制。租约确保同一用户不会同时发起多个生成请求。",
        "principles": [
            "每日额度按用户与全局分别限制。",
            "频率限制使用 Redis 计数器与过期时间。",
            "租约有过期时间，避免进程崩溃后永久占用。",
            "流式响应超时必须小于租约时间。",
        ],
        "example": """```python
if not acquire_lease(user_id, ttl=180):
    raise HTTPException(429, "已有生成任务进行中")

try:
    async for chunk in provider.stream(prompt):
        yield chunk
finally:
    release_lease(user_id)
```""",
        "summary": [
            "AI 保护需要额度、频率、并发三层控制。",
            "租约要设置过期时间防止死锁。",
            "流式超时与租约时间必须协调。",
        ],
        "key_points": [
            "AI 接口需要多层准入控制",
            "每日额度分用户与全局",
            "频率限制使用 Redis 计数",
            "租约必须设置过期时间",
        ],
        "quizzes": [
            {"q": "为什么 AI 租约必须设置过期时间？", "a": "进程异常退出时租约仍能自动释放，避免用户被永久锁定。"},
            {"q": "流式响应超时与租约时间应满足什么关系？", "a": "流式超时应小于租约时间，保证租约有效期内完成或主动结束。"},
        ],
    },
    {
        "key": "ssp-07",
        "title": "知识笔记、复习记录与练习闭环",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "笔记", "复习"],
        "concept": "知识笔记归属用户与学习计划，复习记录追踪每次复习时间，AI 练习基于笔记内容生成题目并保存批改结果，形成学习闭环。",
        "principles": [
            "笔记必须与用户、计划、步骤归属一致。",
            "复习记录用于计算下次复习时间与掌握度。",
            "练习题与批改结果保存为 JSON，保留参考答案与得分。",
            "删除笔记前要检查练习与复习记录的依赖。",
        ],
        "example": """```text
笔记《MySQL 索引》 -> 复习记录（3 次）
                  -> AI 练习（5 题，得分 80）
                  -> 错题反馈 -> 下次复习重点
```""",
        "summary": [
            "笔记、复习、练习三者通过 note_id 关联。",
            "归属一致性是数据校验重点。",
            "历史练习应保存快照，避免笔记变更影响结果。",
        ],
        "key_points": [
            "笔记归属用户与计划",
            "复习记录追踪复习时间",
            "练习题目基于笔记内容",
            "删除笔记需检查依赖",
        ],
        "quizzes": [
            {"q": "笔记、复习记录和练习记录通过什么关联？", "a": "通过 note_id 关联，并同时校验用户归属。"},
            {"q": "为什么练习记录要保存题目与批改快照？", "a": "笔记后续修改或删除时，历史练习结果仍可稳定展示。"},
        ],
    },
    {
        "key": "ssp-08",
        "title": "专注计时、会话状态与统计口径",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "专注", "统计"],
        "concept": "专注会话记录计划时长、实际专注时长与状态。统计时只计入已完成会话，取消会话不计入有效专注时长。",
        "principles": [
            "专注会话状态包括进行中、已完成、已取消。",
            "实际专注时长不能超过计划时长。",
            "统计按业务时区聚合到自然日。",
            "进行中的会话需要 running_started_at 支持恢复。",
        ],
        "example": """```sql
SELECT focus_date, SUM(focused_seconds) AS total_seconds
FROM focus_sessions
WHERE user_id = 42 AND status = 'COMPLETED'
GROUP BY focus_date
ORDER BY focus_date DESC;
```""",
        "summary": [
            "专注统计只计入有效会话。",
            "业务时区决定自然日归属。",
            "会话状态与时间字段必须成对维护。",
        ],
        "key_points": [
            "专注会话有进行中完成取消三态",
            "实际时长不超过计划时长",
            "统计按业务时区聚合",
            "进行中会话依赖开始时间恢复",
        ],
        "quizzes": [
            {"q": "专注统计是否应计入已取消会话？", "a": "不应计入，已取消会话不代表有效专注时间。"},
            {"q": "为什么统计要指定业务时区？", "a": "不同时区会导致同一时间点归属到不同自然日，影响日报与趋势。"},
        ],
    },
    {
        "key": "ssp-09",
        "title": "管理端权限、封禁与审计日志",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "管理端", "审计"],
        "concept": "管理端接口要求 ADMIN 角色。封禁用户、撤销会话、修改 AI 配置等敏感操作必须写入审计日志，记录操作者、目标、原因与变更前后值。",
        "principles": [
            "普通用户访问管理接口返回 403。",
            "封禁用户后其登录与令牌刷新都应被拒绝。",
            "审计日志只追加，不随业务数据删除。",
            "敏感配置修改必须填写原因。",
        ],
        "example": """```text
PATCH /admin/users/42/status
  admin_id: 1
  action: BAN_USER
  target: 42
  reason: 违规内容
  before: {"is_active": 1}
  after:  {"is_active": 0}
```""",
        "summary": [
            "角色校验是管理端的第一道防线。",
            "封禁必须同时影响登录与刷新。",
            "审计日志是安全追溯的核心资产。",
        ],
        "key_points": [
            "管理接口要求 ADMIN 角色",
            "封禁后登录与刷新都应拒绝",
            "审计日志只追加不删除",
            "敏感配置修改需填写原因",
        ],
        "quizzes": [
            {"q": "普通用户访问管理接口应返回什么状态码？", "a": "403，表示已认证但无权限。"},
            {"q": "为什么审计日志不能随业务数据一起删除？", "a": "审计日志是安全追溯与合规证据，需要独立保留。"},
        ],
    },
    {
        "key": "ssp-10",
        "title": "数据库迁移、备份与发布顺序",
        "domain": "Smart Study Planner 项目开发",
        "tags": ["项目", "迁移", "发布"],
        "concept": "数据库迁移必须按依赖顺序执行，并在执行前完整备份。DDL 会隐式提交，失败后不能假设整体回滚，应从备份恢复后重跑。",
        "principles": [
            "迁移前执行 mysqldump 并验证可恢复性。",
            "脚本应包含目标库与前置状态断言。",
            "迁移期间停止应用写入与定时任务。",
            "迁移后校验表数量、关键字段与数据一致性。",
        ],
        "example": """```bash
mysqldump --single-transaction --routines --triggers \\
  smart_study_planner > backup.sql

mysql smart_study_planner < Auth_V2.sql
mysql smart_study_planner < V3.0.sql
```""",
        "summary": [
            "备份与可恢复性验证是迁移的前置条件。",
            "迁移脚本必须自带库名与状态断言。",
            "失败后从备份恢复重跑，禁止续跑半成品。",
        ],
        "key_points": [
            "迁移前必须完整备份",
            "DDL 隐式提交不能依赖事务回滚",
            "迁移期间停止写入与定时任务",
            "迁移后校验表结构与数据",
        ],
        "quizzes": [
            {"q": "为什么数据库迁移失败后不能直接在中途继续？", "a": "DDL 隐式提交可能留下部分完成状态，继续执行会破坏断言与结构一致性。"},
            {"q": "迁移前备份需要验证什么？", "a": "验证备份能成功恢复到全新库，并核对表数量与关键行数。"},
        ],
    },
    {
        "key": "rd-04",
        "title": "缓存一致性：先更新数据库还是先删缓存",
        "domain": "Redis",
        "tags": ["Redis", "缓存一致性", "双写"],
        "concept": "缓存与数据库双写存在短暂不一致。常用策略是先更新数据库再删除缓存（Cache Aside），并配合延迟双删或消息补偿降低不一致窗口。",
        "principles": [
            "更新数据库后删除缓存，而不是直接更新缓存。",
            "删除失败时应重试或写入补偿队列。",
            "强一致场景应让缓存只承担加速，关键读走数据库。",
            "为缓存设置过期时间是最终兜底。",
        ],
        "example": """```python
def update_plan(plan_id, data):
    db.update_plan(plan_id, data)
    try:
        redis.delete(f"plan:{plan_id}")
    except RedisError:
        compensation_queue.push(plan_id)
```""",
        "summary": [
            "Cache Aside 是工程中最常用的策略。",
            "删除缓存比更新缓存更不容易产生脏数据。",
            "过期时间与补偿机制是最终一致性保障。",
        ],
        "key_points": [
            "先更新数据库再删除缓存",
            "删除失败需要补偿",
            "强一致场景不能只依赖缓存",
            "过期时间是最终兜底",
        ],
        "quizzes": [
            {"q": "为什么通常删除缓存而不是更新缓存？", "a": "并发更新时直接写缓存容易产生旧值覆盖新值，删除后按需回源更安全。"},
            {"q": "缓存删除失败应如何处理？", "a": "重试或写入补偿队列，并依赖过期时间最终兜底。"},
        ],
    },
    {
        "key": "rd-05",
        "title": "Redis 持久化：RDB、AOF 与混合模式",
        "domain": "Redis",
        "tags": ["Redis", "持久化", "RDB"],
        "concept": "RDB 生成某一时刻的数据快照，恢复快但可能丢失最近写入；AOF 追加写命令，数据更完整但文件更大；混合持久化结合两者优点。",
        "principles": [
            "RDB 适合备份与快速恢复。",
            "AOF 的 fsync 策略影响性能与数据安全。",
            "AOF 重写可压缩文件体积。",
            "缓存场景可关闭持久化，但会话与锁数据需要评估。",
        ],
        "table": "| 方式 | 数据安全 | 恢复速度 | 文件体积 |\n|---|---|---|---|\n| RDB | 较低 | 快 | 小 |\n| AOF | 较高 | 较慢 | 大 |\n| 混合 | 较高 | 较快 | 中 |",
        "example": """```conf
save 900 1
appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes
```""",
        "summary": [
            "RDB 与 AOF 在安全性和性能之间取舍。",
            "everysec 是常用的 AOF 折中策略。",
            "持久化策略要结合数据可丢失程度确定。",
        ],
        "key_points": [
            "RDB 是时间点快照",
            "AOF 追加写命令",
            "appendfsync everysec 是折中策略",
            "混合持久化结合两者优点",
        ],
        "quizzes": [
            {"q": "RDB 持久化的主要风险是什么？", "a": "两次快照之间的数据可能丢失。"},
            {"q": "AOF 的 everysec 策略意味着什么？", "a": "每秒将缓冲区刷盘一次，兼顾性能与最多约一秒的数据丢失。"},
        ],
    },
    {
        "key": "rd-06",
        "title": "Redis 限流：固定窗口、滑动窗口与令牌桶",
        "domain": "Redis",
        "tags": ["Redis", "限流", "计数器"],
        "concept": "限流保护系统不被突发流量击穿。固定窗口实现简单但有临界突刺；滑动窗口更平滑；令牌桶允许一定突发并控制平均速率。",
        "principles": [
            "固定窗口使用 INCR + EXPIRE。",
            "滑动窗口使用 ZSet 记录请求时间戳。",
            "令牌桶按速率补充令牌，请求消耗令牌。",
            "限流键要包含用户、接口和时间维度。",
        ],
        "example": """```lua
-- 固定窗口限流
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local current = redis.call("INCR", key)
if current == 1 then
  redis.call("EXPIRE", key, 60)
end
if current > limit then
  return 0
end
return 1
```""",
        "summary": [
            "固定窗口简单但存在边界突刺。",
            "滑动窗口与令牌桶更平滑。",
            "限流键设计决定限流粒度。",
        ],
        "key_points": [
            "固定窗口使用 INCR 与过期时间",
            "滑动窗口使用 ZSet 记录时间戳",
            "令牌桶允许一定突发",
            "限流键应包含用户与接口维度",
        ],
        "quizzes": [
            {"q": "固定窗口限流的临界问题是什么？", "a": "窗口边界前后可能瞬间通过两倍限额的请求。"},
            {"q": "令牌桶如何允许突发流量？", "a": "桶中预存令牌，突发请求可以一次性消耗多个令牌。"},
        ],
    },
    {
        "key": "rd-07",
        "title": "分布式锁续期、Redlock 与争议",
        "domain": "Redis",
        "tags": ["Redis", "分布式锁", "Redlock"],
        "concept": "业务执行时间不确定时，需要看门狗为锁续期。Redlock 通过在多个独立 Redis 节点上获取多数锁提高容错，但其强一致性保证仍存在争议。",
        "principles": [
            "续期必须校验令牌，避免为他人的锁续期。",
            "看门狗应按剩余时间比例定期续期。",
            "Redlock 需要多个独立主节点，不能是主从复制关系。",
            "强一致场景应使用数据库唯一约束或共识系统。",
        ],
        "example": """```python
# 续期脚本：仅当令牌匹配时延长过期时间
RENEW_LUA = '''
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("pexpire", KEYS[1], ARGV[2])
end
return 0
'''
```""",
        "summary": [
            "续期解决业务执行超过锁 TTL 的问题。",
            "Redlock 提升容错但不等于强一致。",
            "关键互斥应优先考虑数据库约束。",
        ],
        "key_points": [
            "锁续期必须校验持有者令牌",
            "看门狗按剩余时间定期续期",
            "Redlock 使用多个独立节点",
            "强一致场景优先数据库约束",
        ],
        "quizzes": [
            {"q": "看门狗续期时为什么必须校验令牌？", "a": "防止锁已过期并被他人获取后，原持有者误续期导致互斥失效。"},
            {"q": "Redlock 能提供绝对强一致吗？", "a": "不能，在时钟漂移、网络分区等情况下仍存在争议与理论风险。"},
        ],
    },
    {
        "key": "py-09",
        "title": "Python 工程化：依赖、配置与日志",
        "domain": "Python",
        "tags": ["Python", "工程化", "配置"],
        "concept": "可维护的 Python 项目需要锁定依赖、集中配置、结构化日志和明确的启动入口。配置从环境变量读取，敏感信息不进入代码仓库。",
        "principles": [
            "使用虚拟环境与锁文件保证依赖可复现。",
            "配置集中到 settings 对象，避免散落读取环境变量。",
            "日志使用结构化字段，便于检索与告警。",
            "启动时校验关键配置，缺失时快速失败。",
        ],
        "example": """```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_host: str
    db_name: str
    secret_key: str

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```""",
        "summary": [
            "依赖锁定保证环境一致。",
            "配置集中管理并启动时校验。",
            "结构化日志提升可观测性。",
        ],
        "key_points": [
            "虚拟环境与锁文件保证依赖一致",
            "配置集中到 settings 对象",
            "敏感配置从环境变量读取",
            "启动时校验关键配置",
        ],
        "quizzes": [
            {"q": "为什么配置要集中到 settings 对象？", "a": "避免散落的环境变量读取与默认值不一致，便于校验和测试。"},
            {"q": "敏感配置应如何提供？", "a": "通过环境变量或密钥管理系统注入，不写入代码与仓库。"},
        ],
    },
    {
        "key": "py-10",
        "title": "Python 性能分析：cProfile 与优化顺序",
        "domain": "Python",
        "tags": ["Python", "性能", "cProfile"],
        "concept": "性能优化应先测量再修改。cProfile 统计函数调用次数与耗时，line_profiler 定位热点行，memory_profiler 观察内存增长。",
        "principles": [
            "先确定瓶颈是 CPU、I/O 还是内存。",
            "优先优化调用次数多且单次耗时高的函数。",
            "算法复杂度优化通常比微优化收益更大。",
            "缓存、批量操作和减少序列化是常见手段。",
        ],
        "example": """```bash
python -m cProfile -o profile.out app.py
python -m pstats profile.out
# 在 pstats 中执行 sort cumtime 查看累计耗时
```""",
        "summary": [
            "测量是性能优化的起点。",
            "优先优化热点函数与算法复杂度。",
            "避免在没有数据支撑时做微优化。",
        ],
        "key_points": [
            "先测量再优化",
            "cProfile 统计函数调用与耗时",
            "优先优化热点函数",
            "算法优化通常收益最大",
        ],
        "quizzes": [
            {"q": "性能优化应该先做什么？", "a": "先用 profiler 测量，确定瓶颈类型与热点位置。"},
            {"q": "为什么算法复杂度优化优先于微优化？", "a": "复杂度决定增长趋势，规模增大时收益远大于常数级微调。"},
        ],
    },
]