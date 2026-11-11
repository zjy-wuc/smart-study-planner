# Smart Study Planner 双 Token 认证模块开发学习总结

> **文档用途：** 课程答辩、项目复盘与技术学习\
> **项目名称：** 智能学习计划管理系统（Smart Study Planner）\
> **模块名称：** 用户身份认证与双 Token 会话管理\
> **技术栈：**
> Next.js、React、TypeScript、FastAPI、Python、SQLAlchemy、MySQL、JWT\
> **版本定位：** 双 Token 认证模块 V1.0\
> **说明：**
> 本文依据开发过程中已经讨论和展示的设计、代码及测试结果整理。对于尚未完成最终验收的项目，会明确标注为"待验收"或"待确认"，不将计划中的测试写成已经通过。

------------------------------------------------------------------------

# 一、项目背景与开发目标

## 1.1 为什么需要身份认证模块？

Smart Study Planner
是一个智能学习计划管理系统。用户可以创建学习计划、安排学习步骤、生成每日任务、记录打卡情况，并查看学习统计。

这些数据都属于具体用户，因此系统必须能够识别请求者的身份，并确保用户只能访问自己有权限访问的数据。

身份认证模块主要解决两个问题：

1.  **身份识别：** 当前发起请求的用户是谁？
2.  **访问控制：**
    当前用户是否已经通过身份验证，是否可以访问受保护的接口？

例如，用户访问 `GET /users/me`
时，后端不能仅仅相信前端传来的用户名，而应该验证请求携带的凭证，并从可信的认证信息中确定用户身份。

## 1.2 为什么不只使用一个 Token？

单 Token 认证通常是：用户登录后，后端签发一个
JWT，前端保存它，并在后续请求中携带。

这种方式实现简单，但需要权衡安全性和使用体验：

-   如果 Token 有效期很长，Token 泄露后可能在较长时间内被滥用。
-   如果 Token 有效期很短，用户就可能频繁重新登录。
-   如果没有服务端会话管理，服务端很难主动管理长期登录状态。

因此，本项目采用 Access Token 和 Refresh Token
两种令牌，将"访问业务接口"和"延续登录会话"分开。

## 1.3 双 Token 的核心设计

  ----------------------------------------------------------------------------
  对比维度                Access Token            Refresh Token
  ----------------------- ----------------------- ----------------------------
  主要用途                访问受保护的业务接口    申请新的 Token Pair

  使用频率                每次访问受保护接口时    Access Token 过期后

  有效期                  较短                    较长

  前端保存                当前版本使用            当前版本使用 localStorage
                          localStorage            

  后端验证                JWT 签名、有效期、Token JWT
                          类型等                  验证，并检查数据库会话记录

  是否用于业务接口        是                      否
  ----------------------------------------------------------------------------

**Access Token 负责访问资源，Refresh Token 负责延续登录会话。**

需要注意：双 Token 并不意味着 Refresh Token 可以直接访问业务接口。两种
Token 的用途必须严格区分，后端也要检查 Token 类型，避免将 Refresh Token
当成 Access Token 使用。

## 1.4 本模块的目标

本模块的目标包括：

1.  用户注册与登录。
2.  密码安全存储与验证。
3.  签发 Access Token 和 Refresh Token。
4.  通过 Access Token 保护业务接口。
5.  Access Token 过期后自动刷新。
6.  Refresh Token 轮换。
7.  检测旧 Refresh Token 重放。
8.  撤销当前会话。
9.  撤销当前用户的全部会话。
10. 前端统一处理 API 请求和认证错误。

------------------------------------------------------------------------

# 二、整体技术架构与搭建过程

## 2.1 技术栈与职责

  技术         在项目中的职责
  ------------ ---------------------------------
  Next.js      前端应用框架和页面路由
  React        组件、状态和页面交互
  TypeScript   前端类型约束
  FastAPI      提供后端 HTTP API
  Python       后端业务逻辑
  SQLAlchemy   数据库连接、SQL 执行和 ORM 能力
  MySQL        持久化保存用户与会话数据
  JWT          生成和验证令牌
  Apifox       接口调试与手动测试
  Trae         编写、检查和辅助调试代码

项目采用前后端分离架构。

### 前端负责

-   注册和登录页面。
-   保存和读取 Token。
-   统一发起 HTTP 请求。
-   在 Access Token 过期时刷新令牌。
-   对刷新后的请求进行一次重试。
-   处理退出登录和页面跳转。

### 后端负责

-   验证用户账号和密码。
-   签发 JWT。
-   验证 Access Token。
-   管理 Refresh Token 数据库记录。
-   执行 Token 轮换和撤销。
-   检测异常的旧 Token 重放。
-   为受保护接口提供当前用户身份。

### 数据库负责

-   保存用户基本信息。
-   保存 Refresh Token 的哈希值。
-   保存 Token Family、过期时间、撤销时间等会话状态。

## 2.2 后端目录组织

项目后端逐渐按职责拆分为以下结构：

``` text
back/
└── app/
    ├── api/
    │   ├── routes/
    │   │   ├── auth.py
    │   │   ├── system.py
    │   │   └── users.py
    │   └── router.py
    │
    ├── core/
    │   ├── security.py
    │   └── deps.py
    │
    ├── schemas/
    │   ├── user.py
    │   └── auth.py
    │
    ├── services/
    │   └── auth_service.py
    │
    ├── config.py
    ├── database.py
    ├── response.py
    └── main.py
```

各模块的职责：

