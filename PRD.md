# 企业智能检索系统 PRD

## 1. 背景与目标

现有的 `enterprise-kb-agent` 原型验证了"多 Agent + 溯源 + 流程可视化"这条路子是对的，但存在两个问题：
1. 单次问答最多串行调用 4~5 次 LLM（Planner→Synthesis→Critic→修订→再 Critic），慢。
2. 没有部门/员工/权限体系，也没有文档管理界面，只是硬编码 9 篇文档的 demo。

`deer-flow` 是效果验证过的多 Agent 框架，已经有现成的认证系统（JWT + RBAC）、SSE 流式推送、前端 citation 溯源解析、`@xyflow/react` 可视化组件。

本项目目标：**新建一个独立项目**，复用 deer-flow 和 enterprise-kb-agent 里能直接搬的部分，重新设计一条更短、更快、可流式展示的 Agent 链路，加上部门/员工/文档管理后台。

**产品命名**：对外/对用户可见的一切界面文案统一用「企业智能检索系统」，不出现 `deer-flow`、`deerflow`、`enterprise-kb-agent` 等来源项目名或版本号——这些只是内部技术调研/复用的参照对象，不是产品身份。

## 2. 关键决策（已与用户确认）

| 决策项 | 选择 | 说明 |
|---|---|---|
| 检索方案 | BM25 + 本地 embedding 混合 | 兼顾语义召回和速度，不依赖付费向量检索 API |
| 部门隔离方式 | 按部门物理隔离检索库 | 每个部门一份独立索引，员工只能检索到自己所属部门的文档；跨部门员工可合并检索多个授权部门 |
| LLM 接入 | 复用 deer-flow 的模型配置理念 | 走 `.env` + 配置文件指定 API Key/Base URL/模型名，默认使用 NewAPI 网关的 `gpt-5.6-sol` |
| 密码存储 | 对称加密可解密存储 | 管理员后台需要展示账号密码原文，与 deer-flow 现成的 bcrypt 不可逆哈希冲突，改用可解密加密（见 §8 风险提示） |
| 项目组织方式 | 全新独立项目，按需复制代码 | 不直接改动 deer-flow / enterprise-kb-agent 源码，只搬运可复用的设计和片段 |

## 3. 用户角色与核心场景

**管理员（admin）**
- 登录后台，创建/管理部门
- 在部门下添加/编辑/删除员工，创建时可勾选多个所属部门并填写各部门职位，能看到员工的账号和密码（明文）
- 管理部门下的知识库文档：增删改查
- （可选）也能以"上帝视角"提问，检索全部部门文档

**员工（employee）**
- 用管理员分配的账号密码登录，可访问管理员分配的多个部门知识库
- 在问答页面提问，看到右侧 Agent 执行流程实时点亮，中间流式看到回答
- 回答中的每个结论都能点击溯源到具体文档
- 能看到自己部门已有的文档列表（只读）
- 可维护仅自己可见的回答偏好记忆，并设置新会话默认上下文档位
- 可在每个会话选择五档上下文深度，并在授权部门内选择一个或多个文档

## 4. 功能范围

### 4.1 管理员后台
- 部门管理：部门列表、新建部门
- 员工管理（部门详情页内）：员工列表（账号、所属部门/职位、密码明文展示，带"复制"按钮）、新建员工（可多选部门）、删除员工、重置密码
- 文档管理（部门详情页内）：文档列表（标题、分类、是否敏感、更新时间）、新增文档（粘贴文本或上传 .txt/.md）、编辑、删除
- 部门记忆管理（部门详情页内）：新增、编辑、启用/停用、删除部门回答规范；仅管理员可维护

### 4.2 员工问答页
- 左侧：所属部门文档列表（只读，供员工知道"知识库里有什么"）和历史会话
- 中间：对话面板，流式输出回答，回答内引用角标可点击展开来源卡片（文档标题+片段原文+更新时间）
- 右侧：Agent 执行流程可视化面板（4 个 Agent 节点随 SSE 事件实时变色；检索 Agent 旁显示「部门知识索引」数据源节点）
- 历史会话列表（同一用户可看自己之前的对话）
- 用户记忆管理入口：记忆内容上限 20 条、单条 500 字符，管理员也不能读取或修改
- 会话上下文工具栏：五档记忆级别（默认 3）和 `all`/`selected` 文档范围；selected 必须包含授权文档 ID，权限变化或删除后不会回退为全部文档

