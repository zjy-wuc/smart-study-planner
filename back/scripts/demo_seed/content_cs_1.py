"""笔记内容 B1：Java 与数据结构基础（13 篇）。"""

NOTES = [
    {
        "key": "java-01",
        "title": "JVM 内存区域与对象创建过程",
        "domain": "Java",
        "tags": ["Java", "JVM", "内存模型"],
        "concept": "JVM 运行时数据区包括程序计数器、虚拟机栈、本地方法栈、堆和方法区。对象主要分配在堆上，栈帧保存局部变量与引用。",
        "principles": [
            "程序计数器是线程私有的，记录当前字节码位置。",
            "虚拟机栈随线程创建，栈帧包含局部变量表、操作数栈等。",
            "堆是垃圾回收的主要区域，按代或分区管理。",
            "对象创建经历类加载检查、分配内存、零值初始化、设置对象头和执行构造方法。",
        ],
        "example": """```java
public class ObjectCreation {
    public static void main(String[] args) {
        User user = new User("REED");
        System.out.println(user.getName());
    }
}
// 引用 user 在栈帧中，User 实例在堆中
```""",
        "summary": [
            "线程私有区域与线程共享区域职责不同。",
            "对象分配与回收主要发生在堆。",
            "理解对象创建步骤有助于分析内存与性能问题。",
        ],
        "key_points": [
            "程序计数器是线程私有的",
            "虚拟机栈保存栈帧与局部变量",
            "堆是垃圾回收的主要区域",
            "对象创建包含分配内存与初始化",
        ],
        "quizzes": [
            {"q": "对象引用和对象实例分别存放在哪里？", "a": "引用通常在线程栈的局部变量表中，对象实例通常分配在堆上。"},
            {"q": "程序计数器为什么是线程私有的？", "a": "每个线程需要独立记录自己当前执行的字节码位置。"},
        ],
    },
    {
        "key": "java-02",
        "title": "垃圾回收器与常见调优思路",
        "domain": "Java",
        "tags": ["Java", "GC", "调优"],
        "concept": "垃圾回收通过可达性分析判断对象是否存活。不同收集器在吞吐量、停顿时间和内存占用之间取舍，例如 G1 以可预测停顿为目标。",
        "principles": [
            "可达性分析从 GC Roots 出发，无法到达的对象可被回收。",
            "Minor GC 清理新生代，Full GC 通常停顿更长。",
            "G1 将堆划分为 Region，按收益优先回收。",
            "调优应先观察 GC 日志与停顿指标，再调整堆大小和收集器参数。",
        ],
        "table": "| 收集器 | 特点 | 适用场景 |\n|---|---|---|\n| Serial | 单线程、简单 | 小堆 |\n| Parallel | 吞吐优先 | 批处理 |\n| G1 | 可预测停顿 | 中大堆服务 |\n| ZGC | 超低停顿 | 大堆低延迟 |",
        "example": """```bash
java -Xms4g -Xmx4g \\
     -XX:+UseG1GC \\
     -XX:MaxGCPauseMillis=200 \\
     -Xlog:gc*:file=gc.log \\
     -jar app.jar
```""",
        "summary": [
            "GC 的核心是判断对象是否仍可达。",
            "收集器选择取决于延迟与吞吐目标。",
            "调优要以日志和监控数据为依据。",
        ],
        "key_points": [
            "可达性分析从 GC Roots 出发",
            "Minor GC 与 Full GC 停顿不同",
            "G1 按 Region 分区回收",
            "GC 调优应基于日志与监控",
        ],
        "quizzes": [
            {"q": "可达性分析的起点是什么？", "a": "GC Roots，例如栈中引用、静态变量和常量等。"},
            {"q": "G1 收集器的主要设计目标是什么？", "a": "在可控停顿时间内优先回收收益高的 Region。"},
        ],
    },
    {
        "key": "java-03",
        "title": "ArrayList、LinkedList 与 HashMap 的取舍",
        "domain": "Java",
        "tags": ["Java", "集合", "HashMap"],
        "concept": "ArrayList 基于动态数组，随机访问快；LinkedList 基于双向链表，头尾插入删除快但随机访问慢。HashMap 使用数组加链表/红黑树解决哈希冲突。",
        "principles": [
            "ArrayList 扩容会复制数组，应尽量预估容量。",
            "LinkedList 额外维护节点指针，内存开销更大。",
            "HashMap 默认负载因子 0.75，冲突严重时链表转红黑树。",
            "作为 HashMap 键的对象必须正确实现 equals 与 hashCode。",
        ],
        "table": "| 操作 | ArrayList | LinkedList |\n|---|---|---|\n| 随机访问 | O(1) | O(n) |\n| 尾部追加 | 摊还 O(1) | O(1) |\n| 中间插入 | O(n) | O(n)（定位后 O(1)） |",
        "example": """```java
Map<String, Integer> counts = new HashMap<>();
for (String word : words) {
    counts.merge(word, 1, Integer::sum);
}

// 预估容量，减少扩容
List<String> names = new ArrayList<>(1024);
```""",
        "summary": [
            "集合选型要看访问与修改模式。",
            "HashMap 的正确性依赖键的 equals 与 hashCode。",
            "容量预估能减少扩容带来的复制开销。",
        ],
        "key_points": [
            "ArrayList 随机访问快",
            "LinkedList 头尾插入删除快",
            "HashMap 使用链表与红黑树处理冲突",
            "键对象必须正确实现 equals 与 hashCode",
        ],
        "quizzes": [
            {"q": "ArrayList 频繁扩容的代价是什么？", "a": "需要申请更大数组并复制原有元素，带来时间与内存开销。"},
            {"q": "HashMap 对键对象有什么要求？", "a": "必须一致地实现 equals 与 hashCode，否则无法正确查找。"},
        ],
    },
    {
        "key": "java-04",
        "title": "synchronized、volatile 与 CAS",
        "domain": "Java",
        "tags": ["Java", "并发", "CAS"],
        "concept": "synchronized 提供互斥与可见性；volatile 保证可见性和有序性但不保证原子性；CAS 通过比较并交换实现无锁原子更新，是原子类的基础。",
        "principles": [
            "synchronized 锁对象，进入与退出时建立 happens-before 关系。",
            "volatile 禁止指令重排并强制读写主内存。",
            "i++ 不是原子操作，volatile 无法解决竞态。",
            "CAS 在高竞争下可能自旋过多，可用 LongAdder 等分散热点。",
        ],
        "example": """```java
private volatile boolean running = true;
private final AtomicInteger counter = new AtomicInteger();

public void stop() {
    running = false;
}

public void increment() {
    counter.incrementAndGet();   // 基于 CAS
}
```""",
        "summary": [
            "volatile 解决可见性，不解决复合操作原子性。",
            "synchronized 简单可靠，但要注意锁粒度。",
            "CAS 适合低到中等竞争的原子更新。",
        ],
        "key_points": [
            "synchronized 同时保证互斥与可见性",
            "volatile 保证可见性但不保证原子性",
            "i++ 不是原子操作",
            "CAS 是无锁原子更新的基础",
        ],
        "quizzes": [
            {"q": "volatile 能保证 i++ 的线程安全吗？", "a": "不能，i++ 包含读取、计算和写回三个步骤，不是原子操作。"},
            {"q": "synchronized 的锁对象是什么？", "a": "实例方法锁当前实例，静态方法锁 Class 对象，代码块锁指定对象。"},
        ],
    },
    {
        "key": "java-05",
        "title": "线程池参数与拒绝策略",
        "domain": "Java",
        "tags": ["Java", "线程池", "并发"],
        "concept": "ThreadPoolExecutor 由核心线程数、最大线程数、空闲存活时间、任务队列和拒绝策略组成。任务先填核心线程，再入队，队列满后扩容到最大线程，最后触发拒绝策略。",
        "principles": [
            "核心线程数决定常态并发能力。",
            "无界队列会让最大线程数失效，可能导致内存膨胀。",
            "拒绝策略应结合业务选择抛异常、调用者执行或丢弃。",
            "线程池应显式命名并监控队列长度与活跃线程数。",
        ],
        "example": """```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    4, 8, 60, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(200),
    new NamedThreadFactory("study-worker"),
    new ThreadPoolExecutor.CallerRunsPolicy()
);
```""",
        "summary": [
            "线程池的扩容顺序是核心线程、队列、最大线程。",
            "队列类型直接影响拒绝行为。",
            "监控与命名是生产环境的基本要求。",
        ],
        "key_points": [
            "任务先使用核心线程",
            "队列满后才扩容到最大线程",
            "无界队列会使最大线程数失效",
            "拒绝策略应结合业务选择",
        ],
        "quizzes": [
            {"q": "线程池在什么情况下创建超过核心线程数的线程？", "a": "核心线程都在忙且任务队列已满时，才扩容到最大线程数。"},
            {"q": "CallerRunsPolicy 的行为是什么？", "a": "由提交任务的线程直接执行该任务，形成背压。"},
        ],
    },
    {
        "key": "java-06",
        "title": "Spring Boot 分层与依赖注入",
        "domain": "Java",
        "tags": ["Java", "Spring Boot", "分层"],
        "concept": "Spring Boot 通常分为 Controller、Service、Repository 三层。Controller 处理协议，Service 编排业务与事务，Repository 负责数据访问。依赖注入降低层间耦合。",
        "principles": [
            "Controller 不直接写 SQL，也不承载核心业务规则。",
            "Service 是事务边界与业务规则的主要位置。",
            "构造器注入优于字段注入，便于测试与保证不可变。",
            "全局异常处理统一转换业务异常为 HTTP 响应。",
        ],
        "example": """```java
@RestController
@RequestMapping("/api/plans")
public class PlanController {
    private final PlanService planService;

    public PlanController(PlanService planService) {
        this.planService = planService;
    }

    @GetMapping("/{id}")
    public PlanResponse get(@PathVariable Long id) {
        return planService.get(id);
    }
}
```""",
        "summary": [
            "分层让协议、业务与数据访问职责清晰。",
            "事务应放在 Service 层。",
            "构造器注入提升可测试性与不可变性。",
        ],
        "key_points": [
            "Controller 负责协议转换",
            "Service 承载业务规则与事务",
            "Repository 负责数据访问",
            "构造器注入优于字段注入",
        ],
        "quizzes": [
            {"q": "为什么事务边界通常放在 Service 层？", "a": "Service 编排多个数据操作，能保证业务操作的原子性。"},
            {"q": "构造器注入的主要优点是什么？", "a": "依赖显式且可设为 final，便于测试并避免循环依赖隐藏。"},
        ],
    },
    {
        "key": "java-07",
        "title": "JPA、MyBatis 与事务传播",
        "domain": "Java",
        "tags": ["Java", "JPA", "MyBatis"],
        "concept": "JPA 以对象模型为中心，适合标准 CRUD；MyBatis 以 SQL 为中心，适合复杂查询与精细优化。事务传播定义方法被另一个事务方法调用时如何加入或新建事务。",
        "principles": [
            "REQUIRED 是默认传播行为，有事务则加入，无事务则新建。",
            "REQUIRES_NEW 会挂起当前事务并新建独立事务。",
            "同类内部方法调用不会经过代理，事务注解可能失效。",
            "只读事务可提示数据库优化，但不能替代业务一致性设计。",
        ],
        "example": """```java
@Service
public class PlanService {
    @Transactional
    public void activate(Long planId) {
        Plan plan = repo.findById(planId).orElseThrow();
        plan.activate();
        auditService.record(planId);   // 加入当前事务
    }
}
```""",
        "summary": [
            "JPA 与 MyBatis 可以按查询复杂度混合使用。",
            "事务传播决定嵌套调用的事务边界。",
            "注意代理机制导致的事务失效问题。",
        ],
        "key_points": [
            "JPA 面向对象模型",
            "MyBatis 面向 SQL",
            "REQUIRED 是默认事务传播行为",
            "同类内部调用可能导致事务注解失效",
        ],
        "quizzes": [
            {"q": "REQUIRES_NEW 与 REQUIRED 的区别是什么？", "a": "REQUIRES_NEW 会挂起当前事务并新建独立事务，REQUIRED 则加入已有事务。"},
            {"q": "为什么同类内部调用可能导致 @Transactional 失效？", "a": "内部调用不经过 Spring 代理，事务增强逻辑没有机会执行。"},
        ],
    },
    {
        "key": "java-08",
        "title": "Java 异常体系与错误处理原则",
        "domain": "Java",
        "tags": ["Java", "异常", "最佳实践"],
        "concept": "Throwable 分为 Error 与 Exception。Exception 又分受检异常与运行时异常。业务代码应抛出语义明确的异常，并在边界统一转换为响应。",
        "principles": [
            "不要捕获后忽略异常，也不要捕获过宽的 Exception。",
            "受检异常适合调用方必须处理的 recoverable 情况。",
            "运行时异常适合编程错误或无法恢复的业务拒绝。",
            "异常链应保留 cause，便于定位根因。",
        ],
        "example": """```java
public class PlanNotFoundException extends RuntimeException {
    public PlanNotFoundException(Long id) {
        super("plan not found: " + id);
    }
}

@ExceptionHandler(PlanNotFoundException.class)
public ResponseEntity<ErrorBody> handle(PlanNotFoundException exc) {
    return ResponseEntity.status(404)
        .body(new ErrorBody("PLAN_NOT_FOUND", exc.getMessage()));
}
```""",
        "summary": [
            "异常类型应表达业务语义。",
            "保留 cause 是排查问题的关键。",
            "统一异常处理让 API 错误契约稳定。",
        ],
        "key_points": [
            "Throwable 分为 Error 与 Exception",
            "受检异常要求调用方显式处理",
            "运行时异常适合业务拒绝",
            "异常链应保留原始 cause",
        ],
        "quizzes": [
            {"q": "捕获异常后只打印日志并继续执行有什么风险？", "a": "可能掩盖数据不一致或失败状态，导致更难排查的问题。"},
            {"q": "为什么要保留异常 cause？", "a": "可以追溯根因与完整调用链，便于定位问题。"},
        ],
    },
    {
        "key": "dsa-01",
        "title": "时间复杂度、空间复杂度与摊还分析",
        "domain": "数据结构与算法",
        "tags": ["算法", "复杂度", "摊还分析"],
        "concept": "复杂度描述输入规模增长时时间或空间的增长趋势。摊还分析把偶发的高成本操作分摊到一系列操作上，例如动态数组扩容的平均代价是 O(1)。",
        "principles": [
            "只保留最高阶项并忽略常数系数。",
            "最坏、平均与摊还复杂度回答的问题不同。",
            "空间复杂度包括输入之外的额外空间。",
            "递归算法要考虑调用栈空间。",
        ],
        "table": "| 复杂度 | 增长趋势 | 示例 |\n|---|---|---|\n| O(1) | 常数 | 哈希查找 |\n| O(log n) | 对数 | 二分查找 |\n| O(n) | 线性 | 一次遍历 |\n| O(n log n) | 线性对数 | 归并排序 |\n| O(n^2) | 平方 | 双重循环 |",
        "example": """```python
# 摊还 O(1)：动态数组追加
values = []
for i in range(n):
    values.append(i)   # 偶发扩容，但总代价与 n 成正比

# O(n log n)：归并排序
def merge_sort(xs):
    if len(xs) <= 1:
        return xs
    mid = len(xs) // 2
    return merge(merge_sort(xs[:mid]), merge_sort(xs[mid:]))
```""",
        "summary": [
            "复杂度关注增长趋势而非具体耗时。",
            "摊还分析适合解释偶发扩容等场景。",
            "递归必须把调用栈计入空间成本。",
        ],
        "key_points": [
            "复杂度忽略常数与低阶项",
            "摊还分析分摊偶发高成本操作",
            "空间复杂度指额外空间",
            "递归要考虑调用栈空间",
        ],
        "quizzes": [
            {"q": "动态数组 append 的摊还复杂度为什么是 O(1)？", "a": "扩容成本按倍数增长，总扩容代价与元素总数成正比，平均到每次追加为常数。"},
            {"q": "归并排序的时间复杂度是多少？", "a": "O(n log n)，每层合并 O(n)，共 log n 层。"},
        ],
    },
    {
        "key": "dsa-02",
        "title": "数组、链表与双指针技巧",
        "domain": "数据结构与算法",
        "tags": ["算法", "数组", "双指针"],
        "concept": "数组支持 O(1) 随机访问但插入删除成本高；链表插入删除灵活但访问需要遍历。双指针通过在序列上维护两个位置，把许多 O(n^2) 问题降为 O(n)。",
        "principles": [
            "有序数组中的两数之和可用左右指针夹逼。",
            "快慢指针可用于链表判环与找中点。",
            "滑动窗口本质是维护一个满足条件的区间。",
            "原地修改数组常用读写指针。",
        ],
        "example": """```python
def two_sum_sorted(nums, target):
    left, right = 0, len(nums) - 1
    while left < right:
        total = nums[left] + nums[right]
        if total == target:
            return [left, right]
        if total < target:
            left += 1
        else:
            right -= 1
    return []
```""",
        "summary": [
            "数组与链表的取舍取决于访问和修改模式。",
            "双指针把嵌套扫描优化为线性扫描。",
            "滑动窗口适合连续子数组/子串问题。",
        ],
        "key_points": [
            "数组随机访问 O(1)",
            "链表插入删除灵活但访问 O(n)",
            "左右指针适合有序数组夹逼",
            "快慢指针可判环与找中点",
        ],
        "quizzes": [
            {"q": "有序数组两数之和为什么可以用左右指针？", "a": "和偏小时左指针右移增大和，和偏大时右指针左移减小和，每次都能排除一行或一列。"},
            {"q": "快慢指针如何判断链表有环？", "a": "快指针每次走两步、慢指针一步，若有环二者最终相遇。"},
        ],
    },
    {
        "key": "dsa-03",
        "title": "栈、队列与单调栈",
        "domain": "数据结构与算法",
        "tags": ["算法", "栈", "单调栈"],
        "concept": "栈后进先出，队列先进先出。单调栈在栈内维护单调顺序，用于高效寻找每个元素左侧或右侧第一个更大/更小元素。",
        "principles": [
            "括号匹配、表达式求值、函数调用都依赖栈。",
            "BFS 使用队列逐层扩展。",
            "单调栈中每个元素最多入栈出栈一次，整体 O(n)。",
            "单调队列常用于滑动窗口最大值。",
        ],
        "example": """```python
def next_greater(nums):
    result = [-1] * len(nums)
    stack = []
    for i, value in enumerate(nums):
        while stack and nums[stack[-1]] < value:
            result[stack.pop()] = value
        stack.append(i)
    return result

print(next_greater([2, 1, 3]))   # [3, 3, -1]
```""",
        "summary": [
            "栈与队列是许多算法的基础容器。",
            "单调栈把寻找下一个更大元素降到 O(n)。",
            "单调队列适合固定窗口的极值问题。",
        ],
        "key_points": [
            "栈是后进先出",
            "队列是先进先出",
            "单调栈寻找下一个更大或更小元素",
            "单调队列用于滑动窗口最大值",
        ],
        "quizzes": [
            {"q": "单调栈为什么能做到 O(n)？", "a": "每个元素最多入栈一次、出栈一次，总操作次数与 n 成正比。"},
            {"q": "BFS 为什么使用队列？", "a": "队列保证按发现顺序逐层处理节点。"},
        ],
    },
    {
        "key": "dsa-04",
        "title": "哈希表、冲突处理与工程应用",
        "domain": "数据结构与算法",
        "tags": ["算法", "哈希表", "冲突"],
        "concept": "哈希表通过哈希函数把键映射到桶，平均 O(1) 完成查找。不同键可能映射到同一桶，需要链地址法或开放寻址法处理冲突。",
        "principles": [
            "负载因子过高会增加冲突，通常需要扩容。",
            "链地址法实现简单，开放寻址法缓存局部性更好。",
            "哈希函数应均匀分布并保持稳定。",
            "哈希表不保证顺序，需要顺序时使用有序结构。",
        ],
        "example": """```python
def first_unique(s):
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    for ch in s:
        if counts[ch] == 1:
            return ch
    return None
```""",
        "summary": [
            "哈希表以空间换时间，平均查找 O(1)。",
            "冲突处理与负载因子决定实际性能。",
            "需要顺序或范围查询时应选择其他结构。",
        ],
        "key_points": [
            "哈希表平均查找复杂度 O(1)",
            "冲突可用链地址法或开放寻址法",
            "负载因子过高会触发扩容",
            "哈希表不保证键的顺序",
        ],
        "quizzes": [
            {"q": "哈希表为什么需要扩容？", "a": "元素增多会提高负载因子与冲突概率，扩容可恢复较低冲突率。"},
            {"q": "链地址法如何处理冲突？", "a": "同一桶中的冲突元素用链表或红黑树串联存储。"},
        ],
    },
    {
        "key": "dsa-05",
        "title": "二叉树遍历与递归思维",
        "domain": "数据结构与算法",
        "tags": ["算法", "二叉树", "递归"],
        "concept": "二叉树每个节点最多有两个子节点。前序、中序、后序遍历的区别在于访问根节点的时机；层序遍历使用队列。递归把树问题分解为左右子树问题。",
        "principles": [
            "前序：根左右；中序：左根右；后序：左右根。",
            "二叉搜索树的中序遍历得到有序序列。",
            "递归终止条件通常是节点为空。",
            "深度过大时递归可能导致栈溢出，可改用显式栈。",
        ],
        "example": """```python
def inorder(node):
    if node is None:
        return []
    return inorder(node.left) + [node.value] + inorder(node.right)

def max_depth(node):
    if node is None:
        return 0
    return 1 + max(max_depth(node.left), max_depth(node.right))
```""",
        "summary": [
            "遍历顺序由访问根的时机决定。",
            "递归解法的关键是定义子问题与终止条件。",
            "中序遍历是二叉搜索树的重要性质。",
        ],
        "key_points": [
            "前序中序后序的区别是访问根的顺序",
            "层序遍历使用队列",
            "二叉搜索树中序遍历有序",
            "递归需要明确终止条件",
        ],
        "quizzes": [
            {"q": "二叉搜索树的中序遍历有什么性质？", "a": "遍历结果严格递增（或非递减，取决于是否允许重复）。"},
            {"q": "层序遍历使用什么数据结构？", "a": "队列，按层依次取出节点并加入其子节点。"},
        ],
    },
]