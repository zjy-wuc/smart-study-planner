"""笔记内容 C2：前端工程化、英语四六级与雅思（12 篇）。"""

NOTES = [
    {
        "key": "react-09",
        "title": "前端工程化：构建、分包与环境变量",
        "domain": "React 与 Next.js",
        "tags": ["React", "工程化", "构建"],
        "concept": "现代前端工程化包括依赖管理、构建打包、代码分割、环境变量和持续集成。构建工具把源码转换为浏览器可执行的静态资源，并通过分包优化加载性能。",
        "principles": [
            "依赖锁文件保证不同环境安装结果一致。",
            "代码分割按路由或组件懒加载，减少首屏体积。",
            "环境变量只暴露以特定前缀开头的公开变量，密钥不能进入前端包。",
            "构建产物应带内容哈希，便于长期缓存。",
        ],
        "example": """```jsx
const Chart = dynamic(() => import("./Chart"), {
  loading: () => <Skeleton />,
  ssr: false,
});

// 只有 NEXT_PUBLIC_ 前缀的变量会进入浏览器端
const apiBase = process.env.NEXT_PUBLIC_API_BASE;
```""",
        "summary": [
            "锁文件与固定 Node 版本保证构建可复现。",
            "代码分割降低首屏传输体积。",
            "前端环境变量是公开的，不能存放密钥。",
        ],
        "key_points": [
            "锁文件保证依赖版本一致",
            "代码分割按路由或组件懒加载",
            "前端环境变量会被打包公开",
            "构建产物使用内容哈希",
        ],
        "quizzes": [
            {"q": "为什么不能把数据库密码写进前端环境变量？", "a": "前端环境变量会打包进浏览器资源，任何用户都可以查看。"},
            {"q": "代码分割的主要收益是什么？", "a": "减少首屏加载体积，按需加载非关键代码。"},
        ],
    },
    {
        "key": "cet-01",
        "title": "四级听力：场景预判与信号词",
        "domain": "英语四六级",
        "tags": ["四级", "听力", "应试"],
        "concept": "四级听力以校园、职场、旅行和新闻场景为主。提前浏览选项可以预判话题与问题类型，听音时重点捕捉转折、因果和数字信号词。",
        "principles": [
            "选项中的名词和动词决定听音关注点。",
            "but、however、instead 后常出现答案。",
            "数字、时间、地点容易设置干扰项，需要边听边记。",
            "新闻听力关注首句导语，常概括主旨。",
        ],
        "example": """```text
选项：
A. The meeting was canceled.
B. The meeting was postponed.
C. The meeting was moved online.

听音信号：But the manager decided to put it off until Friday.
→ postponed（put off 同义替换）
```""",
        "summary": [
            "预读选项是最有效的听力准备。",
            "转折与因果信号词后常是考点。",
            "同义替换是四级听力的核心命题方式。",
        ],
        "key_points": [
            "预读选项可预判话题",
            "转折词后常出现答案",
            "数字时间地点易设干扰",
            "新闻首句常含主旨",
        ],
        "quizzes": [
            {"q": "听力中 but、however 之后通常出现什么？", "a": "往往出现说话人真正的观点或答案信息。"},
            {"q": "为什么要注意同义替换？", "a": "正确选项常使用与原文不同但意义相同的表达。"},
        ],
    },
    {
        "key": "cet-02",
        "title": "四级阅读：定位、同义替换与排除法",
        "domain": "英语四六级",
        "tags": ["四级", "阅读", "技巧"],
        "concept": "阅读理解的核心是快速定位与准确比对。先读题干划关键词，再回原文定位，最后比较选项与原文的表达差异。",
        "principles": [
            "题干关键词优先选择专有名词、数字和独特动词。",
            "正确选项通常是原文的同义改写，而非原词照搬。",
            "绝对化表达（all、never、only）往往是干扰项。",
            "主旨题关注首尾段与各段主题句。",
        ],
        "example": """```text
原文：Regular exercise can significantly reduce the risk of heart disease.
题干：What is a benefit of regular exercise?
正确项：It lowers the chance of developing heart problems.
（reduce the risk ≈ lower the chance）
```""",
        "summary": [
            "先题干后原文，避免通读全文耗时。",
            "同义替换是正确项的常见特征。",
            "排除法与主旨句定位能提高准确率。",
        ],
        "key_points": [
            "先读题干划关键词",
            "正确项常为同义改写",
            "绝对化表达常是干扰项",
            "主旨题关注首尾段",
        ],
        "quizzes": [
            {"q": "阅读中为什么原词照搬的选项常常不是答案？", "a": "命题人常用同义替换设置正确项，原词照搬可能是偷换概念的干扰项。"},
            {"q": "主旨题应优先关注哪些位置？", "a": "首段、尾段以及各段主题句。"},
        ],
    },
    {
        "key": "cet-03",
        "title": "四级写作：三段式结构与论证展开",
        "domain": "英语四六级",
        "tags": ["四级", "写作", "结构"],
        "concept": "四级写作常用三段式：引言提出观点，主体给出两到三个理由并举例，结论总结并升华。清晰结构比复杂词汇更能保证分数。",
        "principles": [
            "引言段用现象或问题引出明确立场。",
            "主体段每段一个中心句，后接解释与例子。",
            "使用 first、moreover、therefore 等连接词增强逻辑。",
            "结论不要引入新观点，重申立场并给出建议。",
        ],
        "example": """```text
Nowadays, more college students choose to study online.
From my perspective, this trend brings both convenience and challenges.

First, online learning saves time and offers flexible schedules.
Moreover, it provides access to high-quality courses from anywhere.
However, it also requires strong self-discipline.

In conclusion, online learning is a valuable supplement,
and students should learn to manage their time wisely.
```""",
        "summary": [
            "结构清晰、论点明确是写作得分基础。",
            "每个主体段遵循中心句、解释、例子的顺序。",
            "连接词让论证关系更易读。",
        ],
        "key_points": [
            "三段式结构清晰",
            "主体段每段一个中心句",
            "使用连接词增强逻辑",
            "结论重申观点不引入新论点",
        ],
        "quizzes": [
            {"q": "四级写作主体段通常如何展开？", "a": "先写中心句，再解释原因，最后给出例子或结果。"},
            {"q": "结论段应该避免什么？", "a": "避免引入新的观点或展开新的论证。"},
        ],
    },
    {
        "key": "cet-04",
        "title": "四级翻译：拆分意群与调整语序",
        "domain": "英语四六级",
        "tags": ["四级", "翻译", "语序"],
        "concept": "汉译英的关键是先拆分意群，确定主干，再处理修饰成分。中文多短句并列，英文常用从句、非谓语和介词短语连接。",
        "principles": [
            "先找主语和谓语，保证句子有完整主干。",
            "中文的定语常前置，英文长定语常后置或用从句。",
            "避免逐字翻译，优先表达原意。",
            "遇到不会的词用上位词或解释性表达替代。",
        ],
        "example": """```text
中文：随着互联网的发展，越来越多的人开始在线学习。
拆分：随着互联网的发展 / 越来越多的人 / 开始在线学习
英文：With the development of the Internet,
more and more people are beginning to learn online.
```""",
        "summary": [
            "拆分意群能降低长句翻译难度。",
            "先保证主干正确，再优化修饰。",
            "意译优于生硬直译。",
        ],
        "key_points": [
            "先拆分意群再确定主干",
            "中文定语常需转换为英文后置修饰",
            "避免逐字直译",
            "不会的词可用解释性表达",
        ],
        "quizzes": [
            {"q": "汉译英时第一步应该做什么？", "a": "拆分意群并找出句子的主干（主语和谓语）。"},
            {"q": "中文长定语翻译成英文时通常如何处理？", "a": "转换为后置定语、从句或介词短语。"},
        ],
    },
    {
        "key": "cet-05",
        "title": "六级词汇：词根、搭配与语境记忆",
        "domain": "英语四六级",
        "tags": ["六级", "词汇", "搭配"],
        "concept": "六级词汇不应孤立背诵，而应结合词根词缀、常见搭配和语境例句。掌握搭配能避免认识单词却用错的情况。",
        "principles": [
            "词根词缀帮助推断生词含义。",
            "动词与介词/名词的固定搭配需要整体记忆。",
            "通过例句记忆能同时掌握用法与语感。",
            "定期复习比一次性大量背诵更有效。",
        ],
        "example": """```text
词根：spect（看）
inspect 检查；respect 尊重；prospect 前景；retrospect 回顾

搭配：
take measures 采取措施
pose a threat 构成威胁
be attributed to 归因于
```""",
        "summary": [
            "词根词缀提升猜词与记忆效率。",
            "搭配是词汇能力的重要组成部分。",
            "语境与间隔复习能提高长期记忆。",
        ],
        "key_points": [
            "词根词缀帮助推断词义",
            "固定搭配需要整体记忆",
            "例句能同时提供用法与语境",
            "间隔复习优于集中突击",
        ],
        "quizzes": [
            {"q": "为什么只背单词中文意思不够？", "a": "实际使用还需要掌握搭配、词性和语境，否则容易用错。"},
            {"q": "词根 spect 的含义是什么？", "a": "看，例如 inspect、respect、prospect 都与看或视角有关。"},
        ],
    },
    {
        "key": "cet-06",
        "title": "六级阅读：长难句拆解与逻辑关系",
        "domain": "英语四六级",
        "tags": ["六级", "阅读", "长难句"],
        "concept": "六级阅读长难句常包含从句、非谓语和插入语。拆解时先找主句主干，再识别修饰成分与逻辑连接，避免被细节干扰。",
        "principles": [
            "先找主句的主语、谓语和宾语。",
            "that、which、who 引导的从句通常修饰前面的名词。",
            "插入语常用逗号或破折号隔开，可暂时跳过。",
            "转折、因果和让步关系决定作者态度。",
        ],
        "example": """```text
原文：The assumption that economic growth automatically
improves public health, which was long taken for granted,
has been challenged by recent studies.

主干：The assumption has been challenged.
修饰：that ... 解释 assumption；which ... 修饰前句内容。
```""",
        "summary": [
            "长难句先抓主干再处理修饰。",
            "插入语可以暂时跳过不影响主干理解。",
            "逻辑关系词帮助判断作者态度与论点。",
        ],
        "key_points": [
            "先找主句主干",
            "从句通常修饰前面的名词",
            "插入语可暂时跳过",
            "逻辑关系决定作者态度",
        ],
        "quizzes": [
            {"q": "分析长难句的第一步是什么？", "a": "找出主句的主语、谓语和宾语，确定核心意思。"},
            {"q": "插入语在阅读中应如何处理？", "a": "可先跳过，抓住主干后再回看其补充信息。"},
        ],
    },
    {
        "key": "ielts-01",
        "title": "雅思听力：填空题的预判与拼写",
        "domain": "雅思",
        "tags": ["雅思", "听力", "填空"],
        "concept": "雅思听力填空题要求边听边写。读题时预判答案词性、单复数和字数限制，听音时定位同义替换并准确拼写。",
        "principles": [
            "注意题目中的字数限制，如 NO MORE THAN TWO WORDS。",
            "根据空格前后词判断答案是名词、动词还是数字。",
            "答案通常按题目顺序出现。",
            "拼写错误会直接失分，需专项练习高频词。",
        ],
        "example": """```text
题目：The course begins on ______.
预判：日期或星期
听音：It actually starts on the 15th of March.
答案：15 March（注意字数限制）
```""",
        "summary": [
            "预判词性可以显著提高抓词准确率。",
            "同义替换是定位答案的关键。",
            "拼写与字数限制是常见失分点。",
        ],
        "key_points": [
            "注意字数限制",
            "根据上下文预判词性",
            "答案通常按题序出现",
            "拼写错误会直接失分",
        ],
        "quizzes": [
            {"q": "雅思听力填空题读题时应预判什么？", "a": "答案的词性、单复数、数字形式和字数限制。"},
            {"q": "为什么拼写错误影响很大？", "a": "听力填空按答案精确判分，拼写错误通常视为错误。"},
        ],
    },
    {
        "key": "ielts-02",
        "title": "雅思阅读：True/False/Not Given 判断",
        "domain": "雅思",
        "tags": ["雅思", "阅读", "判断题"],
        "concept": "True/False/Not Given 考查原文与题干的逻辑关系。True 表示一致，False 表示矛盾，Not Given 表示原文没有足够信息判断。",
        "principles": [
            "不要用常识补充原文未提供的信息。",
            "题干出现绝对化词时要特别核对原文程度。",
            "False 是原文与题干明确矛盾，Not Given 是无法判断。",
            "先定位题干关键词，再精读相关句。",
        ],
        "example": """```text
原文：Some studies suggest that moderate coffee consumption
may reduce the risk of heart disease.
题干：Coffee definitely prevents heart disease.
判断：False（may reduce ≠ definitely prevents）
```""",
        "summary": [
            "判断题严格基于原文信息。",
            "区分矛盾与未提及是核心难点。",
            "绝对化表达常导致 False。",
        ],
        "key_points": [
            "True 表示与原文一致",
            "False 表示与原文矛盾",
            "Not Given 表示原文无法判断",
            "不要用常识补充信息",
        ],
        "quizzes": [
            {"q": "Not Given 与 False 的区别是什么？", "a": "False 是原文与题干明确矛盾，Not Given 是原文没有足够信息判断。"},
            {"q": "题干出现 definitely 时应如何判断？", "a": "回到原文核对语气强度，若原文只是 may 或 some studies，则通常为 False。"},
        ],
    },
    {
        "key": "ielts-03",
        "title": "雅思写作 Task 2：论证结构与连贯性",
        "domain": "雅思",
        "tags": ["雅思", "写作", "Task 2"],
        "concept": "Task 2 要求就社会议题表达立场并展开论证。高分作文需要清晰立场、充分展开的主体段和自然的衔接，而不是堆砌高级词汇。",
        "principles": [
            "引言段改写题目并明确立场。",
            "主体段采用论点、解释、例子的 PEEL 结构。",
            "每个主体段只聚焦一个中心论点。",
            "结论段总结主要论点，不引入新信息。",
        ],
        "example": """```text
题目：Some people think universities should focus on
academic subjects rather than practical skills. Discuss.

立场：两者应结合。
主体段 1：学术科目培养长期研究能力。
主体段 2：实践技能提升就业适应力。
结论：课程设计应兼顾理论与实践。
```""",
        "summary": [
            "明确立场与连贯论证比词汇华丽更重要。",
            "PEEL 结构能保证主体段充分展开。",
            "结论段应回应题目而非另起话题。",
        ],
        "key_points": [
            "引言段改写题目并表明立场",
            "主体段使用 PEEL 结构",
            "每段只聚焦一个中心论点",
            "结论段不引入新信息",
        ],
        "quizzes": [
            {"q": "Task 2 主体段的 PEEL 结构指什么？", "a": "Point 论点、Explain 解释、Example 例子、Link 回扣主题。"},
            {"q": "为什么每个主体段只应有一个中心论点？", "a": "保证论证充分且逻辑清晰，避免段落主题分散。"},
        ],
    },
    {
        "key": "ielts-04",
        "title": "雅思口语 Part 2：素材法与一分钟准备",
        "domain": "雅思",
        "tags": ["雅思", "口语", "Part 2"],
        "concept": "Part 2 要求就提示卡连续陈述约两分钟。高效准备方法是使用可迁移素材，把人物、地点、事件和物品串成故事，而不是每题从零构思。",
        "principles": [
            "一分钟准备时写下关键词而非完整句子。",
            "按时间顺序或空间顺序组织内容。",
            "加入感受与评价，避免只罗列事实。",
            "准备两到三个万能素材，覆盖多类题目。",
        ],
        "example": """```text
提示卡：Describe a person who helped you.
关键词：
who: my first programming teacher
when: senior high school
what: encouraged me to debug step by step
feeling: patient, important turning point
```""",
        "summary": [
            "关键词笔记比背稿更自然。",
            "可迁移素材能降低准备负担。",
            "感受与评价让回答更有深度。",
        ],
        "key_points": [
            "准备时写关键词而非完整句子",
            "按时间或空间顺序组织",
            "加入感受与评价",
            "准备可迁移的万能素材",
        ],
        "quizzes": [
            {"q": "Part 2 一分钟准备时应该写什么？", "a": "写关键词和结构提示，而不是完整句子或背稿。"},
            {"q": "为什么建议准备可迁移素材？", "a": "同一段经历可以适配人物、事件、地点等多类题目，降低临场构思压力。"},
        ],
    },
    {
        "key": "ielts-05",
        "title": "雅思写作 Task 1：图表描述与数据对比",
        "domain": "雅思",
        "tags": ["雅思", "写作", "Task 1"],
        "concept": "Task 1 要求客观描述图表的主要特征与趋势，不解释原因。结构通常为引言改写、概述、两到三段细节对比。",
        "principles": [
            "概述段必须包含最显著的趋势或差异。",
            "细节段按时间、类别或高低分组。",
            "使用上升、下降、波动、持平等等替代表达。",
            "不要加入个人观点或原因分析。",
        ],
        "example": """```text
The line graph compares the number of online and offline
course enrollments from 2018 to 2023.

Overall, online enrollments rose steadily, while offline
numbers fluctuated and eventually declined.

In 2018, offline courses were more popular...
By 2023, online enrollments had overtaken offline ones...
```""",
        "summary": [
            "Task 1 的核心是客观概述与数据对比。",
            "概述段应突出最显著特征。",
            "避免原因分析与主观评价。",
        ],
        "key_points": [
            "Task 1 只描述不解释原因",
            "概述段突出最显著趋势",
            "细节段按时间或类别分组",
            "使用趋势词进行同义替换",
        ],
        "quizzes": [
            {"q": "Task 1 的概述段应该包含什么？", "a": "图表最显著的整体趋势、差异或极值。"},
            {"q": "Task 1 可以分析数据变化的原因吗？", "a": "不可以，Task 1 只要求客观描述图表信息。"},
        ],
    },
]