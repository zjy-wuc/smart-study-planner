"""笔记内容 A2：FastAPI 进阶、MySQL 与 Redis 基础（12 篇）。"""

NOTES = [
    {
        "key": "fa-06",
        "title": "FastAPI 与 SQLAlchemy 会话管理",
        "domain": "FastAPI",
        "tags": ["FastAPI", "SQLAlchemy", "事务"],
        "concept": "数据库会话是工作单元，负责跟踪对象状态并管理事务。FastAPI 通过依赖为每个请求创建独立会话，请求结束后关闭，避免会话跨请求共享。",
        "principles": [
            "Session 不是线程安全的，不能全局复用同一个实例。",
            "读操作也应在会话中执行，并在结束时释放连接。",
            "事务边界应放在服务层，避免路由层随意 commit。",
            "异常时必须 rollback，否则连接可能停留在失败事务中。",
        ],
        "example": """```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.post("/plans")
def create_plan(data: PlanCreate, db=Depends(get_db)):
    return plan_service.create(db, data)
```""",
        "summary": [
            "每个请求一个会话，请求结束即释放。",
            "事务边界放在服务层，路由只负责协议转换。",
            "异常回滚与关闭缺一不可。",
        ],
        "key_points": [
            "Session 不是线程安全的",
            "每个请求应使用独立会话",
            "事务边界适合放在服务层",
            "异常时必须回滚并关闭会话",
        ],
        "quizzes": [
            {"q": "为什么不能把 SQLAlchemy Session 定义为全局单例？", "a": "Session 不是线程安全的，跨请求共享会导致状态混乱与事务串扰。"},
            {"q": "请求结束时必须执行哪些清理？", "a": "异常时回滚事务，并在 finally 中关闭会话释放连接。"},
        ],
    },
    {
        "key": "fa-07",
        "title": "FastAPI 流式响应与 SSE 实践",
        "domain": "FastAPI",
        "tags": ["FastAPI", "SSE", "流式响应"],
        "concept": "SSE（Server-Sent Events）通过长连接持续向浏览器推送文本事件，适合 AI 生成内容的逐步输出。FastAPI 使用 StreamingResponse 返回异步生成器。",
        "principles": [
            "响应头必须包含 text/event-stream。",
            "每条消息以 data: 开头，并以两个换行结束。",
            "客户端断开后应停止生成，避免继续消耗模型额度。",
            "生成器内要处理异常并发送明确的结束事件。",
        ],
        "example": """```python
async def event_stream():
    try:
        async for chunk in provider.stream(prompt):
            yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\\n\\n"
        yield "data: [DONE]\\n\\n"
    except ProviderError as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\\n\\n"

@router.post("/ai/ask")
async def ask(payload: AskRequest):
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
```""",
        "summary": [
            "SSE 是单向、基于文本的服务器推送协议。",
            "流式接口必须处理客户端断开与上游异常。",
            "结束事件让前端能够正确关闭连接与状态。",
        ],
        "key_points": [
            "SSE 使用 text/event-stream 响应类型",
            "每条事件以 data 开头并以空行结束",
            "客户端断开后应停止上游生成",
            "流式响应需要明确的结束事件",
        ],
        "quizzes": [
            {"q": "SSE 响应必须设置什么 Content-Type？", "a": "text/event-stream。"},
            {"q": "为什么流式接口要监听客户端断开？", "a": "避免客户端已离开后仍继续调用模型，浪费额度与连接资源。"},
        ],
    },
    {
        "key": "my-01",
        "title": "InnoDB 索引结构与 B+ 树",
        "domain": "MySQL",
        "tags": ["MySQL", "索引", "B+树"],
        "concept": "InnoDB 使用 B+ 树组织索引。非叶子节点只存键和页指针，叶子节点存放数据或主键，并通过链表相连，因此范围查询和排序效率较高。",
        "principles": [
            "聚簇索引的叶子节点就是数据行，主键决定物理组织方式。",
            "二级索引叶子节点存放主键值，查询非索引列需要回表。",
            "联合索引遵循最左前缀原则。",
            "索引不是越多越好，写入与存储成本会随索引数量增加。",
        ],
        "table": "| 索引类型 | 叶子内容 | 典型场景 |\n|---|---|---|\n| 聚簇索引 | 完整数据行 | 主键查询 |\n| 二级索引 | 索引列 + 主键 | 条件过滤 |\n| 覆盖索引 | 查询所需列 | 避免回表 |",
        "example": """```sql
-- 联合索引 (user_id, status, created_at)
EXPLAIN SELECT id, name
FROM study_plans
WHERE user_id = 42 AND status = 'ACTIVE'
ORDER BY created_at DESC;
-- 可命中索引并利用索引顺序完成排序
```""",
        "summary": [
            "B+ 树让等值、范围和排序查询都能高效执行。",
            "聚簇索引与二级索引的叶子内容不同。",
            "覆盖索引可以减少回表次数。",
        ],
        "key_points": [
            "InnoDB 使用 B+ 树组织索引",
            "聚簇索引叶子节点存放完整数据行",
            "二级索引叶子节点存放主键值",
            "覆盖索引可以避免回表",
        ],
        "quizzes": [
            {"q": "二级索引查询为什么可能需要回表？", "a": "二级索引叶子只存索引列与主键，查询其他列需按主键回到聚簇索引取数据。"},
            {"q": "覆盖索引的定义是什么？", "a": "查询所需列全部包含在索引中，无需回表即可返回结果。"},
        ],
    },
    {
        "key": "my-02",
        "title": "联合索引与最左前缀原则",
        "domain": "MySQL",
        "tags": ["MySQL", "联合索引", "优化"],
        "concept": "联合索引按列顺序构建。查询条件必须从最左列开始连续匹配，才能充分利用索引；跳过前缀列通常只能使用部分索引或无法使用索引。",
        "principles": [
            "范围条件会中断后续列在索引中的有序性。",
            "等值条件放在联合索引前部通常更有效。",
            "ORDER BY 的列顺序与索引顺序一致时可避免额外排序。",
            "使用 EXPLAIN 观察 key、key_len 与 Extra 判断命中情况。",
        ],
        "example": """```sql
CREATE INDEX idx_plan_user_status_date
ON study_plans (user_id, status, created_at);

-- 命中：等值 + 等值 + 排序
SELECT * FROM study_plans
WHERE user_id = 1 AND status = 'ACTIVE'
ORDER BY created_at DESC;

-- 无法使用该索引：缺少最左列 user_id
SELECT * FROM study_plans WHERE status = 'ACTIVE';
```""",
        "summary": [
            "联合索引的列顺序决定可用查询模式。",
            "最左前缀是最基本的命中规则。",
            "范围条件之后的列通常无法继续用于索引过滤。",
        ],
        "key_points": [
            "联合索引按定义列顺序生效",
            "查询需从最左列开始连续匹配",
            "范围条件会中断后续列的有序利用",
            "EXPLAIN 的 key_len 可判断使用了几列",
        ],
        "quizzes": [
            {"q": "联合索引 (a, b, c) 能否支持只查 b 的条件？", "a": "通常不能有效使用该索引，因为缺少最左前缀 a。"},
            {"q": "为什么范围条件后的列排序可能失效？", "a": "范围扫描后后续列在每个范围内有序，但全局不再保持索引顺序。"},
        ],
    },
    {
        "key": "my-03",
        "title": "事务隔离级别与 MVCC",
        "domain": "MySQL",
        "tags": ["MySQL", "事务", "MVCC"],
        "concept": "InnoDB 默认使用可重复读隔离级别，通过 MVCC 提供一致性读。每行记录包含事务版本信息，读取时根据 Read View 判断哪个版本可见。",
        "principles": [
            "读已提交与可重复读的核心差异是 Read View 的创建时机。",
            "MVCC 主要解决读写冲突，不加锁也能得到一致性快照。",
            "当前读（SELECT ... FOR UPDATE）会读取最新版本并加锁。",
            "长事务会阻止 undo 日志清理，导致版本链膨胀。",
        ],
        "table": "| 隔离级别 | 脏读 | 不可重复读 | 幻读 |\n|---|---|---|---|\n| 读未提交 | 可能 | 可能 | 可能 |\n| 读已提交 | 否 | 可能 | 可能 |\n| 可重复读 | 否 | 否 | InnoDB 基本避免 |\n| 串行化 | 否 | 否 | 否 |",
        "example": """```sql
-- 可重复读：同一事务内两次普通 SELECT 结果一致
START TRANSACTION;
SELECT balance FROM account WHERE id = 1;
SELECT balance FROM account WHERE id = 1;
COMMIT;

-- 当前读：读取最新已提交版本并加排他锁
SELECT balance FROM account WHERE id = 1 FOR UPDATE;
```""",
        "summary": [
            "MVCC 用版本链与 Read View 实现一致性读。",
            "普通 SELECT 是快照读，FOR UPDATE 是当前读。",
            "长事务会显著增加 undo 与版本链压力。",
        ],
        "key_points": [
            "InnoDB 默认隔离级别是可重复读",
            "MVCC 通过版本链与 Read View 实现快照读",
            "当前读会读取最新版本并加锁",
            "长事务会阻止 undo 日志清理",
        ],
        "quizzes": [
            {"q": "可重复读与读已提交的主要区别是什么？", "a": "Read View 的创建时机不同，可重复读在整个事务内复用同一视图。"},
            {"q": "为什么长事务会增加存储压力？", "a": "旧版本 undo 日志无法及时清理，版本链持续膨胀。"},
        ],
    },
    {
        "key": "my-04",
        "title": "行锁、间隙锁与死锁处理",
        "domain": "MySQL",
        "tags": ["MySQL", "锁", "死锁"],
        "concept": "InnoDB 支持行级锁。可重复读下，范围条件可能产生间隙锁，用于阻止其他事务在间隙中插入。多个事务以不同顺序申请锁时可能形成死锁。",
        "principles": [
            "行锁基于索引实现，未命中索引可能退化为大范围锁。",
            "间隙锁锁定索引记录之间的空隙，防止幻读。",
            "死锁发生时 InnoDB 会选择代价较小的事务回滚。",
            "统一加锁顺序、缩短事务、使用合适索引可降低死锁概率。",
        ],
        "example": """```sql
-- 事务 A
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 1;

-- 事务 B
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 2;

-- 若 A 再更新 id=2、B 再更新 id=1，就可能死锁
```""",
        "summary": [
            "行锁依赖索引，缺失索引会扩大锁定范围。",
            "间隙锁是可重复读下防止幻读的重要手段。",
            "死锁无法完全避免，但可以通过设计与重试降低影响。",
        ],
        "key_points": [
            "InnoDB 行锁基于索引实现",
            "间隙锁用于阻止间隙插入",
            "死锁时 InnoDB 自动回滚较小事务",
            "统一加锁顺序可降低死锁概率",
        ],
        "quizzes": [
            {"q": "为什么缺少索引的更新可能锁住更多行？", "a": "无法精确定位记录时会扫描并锁定更大范围，甚至接近表锁。"},
            {"q": "发生死锁后应用应该如何处理？", "a": "捕获死锁错误并按幂等逻辑有限次重试，同时排查加锁顺序。"},
        ],
    },
    {
        "key": "my-05",
        "title": "慢查询定位与 EXPLAIN 解读",
        "domain": "MySQL",
        "tags": ["MySQL", "慢查询", "EXPLAIN"],
        "concept": "慢查询日志记录超过阈值的 SQL。EXPLAIN 展示优化器选择的访问方式、使用索引、扫描行数与额外操作，是定位性能问题的主要工具。",
        "principles": [
            "type 从 const、ref、range 到 ALL 大致由好到差。",
            "rows 是估算扫描行数，数值越大越需要关注。",
            "Extra 中出现 Using filesort、Using temporary 通常意味着额外开销。",
            "Using index 表示覆盖索引，Using where 表示服务器层过滤。",
        ],
        "example": """```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;

EXPLAIN ANALYZE
SELECT t.id, t.content
FROM daily_tasks t
JOIN study_plans p ON p.id = t.plan_id
WHERE p.user_id = 42 AND t.task_date = '2026-11-28';
```""",
        "summary": [
            "先定位慢 SQL，再用 EXPLAIN 分析访问路径。",
            "关注 type、rows、key 与 Extra 四个关键字段。",
            "优化手段包括补索引、改写 SQL、减少回表与排序。",
        ],
        "key_points": [
            "慢查询日志用于发现高耗时 SQL",
            "EXPLAIN 的 type 反映访问方式",
            "rows 是优化器估算的扫描行数",
            "Using filesort 与 Using temporary 需要关注",
        ],
        "quizzes": [
            {"q": "EXPLAIN 中 type=ALL 表示什么？", "a": "全表扫描，通常是性能较差的访问方式。"},
            {"q": "Extra 中 Using index 的含义是什么？", "a": "查询使用了覆盖索引，无需回表读取数据行。"},
        ],
    },
    {
        "key": "my-06",
        "title": "数据库范式、反范式与表设计",
        "domain": "MySQL",
        "tags": ["MySQL", "范式", "表设计"],
        "concept": "范式化通过消除冗余保证一致性，反范式通过适度冗余换取查询性能。实际设计需要在一致性、写入复杂度和读取效率之间权衡。",
        "principles": [
            "第一范式要求字段原子性，第二范式消除部分依赖，第三范式消除传递依赖。",
            "高频联表且读多写少的场景可以考虑冗余快照字段。",
            "冗余字段必须明确维护责任与更新时机。",
            "金额、数量等关键字段应选择精确类型并加约束。",
        ],
        "example": """```sql
-- 反范式示例：练习记录保存笔记标题快照
CREATE TABLE practice_records (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  note_id BIGINT UNSIGNED NULL,
  note_title_snapshot VARCHAR(255) NOT NULL,
  score DECIMAL(5,2) NOT NULL
);
-- 即使原笔记改名或删除，历史记录仍能展示当时的标题
```""",
        "summary": [
            "范式化优先保证一致性，反范式优先保证读取效率。",
            "冗余字段要有清晰的同步策略。",
            "历史快照字段是常见的合理反范式。",
        ],
        "key_points": [
            "范式化减少冗余并保证一致性",
            "反范式用冗余换取查询性能",
            "冗余字段需要明确维护责任",
            "历史快照是合理的反范式场景",
        ],
        "quizzes": [
            {"q": "第三范式主要消除什么依赖？", "a": "消除非主属性对主键的传递依赖。"},
            {"q": "为什么历史记录常保存标题快照？", "a": "原记录可能改名或删除，快照能保证历史展示稳定。"},
        ],
    },
    {
        "key": "my-07",
        "title": "深分页、计数与查询稳定性",
        "domain": "MySQL",
        "tags": ["MySQL", "分页", "性能"],
        "concept": "LIMIT offset, size 在 offset 很大时需要扫描并丢弃大量行，导致深分页变慢。基于游标（上一页最后一条记录的排序键）分页可以稳定利用索引。",
        "principles": [
            "深分页应尽量使用 WHERE 排序键 > 上一页最后值 的方式。",
            "COUNT(*) 在大表上成本高，可考虑近似统计或缓存。",
            "分页必须使用确定性排序，否则可能重复或遗漏记录。",
            "排序键应包含唯一列作为最终 tie-breaker。",
        ],
        "example": """```sql
-- 不推荐：offset 很大
SELECT id, title FROM knowledge_notes
ORDER BY created_at DESC, id DESC
LIMIT 100000, 20;

-- 推荐：游标分页
SELECT id, title FROM knowledge_notes
WHERE (created_at, id) < ('2026-11-01 10:00:00', 12345)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```""",
        "summary": [
            "深分页的核心问题是扫描并丢弃大量行。",
            "游标分页依赖稳定且唯一的排序键。",
            "计数应与列表查询解耦，避免每次请求都全量统计。",
        ],
        "key_points": [
            "LIMIT 大 offset 会扫描并丢弃大量行",
            "游标分页基于上一页最后一条记录",
            "分页排序必须确定且唯一",
            "COUNT 大表查询成本高可缓存",
        ],
        "quizzes": [
            {"q": "深分页为什么慢？", "a": "数据库需要先扫描 offset 行再丢弃，偏移越大成本越高。"},
            {"q": "游标分页依赖什么条件？", "a": "稳定且唯一的排序键，通常由排序列加主键组成。"},
        ],
    },
    {
        "key": "rd-01",
        "title": "Redis 数据结构与业务选型",
        "domain": "Redis",
        "tags": ["Redis", "数据结构", "选型"],
        "concept": "Redis 提供 String、Hash、List、Set、ZSet 等结构。选型应围绕访问模式：计数用 String，对象字段用 Hash，排行榜用 ZSet，去重用 Set。",
        "principles": [
            "String 适合缓存、计数和分布式锁标记。",
            "Hash 适合存储对象的多个字段，减少键数量。",
            "ZSet 按分数排序，适合排行榜与延迟队列。",
            "大 Key 和高频全量操作会阻塞单线程事件循环。",
        ],
        "table": "| 结构 | 典型用途 | 注意点 |\n|---|---|---|\n| String | 缓存、计数 | 大 value 拆分 |\n| Hash | 对象字段 | 避免超大 Hash |\n| List | 队列、时间线 | 控制长度 |\n| ZSet | 排行榜 | 分数设计要稳定 |",
        "example": """```text
SET plan:42:cache "{...}" EX 300
HSET user:42 name "REED" role "USER"
ZADD leaderboard 1280 "user:42"
SADD task:done:2026-11-28 1001 1002
```""",
        "summary": [
            "数据结构选择由访问模式决定。",
            "避免大 Key 与 O(N) 全量命令。",
            "过期时间应结合业务一致性要求设置。",
        ],
        "key_points": [
            "String 适合缓存与计数",
            "Hash 适合存储对象字段",
            "ZSet 适合排行榜与延迟队列",
            "大 Key 会阻塞 Redis 单线程",
        ],
        "quizzes": [
            {"q": "排行榜最适合使用哪种 Redis 结构？", "a": "ZSet，可按分数排序并范围查询。"},
            {"q": "为什么需要避免大 Key？", "a": "大 Key 的读写与删除会长时间占用单线程事件循环，影响其他请求。"},
        ],
    },
    {
        "key": "rd-02",
        "title": "缓存穿透、击穿与雪崩",
        "domain": "Redis",
        "tags": ["Redis", "缓存", "高可用"],
        "concept": "穿透是查询不存在的数据绕过缓存；击穿是热点 Key 失效瞬间大量请求打到数据库；雪崩是大量 Key 同时失效或 Redis 故障导致数据库压力骤增。",
        "principles": [
            "穿透可用空值缓存、布隆过滤器或参数校验缓解。",
            "击穿可用互斥锁或逻辑过期保证只有一个请求回源。",
            "雪崩应给过期时间加随机抖动，并准备降级与限流。",
            "缓存一致性策略需要明确更新顺序与失败补偿。",
        ],
        "example": """```python
def get_plan(plan_id):
    key = f"plan:{plan_id}"
    cached = redis.get(key)
    if cached is not None:
        return json.loads(cached)

    lock = redis.set(f"lock:{key}", "1", nx=True, ex=5)
    if not lock:
        time.sleep(0.05)
        return get_plan(plan_id)

    try:
        data = db.load_plan(plan_id)
        value = json.dumps(data) if data else "__NULL__"
        redis.set(key, value, ex=300 + random.randint(0, 60))
        return data
    finally:
        redis.delete(f"lock:{key}")
```""",
        "summary": [
            "三种缓存问题的触发条件不同，治理手段也不同。",
            "互斥回源与逻辑过期是解决击穿的常用方案。",
            "随机过期时间与降级策略可降低雪崩影响。",
        ],
        "key_points": [
            "缓存穿透是查询不存在的数据",
            "缓存击穿是热点 Key 失效",
            "缓存雪崩是大量 Key 同时失效",
            "随机过期时间可缓解雪崩",
        ],
        "quizzes": [
            {"q": "空值缓存如何缓解缓存穿透？", "a": "把不存在的结果也短暂缓存，避免相同请求反复打到数据库。"},
            {"q": "互斥锁解决缓存击穿的原理是什么？", "a": "只允许一个请求回源重建缓存，其余请求等待或读取旧值。"},
        ],
    },
    {
        "key": "rd-03",
        "title": "Redis 分布式锁：SET NX PX 与 Lua 释放",
        "domain": "Redis",
        "tags": ["Redis", "分布式锁", "Lua"],
        "concept": "分布式锁需要满足互斥、防死锁和可安全释放。Redis 常用 SET key value NX PX ttl 获取锁，value 使用唯一令牌，释放时用 Lua 比较令牌后删除。",
        "principles": [
            "必须同时设置 NX 与过期时间，避免死锁。",
            "释放锁必须校验持有者令牌，防止误删他人锁。",
            "业务执行时间可能超过锁过期时间，需要续期机制。",
            "单节点 Redis 锁在主从切换时存在理论上的互斥风险。",
        ],
        "example": """```lua
-- release_lock.lua
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
```

```python
token = uuid.uuid4().hex
ok = redis.set("lock:plan:42", token, nx=True, px=30000)
if ok:
    try:
        do_work()
    finally:
        redis.eval(RELEASE_LUA, 1, "lock:plan:42", token)
```""",
        "summary": [
            "NX 保证互斥，PX 防止死锁。",
            "唯一令牌与 Lua 保证释放安全。",
            "长任务需要续期，单节点锁并非强一致。",
        ],
        "key_points": [
            "SET NX PX 同时保证互斥与防死锁",
            "锁 value 应使用唯一令牌",
            "Lua 脚本保证比较与删除的原子性",
            "单节点 Redis 锁存在主从切换风险",
        ],
        "quizzes": [
            {"q": "为什么释放锁需要 Lua 脚本？", "a": "把比较令牌与删除操作放在同一原子操作中，避免误删他人锁。"},
            {"q": "只设置 NX 不设置过期时间会有什么风险？", "a": "持有者崩溃后锁永远不会释放，形成死锁。"},
        ],
    },
]