"""笔记内容 C1：操作系统进阶与 React（13 篇）。"""

NOTES = [
    {
        "key": "os-03",
        "title": "虚拟内存、分页与地址转换",
        "domain": "操作系统",
        "tags": ["操作系统", "虚拟内存", "分页"],
        "concept": "虚拟内存为每个进程提供独立地址空间。分页把虚拟地址划分为固定大小的页，通过页表映射到物理页框，使进程无需连续物理内存。",
        "principles": [
            "虚拟地址由页号和页内偏移组成。",
            "页表记录虚拟页到物理页框的映射与权限位。",
            "TLB 缓存近期页表项，减少多级页表访问开销。",
            "缺页时触发中断，由操作系统加载页面并更新页表。",
        ],
        "example": """```text
32 位地址、4KB 页：
页号 = 地址 >> 12
页内偏移 = 地址 & 0xFFF
页表[页号] -> 物理页框号
物理地址 = (页框号 << 12) | 页内偏移
```""",
        "summary": [
            "虚拟内存提供隔离、抽象与按需加载。",
            "分页解决外部碎片并支持非连续分配。",
            "TLB 是多级页表性能的关键。",
        ],
        "key_points": [
            "虚拟内存为进程提供独立地址空间",
            "分页把地址划分为页号与页内偏移",
            "页表记录虚拟页到物理页框映射",
            "TLB 缓存页表项减少访问开销",
        ],
        "quizzes": [
            {"q": "分页如何避免外部碎片？", "a": "页和页框大小固定，物理内存可按页框分配，不会产生大小不匹配的外部空洞。"},
            {"q": "TLB 的作用是什么？", "a": "缓存近期使用的页表项，减少每次地址转换访问内存页表的次数。"},
        ],
    },
    {
        "key": "os-04",
        "title": "页面置换算法与缺页中断",
        "domain": "操作系统",
        "tags": ["操作系统", "页面置换", "缺页"],
        "concept": "物理内存不足时，操作系统需要选择页面换出。FIFO 简单但可能出现 Belady 异常；LRU 依据最近使用情况，接近最优但实现成本高；Clock 算法用访问位近似 LRU。",
        "principles": [
            "缺页中断发生在访问的页面不在物理内存时。",
            "置换算法目标是最小化缺页率。",
            "工作集模型用于估计进程当前需要的页面集合。",
            "抖动是频繁换入换出导致 CPU 利用率下降的现象。",
        ],
        "table": "| 算法 | 依据 | 特点 |\n|---|---|---|\n| FIFO | 进入时间 | 简单，可能 Belady 异常 |\n| LRU | 最近访问 | 效果好，成本高 |\n| Clock | 访问位 | 近似 LRU，开销低 |",
        "example": """```text
Clock 算法：
指针扫描页框，访问位为 1 则清零并跳过；
访问位为 0 的页面被选中换出。
```""",
        "summary": [
            "缺页率直接受置换算法影响。",
            "LRU 效果好但需要额外维护访问顺序。",
            "工作集与抖动分析用于容量规划。",
        ],
        "key_points": [
            "缺页中断发生在页面不在内存时",
            "FIFO 可能出现 Belady 异常",
            "LRU 依据最近访问情况",
            "Clock 用访问位近似 LRU",
        ],
        "quizzes": [
            {"q": "Belady 异常是什么？", "a": "使用 FIFO 时增加物理页框反而导致缺页次数增加的现象。"},
            {"q": "系统抖动的主要原因是什么？", "a": "分配给进程的物理页不足，频繁缺页换入换出，CPU 大量时间用于调度 I/O。"},
        ],
    },
    {
        "key": "os-05",
        "title": "文件系统、inode 与磁盘 I/O",
        "domain": "操作系统",
        "tags": ["操作系统", "文件系统", "inode"],
        "concept": "文件系统把磁盘块组织为目录、inode 和数据块。inode 保存文件元数据与数据块指针，目录项把文件名映射到 inode 编号。",
        "principles": [
            "文件名存储在目录项中，inode 不保存文件名。",
            "硬链接共享同一 inode，软链接是独立文件。",
            "页缓存减少磁盘 I/O，但断电可能丢失未落盘数据。",
            "顺序 I/O 通常快于随机 I/O。",
        ],
        "example": """```bash
stat notes.md          # 查看 inode、权限、大小、时间
df -h                  # 文件系统容量
du -sh ./storage       # 目录占用
iostat -x 1            # 磁盘 I/O 指标
```""",
        "summary": [
            "inode 是文件元数据与数据块索引的核心。",
            "硬链接与软链接的语义不同。",
            "页缓存与落盘策略影响性能和数据安全。",
        ],
        "key_points": [
            "inode 保存文件元数据",
            "目录项把文件名映射到 inode",
            "硬链接共享 inode",
            "顺序 I/O 通常快于随机 I/O",
        ],
        "quizzes": [
            {"q": "inode 中保存文件名吗？", "a": "不保存，文件名在目录项中，目录项指向 inode 编号。"},
            {"q": "硬链接与软链接的区别是什么？", "a": "硬链接指向同一 inode，软链接是保存目标路径的独立文件。"},
        ],
    },
    {
        "key": "os-06",
        "title": "死锁的四个必要条件与处理策略",
        "domain": "操作系统",
        "tags": ["操作系统", "死锁", "并发"],
        "concept": "死锁是多个进程互相等待对方持有的资源而无法推进。必要条件包括互斥、占有并等待、不可抢占和循环等待。处理策略分为预防、避免、检测与恢复。",
        "principles": [
            "破坏任一必要条件即可预防死锁。",
            "资源有序分配可以破坏循环等待。",
            "银行家算法属于死锁避免，需要预知最大需求。",
            "检测到死锁后可终止进程或回滚资源。",
        ],
        "example": """```text
进程 A 持有锁 1，等待锁 2
进程 B 持有锁 2，等待锁 1
→ 循环等待，形成死锁
```""",
        "summary": [
            "死锁需要同时满足四个必要条件。",
            "工程上最常用的是统一加锁顺序与超时重试。",
            "数据库死锁由存储引擎检测并回滚事务。",
        ],
        "key_points": [
            "死锁四个必要条件",
            "破坏循环等待可预防死锁",
            "银行家算法用于死锁避免",
            "统一加锁顺序是常用工程手段",
        ],
        "quizzes": [
            {"q": "死锁的四个必要条件是什么？", "a": "互斥、占有并等待、不可抢占、循环等待。"},
            {"q": "统一加锁顺序破坏了哪个条件？", "a": "破坏了循环等待条件。"},
        ],
    },
    {
        "key": "os-07",
        "title": "Linux 性能排查常用命令",
        "domain": "操作系统",
        "tags": ["操作系统", "Linux", "排查"],
        "concept": "性能排查遵循从整体到局部的顺序：先看负载与 CPU，再看内存、磁盘和网络，最后定位到具体进程与线程。",
        "principles": [
            "top/htop 观察整体负载与进程资源占用。",
            "vmstat 查看内存、交换与上下文切换。",
            "iostat 判断磁盘是否成为瓶颈。",
            "ss/netstat 查看连接与端口监听状态。",
        ],
        "example": """```bash
uptime
top -H -p 1234
vmstat 1 5
iostat -x 1 5
ss -lntp
pidstat -u -p 1234 1
```""",
        "summary": [
            "先判断瓶颈类型，再深入具体指标。",
            "线程级观察有助于定位热点线程。",
            "网络与磁盘问题常表现为负载升高但 CPU 不高。",
        ],
        "key_points": [
            "top 观察整体资源占用",
            "vmstat 查看内存与上下文切换",
            "iostat 判断磁盘瓶颈",
            "ss 查看连接与监听端口",
        ],
        "quizzes": [
            {"q": "负载很高但 CPU 使用率不高，可能是什么原因？", "a": "可能存在大量不可中断 I/O 等待，例如磁盘或网络阻塞。"},
            {"q": "如何查看某个进程内各线程的 CPU 占用？", "a": "使用 top -H -p <pid> 或 pidstat -u -p <pid> 观察线程级数据。"},
        ],
    },
    {
        "key": "react-01",
        "title": "React 组件、Props 与状态",
        "domain": "React 与 Next.js",
        "tags": ["React", "组件", "状态"],
        "concept": "React 组件是返回 UI 描述的函数。Props 是父组件传入的只读数据，State 是组件内部可变状态。状态更新会触发重新渲染。",
        "principles": [
            "Props 不可在子组件中直接修改。",
            "状态更新应使用 setState 或 setter，不能直接改变量。",
            "React 采用不可变更新，返回新对象以触发渲染。",
            "状态应尽量放在需要它的最近公共祖先。",
        ],
        "example": """```jsx
function Counter({ step = 1 }) {
  const [count, setCount] = useState(0);

  return (
    <button onClick={() => setCount((value) => value + step)}>
      {count}
    </button>
  );
}
```""",
        "summary": [
            "Props 向下流动，State 由组件自己管理。",
            "不可变更新是 React 渲染判断的基础。",
            "状态提升用于多个组件共享数据。",
        ],
        "key_points": [
            "Props 是只读输入",
            "State 触发组件重新渲染",
            "状态更新必须使用 setter",
            "不可变更新返回新对象",
        ],
        "quizzes": [
            {"q": "为什么不能直接修改 props？", "a": "Props 属于父组件，直接修改会破坏单向数据流并导致状态不可预测。"},
            {"q": "React 为什么要求不可变更新状态？", "a": "通过引用比较判断状态是否变化，从而决定是否重新渲染。"},
        ],
    },
    {
        "key": "react-02",
        "title": "useEffect 与副作用管理",
        "domain": "React 与 Next.js",
        "tags": ["React", "useEffect", "副作用"],
        "concept": "useEffect 在渲染提交后执行副作用，例如请求数据、订阅事件和操作 DOM。依赖数组决定何时重新执行，清理函数用于取消订阅或请求。",
        "principles": [
            "空依赖数组表示只在挂载时执行一次。",
            "依赖变化会先执行上一次的清理函数，再执行新的副作用。",
            "请求数据时要处理组件卸载后的竞态。",
            "不要在 useEffect 中无条件设置状态导致无限循环。",
        ],
        "example": """```jsx
useEffect(() => {
  const controller = new AbortController();

  fetch(`/api/plans/${id}`, { signal: controller.signal })
    .then((res) => res.json())
    .then(setPlan)
    .catch((err) => {
      if (err.name !== "AbortError") setError(err);
    });

  return () => controller.abort();
}, [id]);
```""",
        "summary": [
            "useEffect 用于同步外部系统。",
            "清理函数是避免泄漏与竞态的关键。",
            "依赖数组必须完整，不能靠省略来掩盖问题。",
        ],
        "key_points": [
            "useEffect 在渲染提交后执行",
            "空依赖只在挂载时执行",
            "清理函数用于取消订阅与请求",
            "依赖数组必须完整",
        ],
        "quizzes": [
            {"q": "useEffect 的清理函数在什么时候执行？", "a": "组件卸载时以及下一次依赖变化导致副作用重新执行之前。"},
            {"q": "如何避免数据请求的竞态问题？", "a": "使用 AbortController 或标记位在清理函数中取消上一次请求。"},
        ],
    },
    {
        "key": "react-03",
        "title": "Hooks 规则与自定义 Hook",
        "domain": "React 与 Next.js",
        "tags": ["React", "Hooks", "复用"],
        "concept": "Hooks 只能在函数组件或自定义 Hook 顶层调用，不能在条件、循环或嵌套函数中调用。自定义 Hook 以 use 开头，用于复用有状态逻辑。",
        "principles": [
            "Hooks 的调用顺序必须在每次渲染中保持一致。",
            "自定义 Hook 本质是函数，内部可以调用其他 Hooks。",
            "自定义 Hook 共享逻辑但不共享状态。",
            "不要在普通函数中调用 Hooks。",
        ],
        "example": """```jsx
function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
```""",
        "summary": [
            "Hooks 规则保证 React 能正确关联状态。",
            "自定义 Hook 复用逻辑而非状态实例。",
            "以 use 开头便于 lint 工具检查规则。",
        ],
        "key_points": [
            "Hooks 只能在顶层调用",
            "Hooks 调用顺序必须稳定",
            "自定义 Hook 以 use 开头",
            "自定义 Hook 共享逻辑不共享状态",
        ],
        "quizzes": [
            {"q": "为什么 Hooks 不能放在条件语句中？", "a": "条件调用会改变 Hooks 顺序，导致 React 无法正确对应状态。"},
            {"q": "两个组件使用同一个自定义 Hook 会共享状态吗？", "a": "不会，每次调用都会创建独立的状态。"},
        ],
    },
    {
        "key": "react-04",
        "title": "Context、Reducer 与状态管理边界",
        "domain": "React 与 Next.js",
        "tags": ["React", "Context", "Reducer"],
        "concept": "Context 用于跨层级传递数据，避免逐层 props drilling。useReducer 适合管理复杂状态转移。两者结合可以构建轻量全局状态。",
        "principles": [
            "Context 值变化会让所有消费者重新渲染。",
            "把频繁变化的值拆分成独立 Context 可减少渲染。",
            "Reducer 把状态转移集中为纯函数，便于测试。",
            "全局状态并非越多越好，局部状态优先。",
        ],
        "example": """```jsx
const PlanContext = createContext(null);

function reducer(state, action) {
  switch (action.type) {
    case "add":
      return [...state, action.plan];
    case "remove":
      return state.filter((p) => p.id !== action.id);
    default:
      return state;
  }
}

function PlanProvider({ children }) {
  const [plans, dispatch] = useReducer(reducer, []);
  return (
    <PlanContext.Provider value={{ plans, dispatch }}>
      {children}
    </PlanContext.Provider>
  );
}
```""",
        "summary": [
            "Context 解决跨层级传值问题。",
            "Reducer 让复杂状态转移可预测。",
            "拆分 Context 可降低不必要的重渲染。",
        ],
        "key_points": [
            "Context 避免逐层传递 props",
            "Context 值变化会触发消费者重渲染",
            "Reducer 用纯函数管理状态转移",
            "局部状态优先于全局状态",
        ],
        "quizzes": [
            {"q": "Context 值变化会影响哪些组件？", "a": "所有订阅该 Context 的消费者组件都会重新渲染。"},
            {"q": "useReducer 相比 useState 的优势是什么？", "a": "适合复杂状态转移，把更新逻辑集中为可测试的纯函数。"},
        ],
    },
    {
        "key": "react-05",
        "title": "React 性能优化：memo、useMemo 与 useCallback",
        "domain": "React 与 Next.js",
        "tags": ["React", "性能", "memo"],
        "concept": "React 默认在父组件渲染时重新渲染子组件。React.memo 对 props 做浅比较，useMemo 缓存计算结果，useCallback 缓存函数引用，避免不必要的渲染与计算。",
        "principles": [
            "先测量再优化，避免盲目使用 memo。",
            "memo 只在 props 浅比较相等时跳过渲染。",
            "useMemo 适合昂贵计算，不适合简单表达式。",
            "useCallback 常与 memo 子组件或依赖数组配合使用。",
        ],
        "example": """```jsx
const Row = memo(function Row({ item, onSelect }) {
  return <li onClick={() => onSelect(item.id)}>{item.name}</li>;
});

function PlanList({ items, onSelect }) {
  const handleSelect = useCallback((id) => onSelect(id), [onSelect]);
  const sorted = useMemo(
    () => [...items].sort((a, b) => a.name.localeCompare(b.name)),
    [items],
  );

  return sorted.map((item) => (
    <Row key={item.id} item={item} onSelect={handleSelect} />
  ));
}
```""",
        "summary": [
            "性能优化应基于实际瓶颈。",
            "memo 与 useCallback 需要配合才能稳定生效。",
            "useMemo 用于昂贵计算而非所有变量。",
        ],
        "key_points": [
            "React.memo 对 props 浅比较",
            "useMemo 缓存计算结果",
            "useCallback 缓存函数引用",
            "优化前应先测量瓶颈",
        ],
        "quizzes": [
            {"q": "React.memo 在什么情况下跳过渲染？", "a": "props 浅比较相等时跳过子组件重新渲染。"},
            {"q": "为什么 useCallback 常与 memo 子组件一起使用？", "a": "稳定函数引用可避免 memo 因 props 引用变化而失效。"},
        ],
    },
    {
        "key": "react-06",
        "title": "Next.js 路由与渲染模式",
        "domain": "React 与 Next.js",
        "tags": ["Next.js", "路由", "SSR"],
        "concept": "Next.js 使用文件系统路由。App Router 支持服务端组件、客户端组件、SSR、SSG 和 ISR。渲染模式决定页面在构建时、请求时还是客户端生成。",
        "principles": [
            "服务端组件默认不发送组件 JS 到浏览器，适合数据读取。",
            "客户端组件使用 use client 声明，可访问浏览器 API 与状态。",
            "SSG 在构建时生成，ISR 可按周期重新验证。",
            "动态路由使用 [param] 目录，布局使用 layout.js。",
        ],
        "table": "| 模式 | 生成时机 | 适用场景 |\n|---|---|---|\n| SSR | 每次请求 | 个性化数据 |\n| SSG | 构建时 | 静态内容 |\n| ISR | 构建 + 周期更新 | 半静态内容 |\n| CSR | 浏览器 | 强交互页面 |",
        "example": """```jsx
// app/plans/[id]/page.jsx
export default async function PlanPage({ params }) {
  const plan = await getPlan(params.id);
  return <PlanDetail plan={plan} />;
}

// 需要交互时拆分为客户端组件
"use client";
export function PlanActions({ id }) {
  return <button onClick={() => archive(id)}>归档</button>;
}
```""",
        "summary": [
            "文件系统路由降低路由配置成本。",
            "服务端组件与客户端组件按能力拆分。",
            "渲染模式影响首屏、缓存与数据新鲜度。",
        ],
        "key_points": [
            "Next.js 使用文件系统路由",
            "服务端组件默认不向浏览器发送组件 JS",
            "客户端组件需要 use client",
            "SSG ISR SSR 的生成时机不同",
        ],
        "quizzes": [
            {"q": "服务端组件与客户端组件的主要区别是什么？", "a": "服务端组件在服务器渲染且不发送组件 JS，客户端组件可访问浏览器 API 与交互状态。"},
            {"q": "ISR 适合什么类型的页面？", "a": "内容相对稳定但需要周期性更新的页面。"},
        ],
    },
    {
        "key": "react-07",
        "title": "Next.js 数据获取、缓存与重新验证",
        "domain": "React 与 Next.js",
        "tags": ["Next.js", "数据获取", "缓存"],
        "concept": "Next.js 在服务端组件中直接使用 async/await 获取数据。fetch 默认参与请求缓存，可通过 cache 与 revalidate 控制缓存策略。",
        "principles": [
            "服务端组件可直接访问数据库或内部服务，避免暴露密钥。",
            "cache: 'no-store' 表示每次请求都重新获取。",
            "revalidate 控制增量静态再生成的周期。",
            "变更数据后可使用 revalidatePath 或 revalidateTag 精确失效。",
        ],
        "example": """```jsx
async function getPlans() {
  const res = await fetch(`${API}/plans`, {
    next: { revalidate: 60, tags: ["plans"] },
  });
  if (!res.ok) throw new Error("加载失败");
  return res.json();
}

// 数据变更后
revalidateTag("plans");
```""",
        "summary": [
            "服务端获取数据可减少客户端暴露与瀑布请求。",
            "缓存策略要匹配数据更新频率。",
            "标签化失效便于精确更新缓存。",
        ],
        "key_points": [
            "服务端组件可直接 async 获取数据",
            "no-store 表示不缓存",
            "revalidate 控制重新验证周期",
            "revalidateTag 可精确失效缓存",
        ],
        "quizzes": [
            {"q": "cache: 'no-store' 的含义是什么？", "a": "每次请求都重新获取数据，不使用缓存。"},
            {"q": "revalidateTag 的作用是什么？", "a": "让带有对应标签的缓存数据失效并在后续请求中重新生成。"},
        ],
    },
    {
        "key": "react-08",
        "title": "前后端分离下的认证与受保护路由",
        "domain": "React 与 Next.js",
        "tags": ["React", "认证", "路由守卫"],
        "concept": "前后端分离时，前端负责登录态展示与路由跳转，后端负责真正的身份与权限校验。受保护路由不能只靠前端隐藏页面。",
        "principles": [
            "Access Token 可存内存，Refresh Token 建议放 HttpOnly Cookie。",
            "路由守卫在客户端做体验优化，服务端仍需校验每个请求。",
            "401 触发刷新令牌或跳转登录，403 展示无权限。",
            "登出应同时清理本地状态并调用服务端撤销接口。",
        ],
        "example": """```jsx
function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) return <Spinner />;
  return user ? children : null;
}
```""",
        "summary": [
            "前端守卫只改善体验，不能替代后端鉴权。",
            "令牌存储方式直接影响 XSS 与 CSRF 风险。",
            "401 与 403 应分别处理。",
        ],
        "key_points": [
            "前端路由守卫不能替代后端鉴权",
            "Refresh Token 建议放在 HttpOnly Cookie",
            "401 触发刷新或登录跳转",
            "403 表示已认证但无权限",
        ],
        "quizzes": [
            {"q": "为什么不能只依赖前端路由守卫保护页面？", "a": "攻击者可直接调用后端接口，服务端必须独立校验身份与权限。"},
            {"q": "Refresh Token 放在 HttpOnly Cookie 的好处是什么？", "a": "JavaScript 无法读取，降低 XSS 窃取风险。"},
        ],
    },
]