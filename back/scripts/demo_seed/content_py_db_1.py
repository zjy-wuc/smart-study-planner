"""笔记内容 A1：Python 基础/进阶与 FastAPI 入门（13 篇）。"""

NOTES = [
    {
        "key": "py-01",
        "title": "Python 变量、对象与引用语义",
        "domain": "Python",
        "tags": ["Python", "内存模型", "引用"],
        "concept": "Python 的变量不是存放值的盒子，而是绑定到对象上的名字。执行 a = [1, 2] 时，解释器先创建列表对象，再让名字 a 指向它；b = a 只是新增一个指向同一对象的引用。",
        "principles": [
            "赋值不复制对象，只改变名字与对象之间的绑定关系。",
            "不可变对象（int、str、tuple）重新赋值会产生新对象，可变对象（list、dict、set）可以原地修改。",
            "== 比较值是否相等，is 比较是否为同一对象；判断 None 应使用 is None。",
            "函数参数按对象引用传递，修改可变参数会影响调用方。",
        ],
        "table": "| 操作 | 是否新建对象 | 是否影响原对象 |\n|---|---|---|\n| a = b | 否 | 否 |\n| a.append(x) | 否 | 是 |\n| a = a + [x] | 是 | 否 |\n| copy.copy(a) | 是（浅拷贝） | 否 |",
        "example": """```python
a = [1, 2]
b = a
b.append(3)
print(a)          # [1, 2, 3]，a 与 b 指向同一列表
print(a is b)     # True

c = a[:]          # 浅拷贝，新列表
c.append(4)
print(a)          # [1, 2, 3]，原列表不受影响
```""",
        "summary": [
            "变量是名字，对象才是数据本体。",
            "区分可变对象与不可变对象，是理解 Python 行为的关键。",
            "需要独立副本时显式使用切片、copy 或深拷贝。",
        ],
        "key_points": [
            "变量是指向对象的引用而不是值容器",
            "可变对象原地修改会同步影响所有引用",
            "is 比较身份而 == 比较值",
            "函数参数传递的是对象引用",
        ],
        "quizzes": [
            {"q": "为什么修改 b 会同时改变 a？", "a": "因为 a 与 b 指向同一个可变对象，修改对象本身而不是重新绑定名字。"},
            {"q": "判断变量是否为 None 应使用哪个运算符？", "a": "应使用 is None，避免自定义 __eq__ 带来的歧义。"},
        ],
    },
    {
        "key": "py-02",
        "title": "Python 可变对象、深浅拷贝与默认参数陷阱",
        "domain": "Python",
        "tags": ["Python", "拷贝", "默认参数"],
        "concept": "浅拷贝只复制最外层容器，内部元素仍是共享引用；深拷贝递归复制所有层级。函数默认参数在定义时求值一次，若默认值是可变对象，就会在多次调用之间共享状态。",
        "principles": [
            "copy.copy 与切片是浅拷贝，copy.deepcopy 是深拷贝。",
            "嵌套列表、字典是浅拷贝陷阱的高发场景。",
            "默认参数不要使用 []、{} 等可变对象，应使用 None 占位后在函数体内创建。",
            "不可变对象作为默认参数没有共享状态问题。",
        ],
        "example": """```python
import copy

def add_item(item, bucket=None):
    bucket = [] if bucket is None else bucket
    bucket.append(item)
    return bucket

nested = [[1], [2]]
shallow = copy.copy(nested)
shallow[0].append(9)
print(nested)     # [[1, 9], [2]]，内层仍共享

deep = copy.deepcopy(nested)
deep[0].append(7)
print(nested)     # 不受影响
```""",
        "summary": [
            "浅拷贝复制容器结构，深拷贝复制整棵对象图。",
            "可变默认参数会把上一次调用的状态带入下一次调用。",
            "用 None 作为默认值并在函数体内初始化，是标准写法。",
        ],
        "key_points": [
            "浅拷贝只复制最外层容器",
            "深拷贝递归复制嵌套对象",
            "可变默认参数会在调用间共享状态",
            "默认参数应使用 None 占位",
        ],
        "quizzes": [
            {"q": "浅拷贝嵌套列表后修改内层元素，原列表会变化吗？", "a": "会，因为内层元素仍是同一个对象引用。"},
            {"q": "为什么不建议用空列表作为默认参数？", "a": "默认值只在定义时创建一次，多次调用会共享同一个列表。"},
        ],
    },
    {
        "key": "py-03",
        "title": "列表推导式、生成器表达式与惰性求值",
        "domain": "Python",
        "tags": ["Python", "推导式", "生成器"],
        "concept": "列表推导式会立即构建完整列表；生成器表达式返回迭代器，按需计算，适合大数据流。两者都能把过滤与映射写在一行表达式里，但内存行为完全不同。",
        "principles": [
            "列表推导式 [f(x) for x in xs if cond] 立即分配内存。",
            "生成器表达式 (f(x) for x in xs) 惰性求值，只能迭代一次。",
            "嵌套推导式可读性差，复杂逻辑应改写成普通循环。",
            "sum、any、all 等聚合函数可以直接消费生成器，避免中间列表。",
        ],
        "example": """```python
squares = [x * x for x in range(10) if x % 2 == 0]
print(squares)                 # [0, 4, 16, 36, 64]

total = sum(x * x for x in range(10) if x % 2 == 0)
print(total)                   # 120，不创建中间列表

gen = (x for x in range(3))
print(list(gen))               # [0, 1, 2]
print(list(gen))               # []，生成器只能消费一次
```""",
        "summary": [
            "推导式适合短小、无副作用的转换。",
            "生成器表达式降低内存占用，但只能迭代一次。",
            "可读性优先，复杂条件不要强行塞进推导式。",
        ],
        "key_points": [
            "列表推导式立即构建列表",
            "生成器表达式惰性求值且只能迭代一次",
            "聚合函数可直接消费生成器",
            "复杂逻辑应改写为普通循环",
        ],
        "quizzes": [
            {"q": "生成器表达式为什么第二次转列表为空？", "a": "生成器只能迭代一次，第一次消费后已耗尽。"},
            {"q": "什么场景更适合使用生成器表达式？", "a": "数据量大、只需单次遍历或做聚合计算的场景。"},
        ],
    },
    {
        "key": "py-04",
        "title": "闭包、装饰器与 functools.wraps",
        "domain": "Python",
        "tags": ["Python", "闭包", "装饰器"],
        "concept": "闭包是引用了外层函数局部变量的内层函数。装饰器本质是接收函数并返回新函数的高阶函数，常用于日志、鉴权、缓存和重试。",
        "principles": [
            "内层函数引用外层变量时，外层函数结束后变量仍被保留。",
            "装饰器在函数定义阶段执行，返回的包装函数在调用阶段执行。",
            "使用 functools.wraps 保留原函数的名称、文档和签名信息。",
            "带参数的装饰器需要再套一层函数，形成三层结构。",
        ],
        "example": """```python
from functools import wraps

def log_calls(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"calling {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

@log_calls
def add(a, b):
    return a + b

print(add(1, 2))       # 先打印 calling add，再输出 3
```""",
        "summary": [
            "闭包让函数携带定义时的环境。",
            "装饰器是函数到函数的高阶变换。",
            "wraps 保留元信息，便于调试与文档生成。",
        ],
        "key_points": [
            "闭包引用外层函数局部变量",
            "装饰器在高阶函数中包装原函数",
            "functools.wraps 保留函数元信息",
            "带参数装饰器需要三层嵌套",
        ],
        "quizzes": [
            {"q": "装饰器在什么阶段执行？", "a": "在函数定义阶段执行，返回包装后的函数对象。"},
            {"q": "为什么包装函数要使用 functools.wraps？", "a": "为了保留原函数的名称、文档字符串和签名等元信息。"},
        ],
    },
    {
        "key": "py-05",
        "title": "Python 异常处理与上下文管理器",
        "domain": "Python",
        "tags": ["Python", "异常", "上下文管理器"],
        "concept": "异常用于中断正常流程并向上传递错误。上下文管理器通过 with 语句保证资源在离开代码块时被释放，即使中途抛出异常。",
        "principles": [
            "只捕获能够处理的异常，避免裸 except 吞掉所有错误。",
            "finally 无论是否异常都会执行，适合释放资源。",
            "自定义上下文管理器可实现 __enter__ 与 __exit__，或用 @contextmanager。",
            "__exit__ 返回 True 会抑制异常，通常不应随意这样做。",
        ],
        "example": """```python
from contextlib import contextmanager

@contextmanager
def transaction(conn):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

with transaction(conn) as tx:
    tx.execute("UPDATE account SET balance = balance - 100 WHERE id = 1")
```""",
        "summary": [
            "异常处理的目标是恢复或明确失败，而不是隐藏错误。",
            "with 语句把资源释放逻辑集中到上下文管理器。",
            "数据库事务是上下文管理器的典型应用。",
        ],
        "key_points": [
            "避免裸 except 捕获所有异常",
            "finally 保证资源释放",
            "上下文管理器实现 enter 与 exit",
            "contextmanager 可简化生成器式资源管理",
        ],
        "quizzes": [
            {"q": "裸 except 的主要风险是什么？", "a": "会吞掉包括 KeyboardInterrupt 在内的所有异常，掩盖真实错误。"},
            {"q": "with 语句如何保证资源释放？", "a": "离开代码块时自动调用上下文管理器的 __exit__ 方法。"},
        ],
    },
    {
        "key": "py-06",
        "title": "迭代器协议与 yield 的工作方式",
        "domain": "Python",
        "tags": ["Python", "迭代器", "生成器"],
        "concept": "可迭代对象实现 __iter__，迭代器同时实现 __iter__ 与 __next__。含 yield 的函数调用时不会立即执行，而是返回生成器；每次 next 推进到下一个 yield。",
        "principles": [
            "for 循环先调用 iter() 获取迭代器，再反复调用 next()。",
            "生成器在 yield 处暂停并保留局部变量状态。",
            "迭代结束时抛出 StopIteration，for 循环会自动处理。",
            "生成器适合流式读取文件、分页拉取和管道式处理。",
        ],
        "example": """```python
def read_lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n")

for line in read_lines("notes.md"):
    if line.startswith("## "):
        print(line)
```""",
        "summary": [
            "迭代器协议由 __iter__ 与 __next__ 组成。",
            "yield 让函数变成状态可暂停的生成器。",
            "生成器能以常量内存处理大文件或数据流。",
        ],
        "key_points": [
            "可迭代对象实现 __iter__",
            "迭代器实现 __next__ 并在结束时抛 StopIteration",
            "yield 暂停函数并保留局部状态",
            "生成器适合流式处理大数据",
        ],
        "quizzes": [
            {"q": "调用含 yield 的函数会立即执行函数体吗？", "a": "不会，而是返回生成器对象，首次 next 时才执行到第一个 yield。"},
            {"q": "for 循环如何知道迭代结束？", "a": "迭代器抛出 StopIteration 时，for 循环捕获并正常结束。"},
        ],
    },
    {
        "key": "py-07",
        "title": "类型注解、dataclass 与可维护性",
        "domain": "Python",
        "tags": ["Python", "类型注解", "dataclass"],
        "concept": "类型注解不会在运行时强制检查，但能被 IDE、mypy 和 FastAPI 等工具利用。dataclass 自动生成初始化、相等比较和 repr，适合承载结构化数据。",
        "principles": [
            "使用 list[str]、dict[str, int] 等内置泛型写法，兼容 Python 3.9+。",
            "Optional[T] 表示可能为 None，应显式处理 None 分支。",
            "dataclass 默认生成 __init__、__repr__、__eq__。",
            "frozen=True 可创建不可变数据对象，便于作为字典键或缓存键。",
        ],
        "example": """```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class PlanStep:
    name: str
    task_type: str
    target: int = 0
    tags: tuple[str, ...] = field(default_factory=tuple)

step = PlanStep(name="每日刷题", task_type="NUMERIC", target=30)
print(step)
```""",
        "summary": [
            "类型注解提升可读性并支持静态检查。",
            "dataclass 减少样板代码，适合领域模型与 DTO。",
            "frozen 数据对象更安全，但更新需创建新实例。",
        ],
        "key_points": [
            "类型注解主要服务于静态检查与工具",
            "Optional 表示可能为 None",
            "dataclass 自动生成常用方法",
            "frozen 创建不可变数据对象",
        ],
        "quizzes": [
            {"q": "Python 会在运行时强制执行类型注解吗？", "a": "不会，注解主要供 IDE、mypy、框架等工具使用。"},
            {"q": "dataclass 的 frozen=True 有什么作用？", "a": "禁止修改实例字段，使对象不可变并可用于哈希场景。"},
        ],
    },
    {
        "key": "py-08",
        "title": "线程、进程与 asyncio 的选型",
        "domain": "Python",
        "tags": ["Python", "并发", "asyncio"],
        "concept": "I/O 密集任务适合线程或 asyncio，CPU 密集任务需要多进程绕过 GIL。asyncio 通过事件循环在单线程内切换协程，适合大量并发连接。",
        "principles": [
            "GIL 使同一进程内多个线程不能同时执行 Python 字节码。",
            "线程适合阻塞式 I/O 和已有同步库的场景。",
            "多进程拥有独立解释器与内存，适合 CPU 密集计算。",
            "asyncio 要求全链路使用非阻塞库，阻塞调用会卡住事件循环。",
        ],
        "table": "| 场景 | 推荐模型 | 原因 |\n|---|---|---|\n| 文件/网络 I/O | 线程或 asyncio | 等待时间长，CPU 占用低 |\n| 图像/数值计算 | 多进程 | 绕过 GIL 并行计算 |\n| 高并发 API | asyncio | 单线程调度大量协程 |",
        "example": """```python
import asyncio

async def fetch(name, delay):
    await asyncio.sleep(delay)
    return name

async def main():
    results = await asyncio.gather(
        fetch("a", 0.2),
        fetch("b", 0.1),
    )
    print(results)      # ['a', 'b']

asyncio.run(main())
```""",
        "summary": [
            "先判断任务是 I/O 密集还是 CPU 密集。",
            "线程与 asyncio 都不能突破 GIL 做并行计算。",
            "asyncio 的性能依赖全链路非阻塞。",
        ],
        "key_points": [
            "GIL 限制同进程多线程并行执行字节码",
            "线程适合阻塞式 I/O",
            "多进程适合 CPU 密集计算",
            "asyncio 中阻塞调用会卡住事件循环",
        ],
        "quizzes": [
            {"q": "为什么 CPU 密集任务不推荐多线程？", "a": "GIL 使线程无法同时执行 Python 字节码，难以获得并行加速。"},
            {"q": "asyncio 中调用阻塞函数会怎样？", "a": "会阻塞整个事件循环，导致其他协程无法推进。"},
        ],
    },
    {
        "key": "fa-01",
        "title": "FastAPI 路由、依赖注入与请求生命周期",
        "domain": "FastAPI",
        "tags": ["FastAPI", "依赖注入", "路由"],
        "concept": "FastAPI 基于 Starlette 处理 ASGI 请求，通过装饰器声明路由，通过 Depends 注入数据库会话、当前用户等依赖。依赖可以嵌套，并在同一请求内缓存结果。",
        "principles": [
            "路径参数、查询参数和请求体由类型注解自动解析与校验。",
            "Depends 声明的依赖在请求进入处理函数前执行。",
            "同一请求内相同依赖默认只执行一次，结果被缓存。",
            "使用 yield 的依赖可在请求结束后执行清理逻辑。",
        ],
        "example": """```python
from fastapi import APIRouter, Depends

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/plans/{plan_id}")
def read_plan(plan_id: int, db=Depends(get_db)):
    return plan_service.get(db, plan_id)
```""",
        "summary": [
            "FastAPI 用类型注解完成参数解析与校验。",
            "Depends 把横切逻辑从路由函数中解耦。",
            "yield 依赖适合管理数据库会话和锁。",
        ],
        "key_points": [
            "路由参数由类型注解自动解析",
            "Depends 用于注入可复用依赖",
            "同一请求内依赖结果默认缓存",
            "yield 依赖负责请求结束后的清理",
        ],
        "quizzes": [
            {"q": "Depends 的主要作用是什么？", "a": "声明依赖并在请求处理前注入，实现复用与解耦。"},
            {"q": "为什么数据库会话依赖要使用 yield？", "a": "便于在请求结束后执行 close 等清理逻辑。"},
        ],
    },
    {
        "key": "fa-02",
        "title": "Pydantic 请求校验与响应模型",
        "domain": "FastAPI",
        "tags": ["FastAPI", "Pydantic", "校验"],
        "concept": "Pydantic 模型在请求进入业务逻辑前完成类型转换与约束校验。response_model 会过滤未声明字段，避免泄露密码哈希、内部标识等敏感信息。",
        "principles": [
            "Field 可声明长度、范围和默认值等约束。",
            "请求体校验失败时 FastAPI 自动返回 422。",
            "响应模型应显式声明，不要直接返回 ORM 对象。",
            "使用 ConfigDict(from_attributes=True) 可从对象属性构造响应。",
        ],
        "example": """```python
from pydantic import BaseModel, Field

class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date

class PlanOut(BaseModel):
    id: int
    name: str
    status: str

@router.post("/plans", response_model=PlanOut)
def create_plan(data: PlanCreate, db=Depends(get_db)):
    return plan_service.create(db, data)
```""",
        "summary": [
            "Pydantic 把校验前移到接口边界。",
            "响应模型是防止敏感字段泄露的最后一道屏障。",
            "输入模型与输出模型应分开设计。",
        ],
        "key_points": [
            "Field 声明字段约束",
            "校验失败自动返回 422",
            "response_model 过滤输出字段",
            "from_attributes 支持从对象构造响应",
        ],
        "quizzes": [
            {"q": "为什么输入模型和输出模型要分开？", "a": "输入关注可写字段，输出需要控制暴露范围并隔离内部结构。"},
            {"q": "response_model 能防止什么问题？", "a": "防止未声明字段（如密码哈希）被意外返回给客户端。"},
        ],
    },
    {
        "key": "fa-03",
        "title": "FastAPI 中同步函数与异步函数的选择",
        "domain": "FastAPI",
        "tags": ["FastAPI", "async", "线程池"],
        "concept": "FastAPI 会把普通 def 路由放到线程池执行，把 async def 路由放到事件循环执行。选择错误会让阻塞调用占满线程池或卡住事件循环。",
        "principles": [
            "async def 内部只能使用非阻塞库，否则会阻塞整个事件循环。",
            "普通 def 路由由线程池承载，适合现有同步 ORM 与阻塞 I/O。",
            "CPU 密集任务不应直接放在请求线程中，应交给任务队列或进程池。",
            "同一路由不要混用阻塞调用与 async 声明。",
        ],
        "example": """```python
# 同步 ORM：使用 def，让 FastAPI 放入线程池
@router.get("/plans")
def list_plans(db=Depends(get_db)):
    return plan_service.list(db)

# 异步 HTTP 客户端：使用 async def 与非阻塞库
@router.get("/remote")
async def remote():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://example.com")
    return {"status": resp.status_code}
```""",
        "summary": [
            "async def 不代表自动并行，只是可被事件循环调度。",
            "阻塞库应放在普通 def 路由中由线程池执行。",
            "CPU 密集任务应异步化到独立工作进程。",
        ],
        "key_points": [
            "普通 def 路由运行在线程池",
            "async def 路由运行在事件循环",
            "async 中使用阻塞库会卡住事件循环",
            "CPU 密集任务应交给独立工作进程",
        ],
        "quizzes": [
            {"q": "为什么不能在 async def 中直接调用阻塞 ORM？", "a": "会阻塞事件循环，使其他请求无法推进。"},
            {"q": "普通 def 路由由什么执行？", "a": "FastAPI 会把它放入线程池执行，避免阻塞事件循环。"},
        ],
    },
    {
        "key": "fa-04",
        "title": "中间件、CORS 与统一异常处理",
        "domain": "FastAPI",
        "tags": ["FastAPI", "中间件", "CORS"],
        "concept": "中间件包裹整个请求响应流程，适合记录请求 ID、耗时和统一响应头。CORS 中间件控制浏览器跨域访问；异常处理器把内部异常转换为稳定的 HTTP 响应。",
        "principles": [
            "中间件按添加顺序的逆序执行响应阶段。",
            "CORS 的 allow_origins 应使用明确白名单，不能在生产环境使用 *。",
            "自定义异常处理器可隐藏堆栈信息并返回统一错误结构。",
            "认证失败、权限不足应分别返回 401 与 403。",
        ],
        "example": """```python
@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(AppError)
async def handle_app_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
```""",
        "summary": [
            "中间件适合处理横切关注点。",
            "CORS 白名单必须与真实前端域名一致。",
            "统一异常处理让客户端获得稳定错误契约。",
        ],
        "key_points": [
            "中间件包裹请求与响应全过程",
            "CORS 生产环境应使用明确白名单",
            "异常处理器统一错误响应结构",
            "401 表示未认证而 403 表示无权限",
        ],
        "quizzes": [
            {"q": "生产环境为什么不能用 allow_origins=['*']？", "a": "会放开任意站点跨域访问，增加凭据泄露与 CSRF 风险。"},
            {"q": "401 与 403 的区别是什么？", "a": "401 表示未认证或凭证无效，403 表示已认证但无权访问。"},
        ],
    },
    {
        "key": "fa-05",
        "title": "JWT 认证、依赖注入与权限校验",
        "domain": "FastAPI",
        "tags": ["FastAPI", "JWT", "认证"],
        "concept": "JWT 由头部、载荷和签名组成，服务端通过签名验证令牌完整性。FastAPI 常用 OAuth2PasswordBearer 或 Cookie 提取令牌，再通过依赖注入得到当前用户。",
        "principles": [
            "Access Token 短有效期，Refresh Token 长有效期并支持轮换。",
            "令牌只应存放必要声明，不得放入密码等敏感信息。",
            "权限校验应集中在依赖中，避免每个路由重复实现。",
            "登出或改密后应撤销会话，使旧 Refresh Token 失效。",
        ],
        "example": """```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db),
):
    payload = decode_token(token)
    user = user_service.get_active(db, payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    return user

@router.get("/me")
def me(user=Depends(get_current_user)):
    return user
```""",
        "summary": [
            "JWT 的签名保证令牌未被篡改，但不自动保证可撤销。",
            "短 Access + 可轮换 Refresh 是常见组合。",
            "权限逻辑集中到依赖中更易审计。",
        ],
        "key_points": [
            "JWT 通过签名保证完整性",
            "Access Token 应短有效期",
            "Refresh Token 需要轮换与撤销",
            "权限校验适合放在依赖中",
        ],
        "quizzes": [
            {"q": "JWT 载荷中可以存放密码吗？", "a": "不可以，载荷可被解码，只能存放非敏感的声明信息。"},
            {"q": "为什么 Refresh Token 需要轮换？", "a": "降低令牌泄露后的长期风险，并能检测重放行为。"},
        ],
    },
]