### 4.3 对话业务助手（管理助手与员工聊天页共用）
- 管理端一级入口只有两个：管理助手 `/admin/assistant` 与企业全景 `/admin/overview`；`/admin/dashboard` 重定向到 `/admin/overview`，其余管理页面保留为深链。
- 服务端对话规划层对一句话只输出五种结果：知识回答、实时查询、表单预填、白名单页面导航、受控动作预览；顺序为已注册动作 → 表单创建 → 导航 → 实时查询 → 明显不完整的业务指令 → 知识回答兜底。
- 规则优先，LLM 只用于补全"既有操作动词又有具体业务对象"的语句；候选的 action 名、参数和 route key 必须重新通过服务端注册表和 Pydantic 输入模型校验，风险等级只取服务端元数据。
- 高频意图（今日考勤、本月费用、查看工单、请假、报销、故障工单）在 LLM 未配置或调用失败时仍然可用。
- 时间区间在服务端解析为显式查询参数：日（今天/昨天/前天/8月15日/2026-07-20/上个月15号）、月（本月/上月/上上个月/7月/去年12月/2026-07）、区间（本周/上周/最近7天/最近30天/今年/去年）。每个查询只绑定一种形态，区间不超过 366 天；无法确定区间的"查看考勤""查看费用"按页面导航处理。
- 确认策略：低风险汇总/列表/导航/表单预填直接执行；敏感查询需确认查看；写操作先预览再确认；批量或跨范围操作两次确认。确认时校验角色、参数哈希、对象版本、预览有效期、幂等键并写审计。
- 覆盖的受控写操作分组：组织与员工、排班考勤请假、项目合同文档、费用审批付款、协作工单待办、薪酬、安全关键词与敏感事件、部门记忆。
- 密码类动作的输入在内部加密存储，在预览、消息、会话标题、审计与接口结果中一律脱敏，且永不进入模型提示。
- AI 只能选择服务端注册的 intent、action 和 route key，不能执行任意 SQL、任意 HTTP 请求或任意 URL。

### 4.4 不做的事（Out of Scope）
- 复杂 PDF/Word 解析（MVP 只吃纯文本/Markdown，图文混排文档手动转存）
- 多租户强隔离、审计日志合规导出
- 单元测试全覆盖（按用户要求，只保证核心路径能跑通）

### 4.5 上下文与安全优先级
- 上下文优先级固定为：系统安全 > 当前日期/时间 > 证据所属部门记忆 > 用户记忆 > 摘要 > 最近历史 > 当前问题与证据。
- 会话记忆级别固定为 1..5，默认 3；历史消息按级别对应的 token 预算（0/2000/6000/12000/24000）整条保留，级别 3..5 可使用摘要，级别 4..5 触发摘要更新。
- 用户记忆和部门记忆只影响回答风格、格式和工作习惯，均不授予文档访问权限，也不是业务事实证据；业务结论必须来自授权文档。
- 文档选择始终受当前用户部门成员关系约束，空的 selected 范围保持为空并阻断检索，绝不扩大为 `all`。

## 5. 多 Agent 链路设计

这是本次重新设计的核心，直接对着 enterprise-kb-agent 的慢的病因改。

### 5.1 enterprise-kb-agent 为什么慢（根因，来自代码调研）
- `app/orchestrator.py`：Planner → Synthesis → (Critic ∥ 规则检查) → 修订 → 再 Critic，正常路径下**至少 3 次串行 LLM 调用**，触发修订则 4~5 次。
- `app/llm.py`：同步 `OpenAI` client + 同步路由函数，阻塞 worker 线程，且不开 `stream`，用户要等完整生成完才看到任何字。
- JSON 解析失败会整次重试 LLM 调用，链路可能翻倍。

检索本身（BM25，9 篇文档）不是瓶颈，是**LLM 调用次数 + 不流式 + 同步阻塞**三个问题叠加。不过 enterprise-kb-agent 的检索层还有一个隐患没暴露出来：`app/kb/retriever.py` 里 BM25 语料是模块加载时对内存里硬编码的 `DOCUMENTS` 一次性分词建索引，如果换成"文档可增删"的真实场景、又不改这个模式，很容易写成"每次提问都重新读全部文档分词建一次 BM25+ 重新算一遍所有 embedding"，那样文档一多检索就会变慢。新方案要明确避开这个坑（见下方索引生命周期）。

### 5.2 索引生命周期：向量化只在文档写入时做一次，问答时只做一次极小的 query 向量化

这是本次和 enterprise-kb-agent 的另一个关键差异点，直接针对"文档不应该每次提问都重新检索"这个要求：