-   `api/routes/`：定义 HTTP 接口，接收请求并返回响应。
-   `api/router.py`：集中注册路由。
-   `core/security.py`：处理密码哈希、JWT 创建与解码等安全逻辑。
-   `core/deps.py`：提供认证依赖，例如获取当前用户。
-   `schemas/`：定义请求和响应的数据结构。
-   `services/auth_service.py`：封装登录会话、刷新、轮换和撤销等业务逻辑。
-   `config.py`：读取数据库连接信息和密钥等配置。
-   `database.py`：管理数据库 Engine、Session 和依赖。
-   `response.py`：统一 API 响应格式。
-   `main.py`：创建 FastAPI 应用并注册路由、中间件和异常处理。

这样拆分的主要原因是**单一职责**：路由不必承载所有安全算法，安全模块也不需要直接处理页面交互。代码更容易测试、维护和定位问题。

## 2.3 前端目录组织

开发过程中使用的主要结构如下：

``` text
next-fro/
├── app/
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── register/
│   │       └── page.tsx
│   ├── profile/
│   │   └── page.tsx
│   ├── layout.tsx
│   └── page.tsx
│
├── components/
│   └── auth/
│       ├── LoginForm.tsx
│       └── UserProfile.tsx
│
├── lib/
│   ├── api/
│   │   └── client.ts
│   └── auth/
│       └── token.ts
│
├── services/
│   └── auth.service.ts
│
└── types/
    └── auth.ts
```

主要职责：

-   `app/`：Next.js App Router 页面路由。
-   `components/auth/`：登录表单、用户资料等界面组件。
-   `lib/auth/token.ts`：统一读写和删除 Token。
-   `lib/api/client.ts`：统一 HTTP 请求入口和自动刷新逻辑。
-   `services/auth.service.ts`：把认证业务接口封装成可复用函数。
-   `types/auth.ts`：集中定义请求、响应和用户数据类型。

`(auth)` 是 Next.js Route Group（路由组）。它用于组织页面，不会出现在
URL 中。因此 `app/(auth)/login/page.tsx` 对应的地址是 `/login`，而不是
`/(auth)/login`。

## 2.4 数据库连接的基本思路

后端通过 SQLAlchemy 连接
MySQL。项目配置中使用数据库主机、端口、数据库名、用户名和密码等参数。

数据库 Session 的基本生命周期是：

1.  请求到达后，依赖函数创建或提供一个 Session。
2.  路由或服务函数使用 Session 执行数据库操作。
3.  请求处理结束后关闭 Session。

`Depends(get_db)` 是 FastAPI
的依赖注入方式。路由函数不必自己在每个接口里重复创建和关闭数据库连接，而是声明需要数据库
Session，由框架调用依赖函数提供。

------------------------------------------------------------------------

# 三、后端核心知识点与实现原理

# 3.1 密码哈希：为什么不能直接保存密码？

用户注册时，不能将原始密码直接保存到数据库。

如果数据库发生泄露，明文密码会直接暴露用户凭证。因此，本项目使用密码哈希方案。

开发中使用的方案为 PBKDF2-HMAC-SHA256，并配置了随机盐和较高迭代次数。

基本过程：

1.  用户提交原始密码。
2.  后端生成随机 Salt（盐）。
3.  将密码、Salt 和迭代次数输入密码派生算法。
4.  得到哈希结果。
5.  将必要的算法参数、Salt 和哈希结果保存。
6.  登录时使用相同参数重新计算，再比较结果。

### Salt 的作用

Salt
是随机数据，用于避免相同密码总是得到相同哈希结果，也增加预计算攻击的成本。

### 为什么使用多次迭代？

密码派生算法会重复执行计算，使每次密码验证都需要一定成本。这样即使攻击者获得密码哈希数据库，也不能像普通快速哈希那样高效地尝试大量密码。

本项目开发中使用的 PBKDF2-HMAC-SHA256 配置为 600,000 次迭代、16
字节随机盐。正式部署时仍应根据运行环境和安全要求评估参数。

### 答辩表达

"用户注册时，系统不会保存明文密码，而是使用带随机盐的 PBKDF2
密码派生算法保存密码验证信息。用户登录时，系统重新计算并比较结果，从而降低数据库泄露后原始密码直接暴露的风险。"

# 3.2 JWT 的结构

JWT 通常由三部分组成：

``` text
Header.Payload.Signature
```

1.  Header：描述令牌类型和签名算法等信息。
2.  Payload：保存声明（Claims），例如用户 ID、签发时间、过期时间和 Token
    类型。
3.  Signature：根据 Header、Payload
    和密钥生成签名，用于检测内容是否被篡改。

本项目使用 HS256 签名算法。

需要特别说明：**JWT 的签名不等于加密。** 普通 JWT 的 Payload
通常可以被解码读取，因此不能把密码、数据库密码等敏感信息放入 Payload。

## 3.3 JWT 中的重要字段

项目使用或讨论过以下字段：

  字段     含义              用途
  -------- ----------------- ------------------------------------
  `sub`    Subject           表示令牌对应的用户主体
  `iat`    Issued At         令牌签发时间
  `exp`    Expiration Time   令牌过期时间
  `jti`    JWT ID            令牌唯一标识
  `type`   自定义声明        区分 Access Token 和 Refresh Token

### 为什么需要 `exp`？

JWT 需要过期时间，避免一个令牌无限期有效。

### 为什么需要 `iat`？

可以知道令牌何时签发，辅助审计和时间判断。

### 为什么需要 `jti`？

每个 Token 可以拥有独立标识。Refresh Token
记录与撤销逻辑需要区分不同令牌，因此唯一 ID 有助于令牌管理。

### 为什么需要 `type`？

Access Token 和 Refresh Token 都是
JWT，但用途不同。后端必须检查类型，不能只要签名正确就允许令牌访问所有接口。

# 3.4 Access Token 验证

访问受保护接口时，前端通过 Authorization 请求头提交 Access Token：

``` http
Authorization: Bearer <access_token>
```

后端验证时，重点检查：

1.  JWT 是否能够正确解码。
2.  签名是否有效。
3.  是否已经过期。
4.  Token 类型是否为 Access Token。
5.  用户是否存在、是否处于允许登录的状态。

