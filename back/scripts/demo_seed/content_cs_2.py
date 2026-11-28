"""笔记内容 B2：树/图、计算机网络与操作系统基础（12 篇）。"""

NOTES = [
    {
        "key": "dsa-06",
        "title": "二叉搜索树、平衡树与红黑树",
        "domain": "数据结构与算法",
        "tags": ["算法", "BST", "红黑树"],
        "concept": "二叉搜索树满足左子树小于根、右子树大于根，查找平均 O(log n)。若插入有序数据会退化为链表，因此需要 AVL、红黑树等平衡结构。",
        "principles": [
            "BST 的查找、插入、删除平均复杂度为 O(log n)。",
            "AVL 通过高度差约束保持严格平衡，旋转较多。",
            "红黑树通过颜色约束保持近似平衡，插入删除更稳定。",
            "Java TreeMap、HashMap 树化桶都使用红黑树。",
        ],
        "example": """```python
def search(node, target):
    while node is not None:
        if target == node.value:
            return node
        node = node.left if target < node.value else node.right
    return None
```""",
        "summary": [
            "BST 的性能取决于树高。",
            "平衡结构用旋转或颜色约束控制树高。",
            "红黑树在工程中兼顾查询与更新性能。",
        ],
        "key_points": [
            "BST 左小右大",
            "有序插入会使 BST 退化为链表",
            "AVL 严格平衡旋转较多",
            "红黑树保持近似平衡",
        ],
        "quizzes": [
            {"q": "为什么普通 BST 可能退化为 O(n)？", "a": "按有序顺序插入时树会变成链表，高度变为 n。"},
            {"q": "红黑树与 AVL 的主要差异是什么？", "a": "红黑树平衡约束更宽松，插入删除旋转更少，查询略慢于 AVL。"},
        ],
    },
    {
        "key": "dsa-07",
        "title": "堆、优先队列与 Top-K 问题",
        "domain": "数据结构与算法",
        "tags": ["算法", "堆", "Top-K"],
        "concept": "堆是完全二叉树，分为大根堆与小根堆。堆顶始终是最大或最小元素，插入与删除堆顶为 O(log n)，建堆为 O(n)。Top-K 常用大小为 K 的堆维护候选集。",
        "principles": [
            "求最大 K 个元素使用大小为 K 的小根堆。",
            "堆排序时间 O(n log n)，原地但不稳定。",
            "优先队列通常基于堆实现。",
            "数据流场景无法全量排序时，堆是自然选择。",
        ],
        "example": """```python
import heapq

def top_k(nums, k):
    heap = []
    for value in nums:
        heapq.heappush(heap, value)
        if len(heap) > k:
            heapq.heappop(heap)
    return sorted(heap, reverse=True)

print(top_k([5, 1, 9, 3, 7], 2))   # [9, 7]
```""",
        "summary": [
            "堆只保证堆顶极值，不保证整体有序。",
            "Top-K 用大小为 K 的堆把空间降到 O(K)。",
            "建堆 O(n) 比逐个插入 O(n log n) 更高效。",
        ],
        "key_points": [
            "堆是完全二叉树",
            "插入与删除堆顶 O(log n)",
            "求最大 K 个元素使用小根堆",
            "Top-K 空间复杂度 O(K)",
        ],
        "quizzes": [
            {"q": "求最大的 K 个元素为什么使用小根堆？", "a": "堆顶是最小候选，新元素大于堆顶时替换，最终保留最大的 K 个。"},
            {"q": "堆排序的空间复杂度是多少？", "a": "O(1)，可以原地排序。"},
        ],
    },
    {
        "key": "dsa-08",
        "title": "图的 BFS、DFS 与最短路径",
        "domain": "数据结构与算法",
        "tags": ["算法", "图", "最短路径"],
        "concept": "图由顶点和边组成，可用邻接表或邻接矩阵表示。BFS 按层扩展，适合无权图最短路；DFS 适合连通性与回溯；Dijkstra 处理非负权最短路。",
        "principles": [
            "邻接表空间 O(V+E)，适合稀疏图。",
            "BFS 需要 visited 集合避免重复访问。",
            "Dijkstra 使用优先队列，不能处理负权边。",
            "负权边应使用 Bellman-Ford 或 SPFA 并检测负环。",
        ],
        "example": """```python
from collections import deque

def bfs(graph, start):
    visited = {start}
    queue = deque([(start, 0)])
    while queue:
        node, dist = queue.popleft()
        for nxt in graph[node]:
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, dist + 1))
    return visited
```""",
        "summary": [
            "BFS 适合无权最短路与层序问题。",
            "DFS 适合连通性、拓扑与回溯。",
            "Dijkstra 要求边权非负。",
        ],
        "key_points": [
            "邻接表适合稀疏图",
            "BFS 按层扩展可求无权最短路",
            "DFS 适合连通性与回溯",
            "Dijkstra 不能处理负权边",
        ],
        "quizzes": [
            {"q": "为什么 Dijkstra 不能处理负权边？", "a": "负权边可能使已确定的最短距离再次变小，破坏贪心正确性。"},
            {"q": "BFS 为什么需要 visited 集合？", "a": "图中可能存在环，visited 防止节点被重复入队与无限循环。"},
        ],
    },
    {
        "key": "net-01",
        "title": "TCP 三次握手与四次挥手",
        "domain": "计算机网络",
        "tags": ["网络", "TCP", "握手"],
        "concept": "TCP 通过三次握手建立连接，双方确认序列号与收发能力；通过四次挥手断开连接，分别关闭两个方向的数据流。",
        "principles": [
            "三次握手：SYN、SYN+ACK、ACK。",
            "两次握手无法确认客户端收到服务端的序列号。",
            "四次挥手因为 TCP 是全双工，两个方向需分别关闭。",
            "TIME_WAIT 等待 2MSL，确保旧报文消失并让对端收到最终 ACK。",
        ],
        "table": "| 阶段 | 方向 | 标志位 |\n|---|---|---|\n| 第一次 | 客户端→服务端 | SYN |\n| 第二次 | 服务端→客户端 | SYN+ACK |\n| 第三次 | 客户端→服务端 | ACK |",
        "example": """```text
客户端                         服务端
  | -------- SYN seq=x --------> |
  | <--- SYN+ACK seq=y ack=x+1 -- |
  | -------- ACK ack=y+1 ------> |
  |          连接建立             |
```""",
        "summary": [
            "三次握手确认双方收发能力与初始序列号。",
            "四次挥手分别关闭两个传输方向。",
            "TIME_WAIT 是保证可靠关闭的重要状态。",
        ],
        "key_points": [
            "三次握手建立连接",
            "两次握手无法确认服务端序列号",
            "TCP 全双工因此需要四次挥手",
            "TIME_WAIT 等待 2MSL",
        ],
        "quizzes": [
            {"q": "为什么 TCP 握手需要三次而不是两次？", "a": "需要让双方都确认对方收到自己的初始序列号，两次无法完成双向确认。"},
            {"q": "TIME_WAIT 状态的作用是什么？", "a": "确保最后一个 ACK 可重传，并让旧连接报文在网络中消失。"},
        ],
    },
    {
        "key": "net-02",
        "title": "TCP 可靠传输与拥塞控制",
        "domain": "计算机网络",
        "tags": ["网络", "TCP", "拥塞控制"],
        "concept": "TCP 通过序列号、确认应答、超时重传和滑动窗口保证可靠传输。拥塞控制根据网络状况调整发送速率，避免压垮网络。",
        "principles": [
            "累积确认表示已收到该序号之前的全部数据。",
            "快速重传在收到三个重复 ACK 后立即重发。",
            "慢启动指数增长拥塞窗口，达到阈值后线性增长。",
            "拥塞发生时窗口减小，常见算法包括 Reno、CUBIC、BBR。",
        ],
        "example": """```text
初始 cwnd = 1 MSS
慢启动：1 → 2 → 4 → 8 ...
达到 ssthresh 后进入拥塞避免，每个 RTT 增加 1 MSS
发生丢包时 ssthresh 减半，cwnd 重置
```""",
        "summary": [
            "可靠传输依赖序列号、ACK 与重传。",
            "滑动窗口兼顾可靠性与吞吐量。",
            "拥塞控制根据丢包或时延调整发送速率。",
        ],
        "key_points": [
            "序列号与 ACK 保证可靠传输",
            "三个重复 ACK 触发快速重传",
            "慢启动指数增长拥塞窗口",
            "拥塞发生时减小发送窗口",
        ],
        "quizzes": [
            {"q": "快速重传的触发条件是什么？", "a": "发送方收到三个重复 ACK，推测某报文丢失并立即重传。"},
            {"q": "慢启动阶段拥塞窗口如何增长？", "a": "每个 RTT 大约翻倍，呈指数增长，直到达到慢启动阈值。"},
        ],
    },
    {
        "key": "net-03",
        "title": "HTTP/1.1、HTTP/2 与 HTTP/3 的演进",
        "domain": "计算机网络",
        "tags": ["网络", "HTTP", "协议"],
        "concept": "HTTP/1.1 使用文本协议与持久连接；HTTP/2 引入二进制分帧、多路复用和头部压缩；HTTP/3 基于 QUIC，使用 UDP 减少握手与队头阻塞。",
        "principles": [
            "HTTP/1.1 的队头阻塞主要发生在应用层连接复用上。",
            "HTTP/2 多路复用让多个请求共享一个 TCP 连接。",
            "HTTP/2 仍受 TCP 层队头阻塞影响。",
            "HTTP/3 使用 QUIC，把可靠传输与加密结合在用户态。",
        ],
        "table": "| 版本 | 传输层 | 多路复用 | 典型优势 |\n|---|---|---|---|\n| HTTP/1.1 | TCP | 有限 | 兼容性好 |\n| HTTP/2 | TCP | 是 | 减少连接数 |\n| HTTP/3 | QUIC/UDP | 是 | 减少握手与队头阻塞 |",
        "example": """```text
HTTP/2 帧结构：长度(24bit) + 类型(8bit) + 标志(8bit) + 流ID(31bit) + 载荷
多个流共享同一连接，按流ID重组消息
```""",
        "summary": [
            "HTTP/2 解决了 HTTP 层队头阻塞。",
            "HTTP/3 进一步解决 TCP 层队头阻塞。",
            "协议升级需要服务端、CDN 与客户端共同支持。",
        ],
        "key_points": [
            "HTTP/1.1 使用文本协议",
            "HTTP/2 引入二进制分帧与多路复用",
            "HTTP/2 仍受 TCP 队头阻塞影响",
            "HTTP/3 基于 QUIC 与 UDP",
        ],
        "quizzes": [
            {"q": "HTTP/2 的多路复用解决了什么问题？", "a": "多个请求可共享一个连接并行传输，减少连接数与 HTTP 层队头阻塞。"},
            {"q": "HTTP/3 为什么能减少队头阻塞？", "a": "QUIC 在用户态实现独立流，单个流丢包不会阻塞其他流。"},
        ],
    },
    {
        "key": "net-04",
        "title": "HTTPS 与 TLS 握手",
        "domain": "计算机网络",
        "tags": ["网络", "HTTPS", "TLS"],
        "concept": "HTTPS 是 HTTP over TLS。TLS 通过非对称加密协商会话密钥，再用对称加密传输数据，并用证书验证服务器身份。",
        "principles": [
            "证书由受信任 CA 签发，包含公钥与域名信息。",
            "TLS 1.2 握手需要多个往返，TLS 1.3 缩减为 1-RTT 或 0-RTT。",
            "会话密钥用于对称加密，性能远高于非对称加密。",
            "HSTS 强制浏览器后续使用 HTTPS 访问。",
        ],
        "example": """```text
TLS 1.3 简化流程：
ClientHello（支持套件、密钥共享）
ServerHello（选定套件、证书、密钥共享）
双方推导会话密钥
Finished 后开始加密应用数据
```""",
        "summary": [
            "TLS 结合非对称协商与对称加密。",
            "证书解决身份信任问题。",
            "TLS 1.3 显著减少握手延迟。",
        ],
        "key_points": [
            "HTTPS 是 HTTP over TLS",
            "证书用于验证服务器身份",
            "会话密钥用于对称加密",
            "TLS 1.3 握手延迟更低",
        ],
        "quizzes": [
            {"q": "TLS 为什么同时使用非对称与对称加密？", "a": "非对称加密安全地协商密钥，对称加密高效传输大量数据。"},
            {"q": "证书在 HTTPS 中解决什么问题？", "a": "证明服务器公钥属于声称的域名，防止中间人冒充。"},
        ],
    },
    {
        "key": "net-05",
        "title": "DNS 解析过程与缓存机制",
        "domain": "计算机网络",
        "tags": ["网络", "DNS", "缓存"],
        "concept": "DNS 把域名解析为 IP。解析器依次查询本地缓存、系统缓存、递归解析器，再由递归解析器向根、顶级域和权威域名服务器查询。",
        "principles": [
            "递归解析器承担大部分查询工作并缓存结果。",
            "TTL 决定缓存时间，过短增加查询压力，过长影响变更生效。",
            "A 记录返回 IPv4，AAAA 返回 IPv6，CNAME 表示别名。",
            "DNS 污染与劫持可通过 DNSSEC、HTTPS  DNS 缓解。",
        ],
        "example": """```bash
nslookup example.com
dig +trace example.com
dig example.com A
dig example.com AAAA
```""",
        "summary": [
            "DNS 是分层分布式数据库。",
            "缓存显著减少解析延迟与根服务器压力。",
            "TTL 是可用性与变更速度之间的权衡。",
        ],
        "key_points": [
            "DNS 把域名解析为 IP",
            "递归解析器负责完整查询",
            "TTL 控制缓存时间",
            "A 记录对应 IPv4 AAAA 对应 IPv6",
        ],
        "quizzes": [
            {"q": "DNS 的 TTL 设置过短有什么影响？", "a": "缓存命中率下降，解析请求增多，延迟与权威服务器压力上升。"},
            {"q": "A 记录与 AAAA 记录的区别是什么？", "a": "A 记录返回 IPv4 地址，AAAA 记录返回 IPv6 地址。"},
        ],
    },
    {
        "key": "net-06",
        "title": "跨域、Cookie 与 SameSite",
        "domain": "计算机网络",
        "tags": ["网络", "CORS", "Cookie"],
        "concept": "浏览器的同源策略限制不同源之间的读取。CORS 通过响应头授权跨域请求；Cookie 的 SameSite 属性限制跨站发送，降低 CSRF 风险。",
        "principles": [
            "同源要求协议、域名和端口完全一致。",
            "简单请求先直接发送，非简单请求先发预检 OPTIONS。",
            "SameSite=Lax 允许顶级导航携带 Cookie，Strict 更严格。",
            "跨域携带凭据时 Access-Control-Allow-Origin 不能为 *。",
        ],
        "example": """```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Content-Type, Authorization

Set-Cookie: ssp_refresh=...; HttpOnly; Secure; SameSite=Lax; Path=/auth
```""",
        "summary": [
            "同源策略是浏览器安全边界。",
            "CORS 是服务端显式授权跨域读取的机制。",
            "SameSite 与 CSRF Token 共同防御跨站请求伪造。",
        ],
        "key_points": [
            "同源要求协议域名端口一致",
            "非简单请求会先发送预检",
            "跨域携带凭据时不能使用通配 Origin",
            "SameSite 限制跨站 Cookie 发送",
        ],
        "quizzes": [
            {"q": "为什么带凭据的跨域请求不能用 Access-Control-Allow-Origin: *？", "a": "浏览器禁止通配符与凭据同时使用，必须返回明确来源。"},
            {"q": "SameSite=Lax 的典型行为是什么？", "a": "同站请求携带 Cookie，跨站顶级导航的 GET 也可携带，其他跨站请求不携带。"},
        ],
    },
    {
        "key": "net-07",
        "title": "CDN、反向代理与缓存层级",
        "domain": "计算机网络",
        "tags": ["网络", "CDN", "反向代理"],
        "concept": "CDN 把静态资源分发到离用户更近的边缘节点。反向代理位于服务端前面，负责负载均衡、TLS 终止、缓存和访问控制。",
        "principles": [
            "静态资源适合长缓存并通过文件名哈希更新。",
            "动态接口通常使用短缓存或不缓存。",
            "反向代理可隐藏后端拓扑并统一处理 HTTPS。",
            "缓存键应包含影响响应的所有维度，如语言与版本。",
        ],
        "example": """```nginx
location /assets/ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}

location /api/ {
    proxy_pass http://backend;
    proxy_set_header X-Real-IP $remote_addr;
}
```""",
        "summary": [
            "CDN 优化静态资源的访问延迟。",
            "反向代理承担入口治理职责。",
            "缓存策略要区分静态资源与动态接口。",
        ],
        "key_points": [
            "CDN 把资源分发到边缘节点",
            "反向代理负责负载均衡与 TLS 终止",
            "静态资源适合长缓存",
            "缓存键应覆盖影响响应的维度",
        ],
        "quizzes": [
            {"q": "为什么静态资源常用文件名哈希做缓存失效？", "a": "内容变化时文件名变化，可安全设置长期缓存而无需手动清理。"},
            {"q": "反向代理相对正向代理的区别是什么？", "a": "反向代理代表服务端接收请求，正向代理代表客户端访问外部资源。"},
        ],
    },
    {
        "key": "os-01",
        "title": "进程、线程与协程的区别",
        "domain": "操作系统",
        "tags": ["操作系统", "进程", "线程"],
        "concept": "进程是资源分配的基本单位，拥有独立地址空间；线程是 CPU 调度的基本单位，共享进程资源；协程是用户态轻量级执行流，由程序主动切换。",
        "principles": [
            "进程隔离性强，通信需要 IPC。",
            "线程共享堆与文件描述符，但各自有栈和寄存器。",
            "线程切换需要内核参与，协程切换在用户态完成。",
            "协程适合高并发 I/O，但一个协程阻塞会影响同线程其他协程。",
        ],
        "table": "| 维度 | 进程 | 线程 | 协程 |\n|---|---|---|---|\n| 地址空间 | 独立 | 共享 | 共享 |\n| 切换成本 | 高 | 中 | 低 |\n| 隔离性 | 强 | 弱 | 弱 |",
        "example": """```text
进程 A ── 线程 A1
       └─ 线程 A2
线程 A1 ── 协程 1 / 协程 2（用户态调度）
```""",
        "summary": [
            "进程负责资源隔离，线程负责并行调度。",
            "协程降低切换成本，但依赖非阻塞编程模型。",
            "选择并发模型要结合任务类型与隔离需求。",
        ],
        "key_points": [
            "进程是资源分配基本单位",
            "线程是 CPU 调度基本单位",
            "线程共享进程资源",
            "协程在用户态切换",
        ],
        "quizzes": [
            {"q": "线程与进程最主要的区别是什么？", "a": "进程拥有独立地址空间，线程共享所属进程的地址空间与资源。"},
            {"q": "协程切换为什么成本低？", "a": "切换在用户态由程序控制，不需要进入内核完成上下文切换。"},
        ],
    },
    {
        "key": "os-02",
        "title": "进程调度算法与公平性",
        "domain": "操作系统",
        "tags": ["操作系统", "调度", "公平性"],
        "concept": "调度器决定哪个就绪进程获得 CPU。常见算法包括先来先服务、短作业优先、时间片轮转、优先级调度和多级反馈队列。",
        "principles": [
            "FCFS 简单但可能产生护航效应。",
            "SJF 平均等待时间短，但需要预知运行时间且可能饥饿。",
            "时间片轮转让交互任务获得响应性。",
            "多级反馈队列兼顾短任务、交互任务与长任务。",
        ],
        "example": """```text
时间片轮转（q=4）：
P1(10) P2(4) P3(2)
执行顺序：P1 P2 P3 P1 P1 P1
```""",
        "summary": [
            "调度算法在吞吐、响应与公平之间权衡。",
            "时间片大小影响上下文切换与交互体验。",
            "多级反馈队列是通用系统的常见选择。",
        ],
        "key_points": [
            "FCFS 可能产生护航效应",
            "SJF 平均等待时间短",
            "时间片轮转提升交互响应",
            "多级反馈队列兼顾多类任务",
        ],
        "quizzes": [
            {"q": "FCFS 的护航效应是什么？", "a": "长任务先到达时，后续短任务被迫等待，平均等待时间变长。"},
            {"q": "时间片设置过小会带来什么问题？", "a": "上下文切换过于频繁，调度开销占比上升。"},
        ],
    },
]