- **文档新增/编辑时**（管理员后台触发）：切分 chunk → 调 embedding 模型算好每个 chunk 的向量 → 连同 BM25 用到的分词结果，一起写入 `DocumentChunk` 表持久化。这一步只在文档变化时发生一次，代价由管理员的写操作承担，不摊到每次员工提问上。
- **文档删除时**：直接删对应 `DocumentChunk` 行。
- **每个部门维护一份轻量内存索引缓存**（BM25 语料 + 向量矩阵），进程启动时从数据库加载一次；文档增删改后只增量更新对应部门这一份缓存，不是从零重建整个索引，也不是重建其他部门的索引。
- **员工提问时**：只对用户这一句话调一次 embedding（几十毫秒级的小调用），拿这个 query 向量去already算好的部门向量矩阵里做 cosine，同时用 BM25 语料对 query 分词打分——检索环节完全不重新处理文档本身，文档的向量和分词早就在写入时算好并留在内存/数据库里，重复使用。

也就是"文档只在上传/修改那一刻被处理一次，之后所有提问都是直接查现成的索引"，这样文档量增长不会拖慢每次提问的检索耗时。

### 5.3 新链路：4 个节点，1 次必经 LLM 调用（流式）+ 1 次异步不阻塞调用

```
用户问题
   │
   ▼
① 敏感话题门禁（规则判断，0 次 LLM 调用）
   - 命中敏感关键词 / 检索唯一命中的文档全部标记 sensitive=true → 直接转人工，不进入下一步
   - 否则继续
   │
   ▼
② 检索 Agent（无 LLM，本地计算，几十毫秒）
   - 用原始问题直接检索本部门索引（BM25 + embedding 混合排序）
   - 不做 query 拆解规划：多数企业内部问答是单一意图，"先让 LLM 拆子查询"这一步在
     enterprise-kb-agent 里是串行链路的第一环，砍掉它是本次最大的提速点
   │
   ▼
③ 回答 Agent（唯一必经的 1 次 LLM 调用，AsyncOpenAI + stream=True）
   - 基于检索到的 chunk 边生成边流式吐字，用户感知的首字延迟大幅下降
   - 结论后用简单角标标记 [[C1]][[C2]]（不是完整 markdown 链接，减轻模型输出结构负担）
   │
   ▼（不阻塞，用户已经看到完整回答）
④ 溯源核查 Agent（异步并行触发，1 次 LLM 调用，可选用更便宜的模型）
   - 核对回答内容是否都能在检索到的 chunk 里找到依据（忠实度检查）
   - 若发现幻觉/引申，通过单独的 SSE 事件补发一个"⚠️部分内容建议人工核实"标记
   - 关键点：**不做原来那种"发现问题就打回去重新生成"的修订循环**，那是 enterprise-kb-agent
     里最耗时的部分。新方案是"先给答案，事后补充风险标记"，用户不用等修订
```

正常路径耗时对比：
- 旧：Planner(LLM) → Synthesis(LLM) → Critic(LLM，等 Synthesis 完) → [可能的修订(LLM)+再 Critic(LLM)]，且都不流式，用户要等最后一次调用完全结束才看到字。
- 新：规则判断(0ms) → 检索(几十 ms) → 回答(1 次 LLM，流式，边吐边看) → 核查(异步，不占用户等待时间)。

用户感知到的"能不能对话"的时间从"等最长一次 LLM 调用链跑完"变成"等第一个 token 吐出来"。

### 5.4 溯源实现方式

不采用 deer-flow 现有的做法（前端用正则从 markdown 里扫 `[citation:xxx](url)`），因为那依赖 LLM 精确吐出完整 URL，流式过程中容易断裂。改为：

1. 检索 Agent 结束后，后端已经拿到 `chunk_id → {doc_id, doc_title, department, snippet, updated_at}` 的映射，通过一条 SSE 事件（`citations_meta`）提前/伴随推给前端。
2. 回答 Agent 只需要在正文里吐出轻量标记 `[[C1]]`，不需要输出 URL 或完整 JSON。
3. 前端把 `[[C1]]` 渲染成可点击角标，点击后从本地已收到的 `citations_meta` 里查出文档卡片展示，不需要额外请求。

这样"溯源"这件事完全不依赖 LLM 输出结构是否规范，比 deer-flow 现在的正则解析方式更可靠。

### 5.5 流程可视化实现方式