验证失败时，后端返回适当的 HTTP 状态码和错误信息。

项目中区分了不同错误代码，例如：

-   `ACCESS_EXPIRED`：Access Token 已过期。
-   `INVALID_TOKEN`：Token 无效。
-   `TOKEN_TYPE_INVALID`：Token 类型不正确。

这样前端可以根据错误代码决定是否尝试刷新，而不是把所有 401 都理解为
Access Token 过期。

# 3.5 Refresh Token 为什么要保存到数据库？

JWT 本身可以独立验证，但如果只依赖 JWT，服务端不容易管理长期会话。

例如：

-   用户主动退出登录。
-   用户要求退出所有设备。
-   Refresh Token 已经被轮换。
-   旧 Refresh Token 再次出现。

因此，本项目为 Refresh Token 建立数据库记录。

## 3.6 `tb_refresh_token` 表设计

项目使用的 Refresh Token 表包含以下主要字段：

  字段            含义
  --------------- --------------------------------------
  `id`            记录主键
  `user_id`       所属用户
  `token_hash`    Refresh Token 的 SHA-256 哈希值
  `family_id`     所属会话家族标识
  `expires_at`    过期时间
  `revoked_at`    撤销时间
  `replaced_by`   替换该 Token 的新 Token 标识或关联值
  `created_at`    创建时间

表中还包含必要的索引和用户外键关系。

### 为什么数据库不保存 Refresh Token 明文？

如果数据库直接保存 Refresh Token
原文，数据库泄露后，攻击者可能直接获得仍然有效的刷新凭证。

因此，系统保存其 SHA-256 哈希值。

验证时：

1.  收到客户端提交的 Refresh Token。
2.  后端计算它的 SHA-256 哈希。
3.  使用计算结果查找数据库记录。
4.  判断记录是否存在、是否过期、是否已经撤销。

这样数据库中的记录不能直接作为原始 Refresh Token 使用。

需要注意：SHA-256 在这里用于对高随机性的 Token
做摘要索引，不是用于保存用户密码。密码哈希和 Token 哈希的安全目标不同。

# 3.7 Token Rotation：Refresh Token 轮换

Token Rotation（令牌轮换）是双 Token 设计中的重要机制。

假设用户当前拥有：

-   Access Token A1
-   Refresh Token R1

当 A1 过期，前端提交 R1。

后端验证 R1 后，不是简单地继续使用 R1，而是：

1.  验证 R1 的 JWT。
2.  计算 R1 的哈希并查询数据库。
3.  检查它是否存在、未过期且未撤销。
4.  撤销旧 Refresh Token R1。
5.  创建新的 Access Token A2。
6.  创建新的 Refresh Token R2。
7.  保存 R2 的哈希记录。
8.  将新 Token Pair 返回给前端。

前端收到结果后，使用 A2 和 R2 替换本地旧 Token。

过程可以表示为：

``` text
登录
  │
  ▼
Access A1 + Refresh R1
  │
  │ A1 过期
  ▼
提交 R1
  │
  ▼
后端验证 R1
  │
  ├── 撤销 R1
  ├── 创建 A2
  └── 创建 R2
  │
  ▼
返回 A2 + R2
  │
  ▼
前端替换本地 Token
```

轮换的价值在于：每次成功刷新后，旧 Refresh Token
都不再继续作为有效刷新凭证使用。

# 3.8 Token Family：为什么需要会话家族？

`family_id` 用来标识一条连续的刷新会话。

例如：

``` text
Family F1

R1 → R2 → R3 → R4
```

这些 Refresh Token 属于同一个 Family。

为什么需要这个概念？

假设系统发现 R1 已经被成功轮换，却又有人再次提交
R1。这意味着旧令牌被重复使用，可能是令牌泄露，也可能是客户端状态异常。

仅仅撤销当前的 R1 不够，因为同一个会话家族中可能已经存在 R2、R3
等后续令牌。

因此，系统可以根据 `user_id` 和 `family_id`，撤销这个 Family
中尚未撤销的 Refresh Token。

# 3.9 Replay Detection：重放检测

Replay Detection（重放检测）是对旧 Refresh Token 重复使用的检测。

正常流程：

``` text
R1 → 成功刷新 → R2
```

异常流程：

``` text
R1 → 已经轮换
R1 → 再次提交
```

如果系统发现一个已经撤销、且已经被替换的 Refresh Token
再次出现，就需要将其视为可疑重放。

本项目设计为撤销对应 Family 中仍有效的 Refresh Token。

### 为什么不是只撤销 R1？

因为 R1 已经不再是当前会话的唯一凭证。它可能已经产生了 R2、R3
等后续凭证。

如果只撤销 R1，后续令牌仍可能有效，无法达到控制整个可疑会话的目的。

### 答辩表达

"系统通过 Refresh Token 的轮换关系和 Family
标识识别旧令牌重放。一旦发现已轮换的旧令牌再次被使用，就撤销对应会话家族中尚未撤销的刷新令牌，以降低被盗令牌继续延续会话的风险。"

# 3.10 当前会话退出与全部会话退出

项目提供两种退出能力。

### 退出当前会话：`POST /auth/logout`

前端提交当前 Refresh Token。

后端定位对应记录，并撤销当前会话。

前端在请求结束后清理本地 Token。

### 退出全部会话：`POST /auth/logout-all`

这个接口通过当前用户的身份认证确定 `user_id`，再撤销该用户的全部有效
Refresh Token 会话。

两者的区别：

  功能         影响范围
  ------------ -----------------------------------
  logout       当前会话
  logout-all   当前用户的全部 Refresh Token 会话

### 本项目的 V1.0 设计取舍

项目选择了方案 A：

-   logout-all 撤销该用户全部 Refresh Token 会话。
-   不在每一次业务请求中额外查询数据库检查 Access Token
    所属会话是否已经撤销。
-   因此，已经签发的 Access Token 可能继续有效到自身过期。

这是有意接受的设计取舍，而不是遗漏。

它减少了每次业务请求的数据库检查成本，但不能实现所有设备上的 Access
Token 立即失效。该限制应在答辩中如实说明。

# 3.11 FastAPI 依赖注入与当前用户

FastAPI 的 `Depends` 用于依赖注入。

例如，受保护接口需要当前用户时，可以声明：

``` python
current_user = Depends(get_current_user)
```

`get_current_user` 的工作流程是：

1.  从请求头中提取 Bearer Token。
2.  解码并验证 Access Token。
3.  获取 Token 中的用户标识。
4.  查询用户是否存在。
5.  检查用户是否处于有效状态。
6.  返回当前用户信息。

这样每个业务路由不必重复编写完整认证逻辑。

例如，未来创建学习计划的接口可以依赖
`get_current_user`，由后端确定计划属于哪个用户，而不是直接相信前端提交的
`user_id`。

# 3.12 统一响应与异常处理

项目使用统一响应结构：

``` json
{
  "code": 200,
  "message": "success",
  "data": {},
  "detail": null
}
```

统一响应的好处：

-   前端不必为每个接口编写完全不同的解析方式。
-   成功和失败信息具有一致结构。
-   便于接口测试和调试。
-   可以保留 HTTP 状态码与业务错误信息。

需要区分：

-   HTTP 状态码表示 HTTP 请求处理结果。
-   响应体中的 `code`、`message`、`detail` 提供应用层信息。

项目的认证异常处理保留了 HTTP 状态码和具体错误代码，使前端能够识别
`ACCESS_EXPIRED` 等情况。

------------------------------------------------------------------------

# 四、前端核心知识点与实现原理

# 4.1 TypeScript 类型定义

前端使用 TypeScript 描述请求和响应结构。

例如：

-   `LoginRequest`：登录请求需要的用户名和密码。
-   `TokenPair`：后端返回的 Token 信息。
-   `User`：用户信息。
-   `ApiResponse<T>`：统一 API 响应结构。

泛型 `T` 允许同一种响应结构承载不同的数据类型。

例如：

-   `ApiResponse<User>` 表示响应中的 `data` 是用户信息。
-   `ApiResponse<TokenPair>` 表示响应中的 `data` 是 Token Pair。

这样可以减少数据结构使用错误，也让编辑器提供更准确的代码提示。

# 4.2 Token 存储模块

`lib/auth/token.ts` 统一管理 Token 的读取、写入和删除。

主要函数包括：

-   `setAccessToken`
-   `getAccessToken`
-   `removeAccessToken`
-   `setRefreshToken`
-   `getRefreshToken`
-   `setTokenPair`
-   `removeTokenPair`

为什么要单独封装？

如果每个页面都直接操作
`localStorage`，容易出现重复代码，也容易出现只更新 Access
Token、忘记更新 Refresh Token 的情况。

封装之后，其他模块只需要调用统一函数。

### 当前方案的安全取舍

V1.0 使用 localStorage 保存 Token，开发实现比较直接，但需要认识到：

-   localStorage 中的 Token 可以被同源 JavaScript 读取。
-   如果页面存在严重 XSS 漏洞，Token 可能被恶意脚本读取。
-   因此必须重视输入输出处理、依赖安全和 XSS 防护。

未来可以评估 HttpOnly、Secure、SameSite Cookie 等方案。它们也需要配合
CSRF 防护和正确的 Cookie 配置，不能简单理解为"换成 Cookie 就绝对安全"。

# 4.3 认证服务层 `auth.service.ts`

认证服务层负责封装具体认证 API。

主要函数：

  函数                  作用
  --------------------- --------------
  `registerUser`        注册用户
  `loginUser`           登录
  `getCurrentUser`      获取当前用户
  `logoutUser`          退出当前会话
  `logoutAllSessions`   退出全部会话

页面组件不必直接拼接每个接口的 URL 和请求格式，而是调用这些函数。

这种分层使页面更关注交互，服务层更关注 API 业务。

### 为什么登录使用 URLSearchParams？

项目的 FastAPI 登录接口使用 OAuth2 表单格式，因此前端使用
`URLSearchParams` 构造 `application/x-www-form-urlencoded` 请求体。

这与普通 JSON 请求不同。

关键是前后端必须约定一致的请求格式，否则即使账号密码正确，后端也可能无法按预期解析参数。

# 4.4 统一请求客户端 `apiFetch`

`lib/api/client.ts` 是前端认证请求的核心。

它将以下操作集中起来：

1.  获取当前 Access Token。
2.  设置请求头。
3.  发送 HTTP 请求。
4.  解析后端响应。
5.  判断是否为 Access Token 过期。
6.  必要时刷新 Token。
7.  使用新 Token 重试原请求。
8.  统一抛出 API 错误。

这样业务页面不必每次都自己处理 Token。

## 4.5 Authorization 请求头

对于需要身份认证的接口，前端会添加：

``` http
Authorization: Bearer <access_token>
```

后端通过 OAuth2 Bearer Token 机制提取令牌，再交给 `get_current_user`
验证。

# 4.6 Access Token 自动刷新

当受保护接口返回 401，并且后端明确返回：

``` text
detail.code = ACCESS_EXPIRED
```

前端才启动自动刷新流程。

大致过程：

``` text
业务请求
   │
   ▼
携带 Access Token
   │
   ▼
后端验证
   │
   ├── 正常 ──→ 返回业务数据
   │
   └── ACCESS_EXPIRED
             │
             ▼
       提交 Refresh Token
             │
             ▼
       获取新的 Token Pair
             │
             ▼
       更新本地 Token
             │
             ▼
       使用新 Access Token
       重试原请求一次
```