deer-flow 实际的可视化是"聊天式思维链时间线"（`subtask-card.tsx`，文本/工具调用交替、可折叠），不是节点连线图——这一点在调研初期判断错误，这里做纠正。用户要的效果是 enterprise-kb-agent 那种"节点随执行状态点亮"的流程图（§5.2 的 4 个节点框图），所以前端按需引入 `@xyflow/react` 单独实现，不是复用 deer-flow 现成页面：

1. 后端每个节点开始/结束都推一条 SSE 事件：`{node: "retrieval", status: "running"|"done", ...payload}`，事件结构直接沿用 enterprise-kb-agent 的 `orchestrator.py` 设计（已验证好用）。
2. 前端用 `@xyflow/react` 渲染 4 个固定 Agent 节点（敏感门禁/检索/回答/溯源核查），并在检索 Agent 旁渲染一个圆柱形「部门知识索引」资源节点。资源节点不是第 5 个 Agent，它表示 §5.2 中按部门隔离的 `DocumentChunk` 持久化数据与内存索引缓存。
3. 「部门知识索引」直接继承真实 `retrieval` SSE 状态：检索开始时节点脉冲、索引到检索 Agent 的连线流动；检索完成后变绿并显示命中片段数；未命中时显示「未命中」，回答和溯源节点进入阻断状态，不播放虚假进度。

## 6. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | FastAPI | 与两个源项目一致，团队熟悉 |
| 数据库 | SQLite（SQLAlchemy） | 单文件、部署简单，参考 deer-flow persistence engine 的思路但不引入 Postgres |
| 检索 | rank_bm25（复用 enterprise-kb-agent）+ 本地 embedding（`bge-small-zh-v1.5`，sentence-transformers）| 中文效果好、离线免费，不引入额外向量数据库，MVP 阶段文档量小，向量在文档写入时算好持久化到 SQLite（BLOB/JSON 字段），进程内按部门缓存成 numpy 矩阵，提问时只做一次 query 向量化+cosine，不重新处理文档（见 §5.2） |
| 混合排序 | BM25 归一化分数 + cosine 归一化分数加权求和 | 几行代码，不引入 RRF 库 |
| LLM 调用 | `AsyncOpenAI` + `stream=True`，配置来自 `.env`（`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`），默认使用 NewAPI 网关的 `gpt-5.6-sol` | 修正 enterprise-kb-agent 同步阻塞的问题 |
| 认证 | 自建 JWT（pyjwt），密码用 `cryptography.Fernet` 对称加密可解密存储，密钥在 `.env` 的 `PASSWORD_ENC_KEY` | 满足管理员查看明文密码的需求 |
| 实时推送 | `sse-starlette`（复用 deer-flow 选型） | 后端流式推送 Agent 执行事件 |
| 前端框架 | React + Vite（不用 Next.js） | 内部工具不需要 SSR/SEO，Vite 启动和构建更快，开发周期短 |
| 前端可视化 | `@xyflow/react` 节点流程图 | 你要的是和 enterprise-kb-agent 一样的"节点随执行点亮"效果（见 §5.4），deer-flow 虽然依赖里带了这个库，但实际页面没用它画流程图（它的可视化是聊天式思维链时间线，不是节点图），这里是按需选用，不是复用 deer-flow 现成页面 |
| 样式 | Tailwind CSS | 复用两个源项目的方法论 |
| 状态管理 | Zustand | 够用，不引入 Redux |

## 7. 数据模型（简化）

```
Department      id, name, created_at
User            id, username, password_encrypted, department_id(primary), role(admin/employee), created_at
UserDepartment  user_id, department_id, position, access_level
Document        id, department_id, title, category, sensitive(bool), content, uploaded_by, created_at, updated_at
DocumentChunk   id, document_id, department_id, chunk_text, chunk_index, embedding(json array)
Thread          id, user_id, department_id, created_at
Message         id, thread_id, role(user/assistant), content, citations(json), created_at
UserMemory      id, user_id, title, content, enabled, created_at, updated_at
DepartmentMemory id, department_id, title, content, enabled, created_by, updated_by, created_at, updated_at
UserChatSetting user_id, default_memory_level, updated_at
ThreadContextSetting thread_id, memory_level, document_scope_mode, summary_text, summary_through_message_id, summary_token_count, summary_updated_at, updated_at
ThreadDocumentSelection thread_id, document_id, created_at
MessageContextFlag message_id, context_eligible, reason, created_at
```

按部门物理隔离的落地方式：`DocumentChunk` 表统一存储，但所有检索查询强制带授权部门集合过滤（服务端从 `UserDepartment` 读取成员关系，不信任客户端越权参数）；管理员角色检索时不加此过滤。