### 为什么不是所有 401 都刷新？

因为 401 可能有不同原因，例如：

-   Token 已过期。
-   Token 无效。
-   Token 类型错误。
-   用户凭证不存在或其他认证问题。

如果把所有 401 都当作 Access Token
过期，就可能产生无意义的刷新请求，甚至掩盖真正的认证错误。

因此，项目根据后端返回的 `ACCESS_EXPIRED` 精确判断。

# 4.7 Promise 与并发刷新控制

这是前端双 Token 中比较重要的知识点。

假设页面同时发起三个请求：

-   请求 A：获取用户信息。
-   请求 B：获取学习计划。
-   请求 C：获取每日任务。

如果 Access Token 已经过期，三个请求可能同时收到 401。

如果每个请求都单独调用刷新接口，就可能出现：

1.  A 使用 R1 刷新，得到 R2。
2.  B 也使用 R1 刷新。
3.  由于 R1 已经轮换，B 的请求可能被判定为旧 Token 重放。
4.  系统可能因此撤销整个 Family。

这就是并发刷新问题。

### 解决方式：共享一个 Promise

项目使用：

``` typescript
let refreshPromise: Promise<string | null> | null = null;
```

它表示当前正在执行的刷新任务。

逻辑是：

-   如果 `refreshPromise` 已存在，后续请求直接等待它。
-   如果不存在，则创建一次刷新任务。
-   所有请求共享这一个 Promise。
-   刷新完成后统一获得新 Access Token。
-   最后将 `refreshPromise` 清空。

示意：

``` text
请求 A ─┐
请求 B ─┼──→ 共享 refreshPromise
请求 C ─┘           │
                    ▼
               只刷新一次
                    │
                    ▼
               得到新 Token
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
        重试 A     重试 B     重试 C
```

这里涉及两个重要概念：

**Promise：** 表示一个未来可能完成或失败的异步任务。

**并发控制：**
多个请求同时需要刷新时，不重复执行相同操作，而是共享同一个任务。

需要注意，Promise 共享控制的是同一个前端 JavaScript
运行环境中的并发请求。它不是跨浏览器标签页、跨设备的全局锁。跨标签页场景仍可能需要额外设计。

# 4.8 为什么要比较旧 Token 和当前 Token？

项目中还处理了一个细节：

某个请求发出时使用的是旧 Access Token，但在它返回 401
之前，另一个请求可能已经完成刷新并更新了本地 Token。

因此，收到 401 后，不能总是重新使用旧 Refresh Token 刷新。

系统会比较：

-   发起原请求时的 `originalToken`。
-   当前 localStorage 中的 `currentToken`。

如果二者不同，说明可能已经有其他请求完成刷新，此时可以直接使用当前新
Access Token 重试，而不是再发起一次刷新。

这可以减少重复刷新，也降低旧 Refresh Token 被再次提交的风险。

# 4.9 为什么刷新请求使用原生 fetch？

`refreshAccessToken` 内部直接使用原生 `fetch`，而不是再次调用
`apiFetch`。

原因是：

`apiFetch` 本身包含自动刷新逻辑。如果刷新请求也经过
`apiFetch`，就可能形成递归：

``` text
apiFetch
  └── refreshAccessToken
        └── apiFetch
              └── refreshAccessToken
                    └── ...
```

使用原生 `fetch` 发送刷新请求，可以避免刷新逻辑再次触发自身。

# 4.10 为什么刷新失败要清除 Token？

如果 Refresh Token 已经过期、无效或被撤销，就无法继续延续当前登录会话。

此时前端清除本地 Token，避免后续请求持续携带无效凭证。

但需要区分：

-   清除本地 Token：浏览器不再保存当前凭证。
-   后端撤销会话：服务端数据库中的 Refresh Token 记录被撤销。

这两件事不是同一件事。

例如退出接口请求失败时，前端仍可以清理本地
Token，但不能因此声称后端一定成功撤销了会话。

# 4.11 ApiError：统一 API 错误类型

项目定义了 `ApiError`，保留：

-   `message`
-   `status`
-   `code`

这样页面可以区分不同错误。

例如：

-   HTTP 401：认证失败。
-   HTTP 403：没有访问权限。
-   网络异常：后端不可连接。
-   其他 HTTP 错误：根据状态码和响应信息处理。

用户资料页面中，401
可以触发清理凭证并跳转登录页；网络异常则显示网络错误，而不是误判成登录失效。

# 4.12 Next.js 页面与路由

项目使用 Next.js App Router。

登录页面位于：

``` text
app/(auth)/login/page.tsx
```

用户资料页面位于：

``` text
app/profile/page.tsx
```

登录表单是客户端交互组件，因此使用：

``` tsx
"use client";
```

登录成功后：

1.  调用 `loginUser`。
2.  从响应中取出 Access Token 和 Refresh Token。
3.  调用 `setTokenPair` 保存。
4.  使用 `router.replace("/profile")` 跳转。

`router.replace` 与 `router.push` 的区别是：`replace`
替换当前历史记录，用户点击浏览器后退时，不会简单地回到刚才的登录表单历史项。

------------------------------------------------------------------------

# 五、一次完整的认证流程

将前后端连接起来，可以得到完整流程。

## 5.1 用户注册

``` text
用户填写注册信息
       │
       ▼
Next.js 调用 registerUser
       │
       ▼
FastAPI 接收注册请求
       │
       ▼
验证数据并哈希密码
       │
       ▼
MySQL 保存用户信息
       │
       ▼
返回注册结果
```

## 5.2 用户登录

``` text
用户输入用户名和密码
       │
       ▼
前端调用 loginUser
       │
       ▼
后端查询用户
       │
       ▼
验证密码哈希
       │
       ▼
生成 Access Token
生成 Refresh Token
       │
       ▼
保存 Refresh Token 哈希记录
       │
       ▼
返回 Token Pair 和用户信息
       │
       ▼
前端保存两个 Token
       │
       ▼
跳转 /profile
```

## 5.3 访问受保护接口

``` text
前端请求 /users/me
       │
       ▼
携带 Access Token
       │
       ▼
后端验证 JWT
       │
       ▼
获取当前用户
       │
       ▼
返回用户信息
```

## 5.4 Access Token 过期

``` text
业务请求返回 ACCESS_EXPIRED
       │
       ▼
apiFetch 判断错误代码
       │
       ▼
共享 refreshPromise
       │
       ▼
提交 Refresh Token
       │
       ▼
后端验证并执行轮换
       │
       ▼
返回新 Token Pair
       │
       ▼
前端更新 Token
       │
       ▼
使用新 Access Token 重试原请求
```

## 5.5 退出登录

``` text
用户点击退出
       │
       ▼
提交当前 Refresh Token
       │
       ▼
后端撤销当前会话
       │
       ▼
前端清除本地 Token
       │
       ▼
跳转登录页
```

------------------------------------------------------------------------

# 六、开发过程中遇到的主要困难与解决思路

## 6.1 前后端请求格式不一致

### 问题

登录接口采用 OAuth2 表单格式，而其他接口通常使用 JSON。

如果前端统一使用 JSON 发送登录请求，后端可能无法正确解析用户名和密码。

### 解决

登录服务使用 `URLSearchParams`，并设置：

`Content-Type: application/x-www-form-urlencoded`

其他 JSON 接口则使用 `application/json`。

### 学到的知识

前后端接口不仅要约定 URL，还必须约定：

-   HTTP 方法。
-   请求头。
-   请求体格式。
-   字段名称。
-   返回数据结构。
-   错误格式。

## 6.2 Refresh Token 不能只靠 JWT 判断

### 问题

JWT 可以验证签名和有效期，但系统还需要主动撤销、轮换和管理会话。

### 解决

增加 `tb_refresh_token` 表，保存 Token
哈希、Family、过期时间和撤销状态。

### 学到的知识

JWT
解决令牌内容的完整性验证，数据库解决长期会话状态管理。二者配合才能实现项目需要的会话控制。

## 6.3 为什么要检测 Token 是否已经撤销？

### 问题

如果一个 Refresh Token 已经被轮换，旧 Token 理应不能再次使用。

如果后端只检查 Token 是否存在，而不检查撤销状态，就可能允许旧 Token
再次刷新。

### 解决

刷新时同时检查数据库记录是否存在、是否过期、是否撤销，并根据轮换关系识别重放。

### 学到的知识

认证系统不能只判断"令牌格式正确"，还必须判断"令牌当前是否仍然有效"。

## 6.4 为什么需要 Family？

### 问题

旧 Token 重放时，后续可能已经存在新 Token。如果只撤销旧
Token，后续令牌可能仍然有效。

### 解决

使用 `family_id` 把同一会话中连续轮换产生的 Refresh Token
关联起来。检测到重放时撤销对应 Family。

### 学到的知识

Family 将单个令牌的状态管理提升为一组相关会话令牌的管理。

## 6.5 并发刷新导致旧 Refresh Token 重复使用

### 问题

多个业务请求同时遇到 Access Token 过期时，可能同时提交同一个 Refresh
Token。

由于后端执行了轮换，后续刷新请求可能被当作重放。

### 解决

前端通过 `refreshPromise` 共享同一个刷新任务，并比较请求开始时的 Token
与当前 Token，尽量复用已经刷新的结果。

### 学到的知识

前端并发控制与后端 Token Rotation
是相互关联的。后端设计了轮换机制，前端也必须避免无意义的重复刷新。

## 6.6 为什么不能把所有 401 都当成过期？

### 问题

401 可能代表无效 Token、过期 Token 或其他认证失败。

### 解决

前端只在后端返回 `ACCESS_EXPIRED` 时尝试自动刷新。

### 学到的知识

前后端需要有明确的错误码契约，前端不能只凭 HTTP 状态码猜测具体原因。

## 6.7 如何区分网络错误与登录失效？

### 问题

后端断开时，前端也会请求失败。如果把所有失败都清除 Token
并跳转登录，就会让用户误以为账号失效。

### 解决

使用 `ApiError` 区分 HTTP
错误和普通网络异常。只有符合认证失败条件时才清理凭证或跳转。

### 学到的知识

错误处理不只是显示一条提示，还决定系统是否应该改变用户登录状态。

## 6.8 退出成功与本地清理不是一回事

### 问题

前端即使清除了 Token，也不能证明后端成功撤销了 Refresh Token。

### 解决

退出服务在请求结束时清理本地凭证；页面跳转与后端撤销结果的提示应分别处理。

### 学到的知识

客户端状态与服务端状态必须区分，不能用本地操作结果代替服务端操作结果。

------------------------------------------------------------------------

# 七、测试与验收

## 7.1 已经确认通过的基础前端测试

开发过程中，以下四项基础测试已由用户确认通过：

  编号   测试内容                                          已知结果
  ------ ------------------------------------------------- ----------
  B01    正常登录后保存 Token 并进入用户资料页面           通过
  B02    刷新 `/profile` 后仍能获取用户信息                通过
  B03    清除两个 Token 后访问 `/profile`，跳转 `/login`   通过
  B04    后端断开时显示网络错误，不误判为登录失效          通过

这些测试证明了基础登录、页面认证和网络错误区分流程已经得到验证。

## 7.2 需要纳入完整验收的测试范围