六张上下文表分别归属于用户、部门、会话、文档或消息；删除所属用户/部门/会话/文档/消息时通过外键关系级联清理。用户记忆的读取过滤始终绑定当前用户 ID，管理员没有越权读取路径。

## 8. API 大纲

```
POST   /auth/login                                   登录，返回 JWT
POST   /auth/logout

GET    /admin/departments                            部门列表
POST   /admin/departments                             新建部门

GET    /admin/departments/{id}/employees              员工列表（含明文密码字段）
POST   /admin/departments/{id}/employees               新建员工
PUT    /admin/employees/{id}                            重置密码/编辑
DELETE /admin/employees/{id}

GET    /admin/departments/{id}/documents               文档列表
POST   /admin/departments/{id}/documents               新增文档（触发 chunk+embedding）
PUT    /admin/documents/{id}                            编辑（重新 chunk+embedding）
DELETE /admin/documents/{id}

GET    /kb/documents                                   员工查看本部门文档（只读）

POST   /chat/ask                                       SSE 流式：可带初始 memory_level/document_scope_mode/document_ids；返回 context/scope、agent 执行事件、流式回答和 citations_meta
GET    /chat/threads                                    历史会话列表
GET    /chat/threads/{id}/messages                      历史消息
GET    /me/memories                                     当前员工的私有记忆
POST   /me/memories                                     新增私有记忆
PUT    /me/memories/{id}                                编辑私有记忆
DELETE /me/memories/{id}                                删除私有记忆
GET    /me/chat-settings                                获取新会话默认记忆级别
PATCH  /me/chat-settings                                更新新会话默认记忆级别（1..5）
GET/POST /admin/departments/{id}/memories               管理部门记忆（管理员）
PUT/DELETE /admin/department-memories/{id}              编辑/删除部门记忆（管理员）
GET    /chat/threads/{id}/context-settings              获取会话上下文和文档选择
PATCH  /chat/threads/{id}/context-settings              更新五档上下文和 selected 文档 ID
```

## 9. 前端页面

1. **登录页**：统一登录表单，后端按角色返回后跳转到对应界面
2. **管理员后台**
   - 部门列表页
   - 部门详情页：员工管理 Tab（列表+所属部门/职位+密码明文列+多部门新增表单）、文档管理 Tab（列表+新增/编辑/删除）
3. **员工问答页**
   - 左侧：所属部门文档列表（只读）和历史会话；账户菜单进入私有记忆管理
   - 中间：对话区（当前对话 + 输入框），回答内角标可点击查看来源卡片
   - 对话工具栏提供五档上下文记忆级别和授权文档多选范围
   - 右侧：Agent 流程可视化（4 个 Agent 节点：敏感门禁 / 检索 / 回答 / 溯源核查，随 SSE 事件变色；检索 Agent 旁附带部门知识索引资源节点及真实检索动画）

## 10. 开发计划（周期短，分 4 步，无需团队排期粒度）

1. 数据层 + 认证 + 管理员 CRUD API（无 UI，用 REST 客户端验证）
2. 检索层（文档 chunk 化、BM25+embedding 混合）+ Agent 链路（脚本级验证 SSE 事件流跑通）
3. 前端：登录页 + 管理员后台 + 问答页（复用 `@xyflow/react` 和 Tailwind 方法论）
4. 联调 + 跑通核心路径 smoke test

## 11. 测试策略

按要求，测试尽量少，能跑通即可：
- 后端只写 1 个 smoke test：起服务 → 登录 → 提问 → 断言收到流式事件且最终回答带 citations
- 前端不写自动化 E2E，人工过一遍：管理员建部门/建员工/传文档 → 员工登录提问看到可视化和溯源
- 不追求单元测试覆盖率

## 12. 风险与提示

- **密码可逆加密存储**是应你的要求做的选择，安全性弱于行业标准的不可逆哈希（deer-flow 原本用 bcrypt）。加密密钥 `PASSWORD_ENC_KEY` 不能进代码仓库，必须放 `.env`。建议仅用于内网可信环境，若后续要对外或过合规审计，需要改回不可逆哈希 + "重置密码"模式。
- 检索按部门物理隔离，依赖 JWT 里的 `department_id` claim 不被前端篡改（后端签发和校验，前端无法伪造）。
- 本地 embedding 模型（`bge-small-zh-v1.5`，约 100MB）首次启动需下载，建议提前下载好或用镜像源。