以下是双 Token
模块的完整验收范围。除前面明确确认通过的项目外，不能仅凭代码存在就认定测试已经通过。

  测试编号   测试内容                    重点检查
  ---------- --------------------------- ---------------------------------------
  T01        注册成功                    用户数据正确保存
  T02        重复用户名注册              正确处理唯一约束
  T03        正常登录                    返回 Token Pair
  T04        错误密码登录                不返回有效 Token
  T05        正常 Access Token           可以访问受保护接口
  T06        过期 Access Token           返回 `ACCESS_EXPIRED`
  T07        无效 Access Token           返回认证错误
  T08        Refresh Token 正常刷新      返回新 Token Pair
  T09        Refresh Token 轮换          旧 Refresh Token 被撤销
  T10        旧 Refresh Token 再次使用   检测重放并处理对应 Family
  T11        Refresh Token 过期          拒绝刷新
  T12        Refresh Token 类型错误      拒绝用于刷新
  T13        退出当前会话                当前 Refresh Token 被撤销
  T14        退出全部会话                当前用户全部 Refresh Token 会话被撤销
  T15        多个请求同时触发刷新        共享刷新任务，不重复刷新
  T16        刷新失败                    清理本地 Token 并正确处理错误
  T17        刷新后重试原请求            使用新 Access Token 重试一次
  T18        已经刷新后收到延迟 401      复用当前新 Token
  T19        后端网络不可用              不误判为 Token 过期
  T20        用户被禁用或不存在          不能继续访问受保护接口
  T21        前后端响应结构              状态码和错误信息保持一致

## 7.3 两项已发现、需要处理的问题

### P1：登录成功后没有跳转 `/profile`

验收报告指出当前实际行为与验收清单不一致，需要核对当前 `LoginForm.tsx`：

-   是否执行 `setTokenPair`。
-   是否在保存 Token 后执行 `router.replace("/profile")`。
-   是否存在提前返回或异常处理阻断跳转。
-   `/profile` 路由是否存在。

如果确实缺失，需要修复并重新测试。

### R1：SECRET_KEY 长度不足

检查发现当前 `SECRET_KEY` 只有 16 字节，建议更换为至少 32
字节的随机密钥。

可以在后端 Python 虚拟环境中生成：

``` bash
python -c "import secrets; print(secrets.token_hex(32))"
```

生成的 64 位十六进制字符串对应 32 字节随机数据。

更新 `.env` 后需要：

1.  确保 `.env` 不会被提交到 Git 仓库。
2.  重启后端。
3.  清除旧 Token 并重新登录。
4.  测试登录、访问用户信息和 Refresh Token 刷新。

更换密钥后，旧密钥签发的 JWT
无法通过新密钥验证，这是预期结果。不要将真实密钥写入报告或提交到
GitHub。

## 7.4 完整验收的原则

-   代码存在不等于功能已经通过测试。
-   单个接口通过不等于整个认证流程通过。
-   自动刷新需要验证真实过期场景。
-   并发刷新需要验证多个请求同时触发的场景。
-   重放检测需要验证旧 Token 再次使用时的行为。
-   安全配置需要检查实际运行配置，而不是只检查代码默认值。

------------------------------------------------------------------------

# 八、V1.0 的安全设计与已知限制

## 8.1 已采用的安全措施

1.  用户密码不以明文形式保存。
2.  JWT 使用签名验证完整性。
3.  Access Token 和 Refresh Token 使用不同类型标识。
4.  Access Token 有较短的有效期。
5.  Refresh Token 的数据库记录保存哈希，而不是原文。
6.  Refresh Token 使用轮换机制。
7.  对旧 Refresh Token 重放进行检测。
8.  支持撤销当前会话和全部 Refresh Token 会话。
9.  前端统一处理认证错误。
10. 刷新请求失败时清理本地 Token。

## 8.2 V1.0 的明确取舍

### localStorage

当前版本使用 localStorage 保存 Token。实现方便，但需要承担 XSS
风险。未来可以评估 HttpOnly Cookie 等方案，并同时设计 CSRF 防护。

### logout-all 与 Access Token

当前方案只撤销全部 Refresh Token 会话，不对每一次业务请求查询会话状态。

因此，已经签发的 Access Token 可能继续有效到自身过期。

### 多标签页并发

`refreshPromise` 主要解决同一页面 JavaScript
运行环境内的并发请求。多个浏览器标签页之间仍可能出现竞争，需要在未来按实际需求扩展。

### 刷新与数据库事务

Refresh Token 轮换涉及旧记录撤销、新记录创建和 Family
状态检查。正式部署时应重点检查事务边界、并发更新和数据库锁策略，避免两个并发请求同时把同一个旧
Token 当作有效凭证。

------------------------------------------------------------------------

# 九、项目开发过程中的核心收获

通过这次开发，学习到的不只是 JWT
的使用方法，还包括完整的前后端认证设计。

## 9.1 后端方面

-   理解密码哈希与普通哈希的区别。
-   理解 JWT 三段式结构和签名验证。
-   理解 Access Token 与 Refresh Token 的职责边界。
-   理解为什么 Refresh Token 需要数据库状态管理。
-   理解 Token Rotation、Family 和 Replay Detection。
-   理解 FastAPI 的依赖注入。
-   理解数据库 Session 的生命周期。
-   理解统一响应和异常处理的意义。

## 9.2 前端方面

-   理解 TypeScript 接口和泛型。
-   理解 localStorage 的读写。
-   理解 Promise 和异步请求。
-   理解统一 API 客户端的设计。
-   理解 HTTP 401 与业务错误码的区别。
-   理解并发刷新控制。
-   理解刷新失败、退出登录和网络错误的处理。
-   理解 Next.js App Router 和客户端路由跳转。

## 9.3 工程设计方面

这次开发让我认识到，一个认证模块不是几个接口的简单组合。

它涉及：

-   前后端接口契约。
-   数据库表设计。
-   令牌生命周期。
-   异常场景。
-   并发请求。
-   安全风险。
-   测试和验收。

真正可靠的功能，不仅要在正常情况下工作，还要考虑令牌过期、请求失败、重复提交、并发请求和用户主动退出等情况。

------------------------------------------------------------------------

# 十、课程答辩准备

## 10.1 一分钟项目介绍

本项目是智能学习计划管理系统中的双 Token 身份认证模块，采用 Next.js 和
TypeScript 实现前端，使用 FastAPI、SQLAlchemy 和 MySQL 实现后端。

系统采用 Access Token 与 Refresh Token 分离的认证机制。Access Token
用于访问受保护接口，Refresh Token 用于在 Access Token 过期后获取新的
Token Pair。

为了管理 Refresh Token 的生命周期，后端使用 MySQL 保存 Refresh Token
的哈希值，并通过 Token Rotation、Family 和 Replay Detection
实现令牌轮换与异常重放检测。

前端通过统一的 API 请求客户端实现自动刷新，并使用共享 Promise
控制并发刷新，避免多个请求同时使用旧 Refresh Token。

此外，系统支持退出当前会话和退出全部会话，为后续学习计划、每日任务和打卡等业务模块提供统一的身份认证基础。

## 10.2 老师可能提出的问题

### Q1：为什么使用双 Token，而不是单 Token？

答：单 Token 需要在有效期和安全性之间权衡。双 Token
将访问业务接口和延续登录会话分开，Access Token 有效期较短，Refresh Token
负责申请新令牌，可以减少用户频繁登录，同时提供更完善的会话管理能力。

### Q2：JWT 是否加密？

答：JWT 的签名主要用于验证令牌内容是否被篡改，不代表 Payload
一定被加密。普通 JWT 的 Payload 可以被解码，因此不能存放密码等敏感数据。

### Q3：为什么 Refresh Token 要存数据库？

答：因为系统需要管理令牌的有效状态，实现主动撤销、轮换和重放检测。单纯依赖
JWT 无法方便地管理这些长期会话状态。

### Q4：为什么数据库只保存 Refresh Token 的哈希？

答：降低数据库泄露时原始 Refresh Token 直接暴露的风险。客户端提交原始
Token 后，后端计算哈希，再与数据库记录进行匹配。

### Q5：什么是 Token Rotation？

答：每次成功使用 Refresh Token 刷新时，后端撤销旧 Refresh
Token，并签发新的 Access Token 和 Refresh Token。这样旧 Refresh Token
不会被无限重复使用。

### Q6：什么是 Token Family？

答：Family 用于标识同一会话中连续轮换产生的一组 Refresh Token。检测到旧
Token 重放时，可以撤销整个对应会话家族。

### Q7：为什么要使用 Promise 控制并发刷新？

答：多个业务请求可能同时遇到 Access Token
过期。如果每个请求都独立刷新，就可能重复提交同一个 Refresh
Token。共享一个 Promise 可以让多个请求等待同一次刷新结果。

### Q8：为什么不对所有 401 自动刷新？

答：401 不一定代表 Access Token 过期，也可能是 Token
无效或其他认证错误。系统只在后端明确返回 `ACCESS_EXPIRED`
时刷新，避免错误处理。

### Q9：退出全部设备后，Access Token 会立即失效吗？

答：当前 V1.0 方案不会保证 Access Token 立即失效。logout-all
会撤销用户全部 Refresh Token
会话，但业务请求不额外查询会话状态，因此已经签发的 Access Token
可能继续有效到自身过期。这是当前版本的性能与即时撤销能力之间的设计取舍。

### Q10：localStorage 保存 Token 是否绝对安全？

答：不是。localStorage 中的数据可被同源 JavaScript 读取，因此存在 XSS
风险。当前版本采用该方案便于实现，后续可以评估 HttpOnly
Cookie，并配套考虑 CSRF 防护。

### Q11：为什么不能只在前端删除 Token 就算退出成功？

答：前端删除 Token 只改变浏览器本地状态，不代表服务端数据库中的 Refresh
Token 已经撤销。真正的服务端会话撤销需要后端成功处理。

### Q12：本模块后续如何扩展？

答：后续可以将当前用户认证依赖应用到学习计划、学习步骤、每日任务和打卡接口，确保每条业务数据都与用户身份关联。同时可以进一步评估
HttpOnly Cookie、多标签页刷新协调和更严格的会话撤销机制。

------------------------------------------------------------------------

# 十一、最终总结

本次双 Token
认证模块开发，完成了从用户注册、登录到令牌签发、验证、刷新、轮换和撤销的整体设计与实现。

它不仅实现了基础身份认证，还处理了真实系统中容易被忽略的问题：

-   Refresh Token 的安全存储。
-   旧令牌重复使用。
-   同一会话的令牌关联。
-   多请求并发刷新。
-   网络异常与认证失效的区分。
-   当前会话和全部会话的退出。

通过这次开发，我对前后端分离项目中的认证流程有了更完整的认识，也理解了安全设计不是简单地引入一个
JWT
库，而是需要从令牌生命周期、数据库状态、前端并发和异常处理等多个角度共同设计。

**模块最终结项条件：** 完成 P1 登录成功跳转问题的核查与必要修复，更新 R1
`SECRET_KEY`，并完成对应回归测试和完整验收。通过后正式标记为"双 Token
认证模块 V1.0 完成"。

下一阶段可以在该认证基础上开发核心业务模块：

``` text
用户身份认证
      │
      ▼
学习计划管理
      │
      ▼
学习步骤管理
      │
      ▼
日期安排与每日任务
      │
      ▼
每日打卡
      │
      ▼
学习统计与总结
```

这次开发最重要的收获是：**不仅要让代码运行起来，还要能够解释为什么这样设计、异常情况下会发生什么，以及如何证明功能确实符合预期。**
