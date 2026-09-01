# 企业对话业务助手与企业全景 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 root/admin 管理助手和员工 ChatPage 都能通过自然语言完成知识问答、实时查询、表单预填、页面导航和受控业务操作，并恢复可下钻的企业全景。

**Architecture:** 在现有 `/chat/ask` SSE 链路之前增加规则优先、LLM 可选补全、服务端白名单复核的对话规划层。规划结果统一为知识回答、实时查询、表单预览、白名单导航或动作预览；所有查询和写入复用现有 service、权限范围、确认、幂等和审计。前端保留 ChatPage 的既有弹窗，抽取共享事件呈现与路由映射供管理助手复用。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Pydantic v2, OpenAI-compatible async client, React 19, TypeScript 6, React Router 6, Zustand, Vite, pytest, Node `--experimental-strip-types` tests.

**Spec:** `docs/superpowers/specs/2026-08-31-root-admin-assistant-design.md`

## Global Constraints

- 管理端主要导航只保留“管理助手”和“企业全景”；现有详情页面继续保留为深链。
- root/admin 无部门归属时默认拥有全部部门管理查询范围；员工、经理、人事和财务继续使用现有角色与部门范围。
- 高频业务意图在 LLM 未配置或调用失败时仍必须工作。
- AI 只能选择服务端注册的 intent、action 和 route key，不能执行任意 SQL、任意 HTTP 请求或任意 URL。
- 低风险汇总、普通列表、白名单导航和表单预填直接执行；敏感查询确认查看；写操作预览确认；批量操作两次确认。
- 所有业务写入调用现有 service，不在助手 adapter 中复制业务规则或自行提交事务。
- 密码、令牌、加密字段、未授权薪资和未授权个人数据不得进入助手响应。
- 真实数据库只用于只读验收；写操作自动化测试使用隔离数据库或事务夹具。
- 工作树中的用户修改必须保留；每次提交只暂存当前任务文件。

## File Map

- Modify `backend/app/assistant/planner.py`: 统一规划类型、规则意图和候选能力复核。
- Modify `backend/app/assistant/registry.py`: 实时查询输入模型和完整业务动作元数据。
- Create `backend/app/assistant/form_previews.py`: 请假、工单和报销共享预览。
- Create `backend/app/assistant/navigation.py`: 角色可用 route key 白名单。
- Create `backend/app/assistant/intent_extractor.py`: LLM 结构化候选补全与失败降级。
- Modify `backend/app/assistant/adapters.py`: 实时查询及现有业务 service adapter。
- Modify `backend/app/assistant/service.py`: 无持久副作用的低风险查询执行入口。
- Modify `backend/app/assistant/schemas.py`: 对话业务事件结构。
- Modify `backend/app/routers/chat.py`: 统一规划、SSE 事件和消息持久化。
- Modify `backend/app/routers/schedule.py`: 复用共享请假预览。
- Modify `backend/app/routers/tickets.py`: 复用共享工单预览。
- Modify `backend/app/routers/expenses.py`: 复用共享报销预览。
- Create `frontend/src/assistantPresentation.ts`: 事件归一化、结果文案和安全路由解析。
- Create `frontend/src/components/AssistantResultCard.tsx`: 查询结果和导航卡片。
- Modify `frontend/src/pages/ChatPage.tsx`: 消费 form/query/navigation/action 事件。
- Modify `frontend/src/pages/AdminAssistantPage.tsx`: 正常聊天气泡、知识回答、结果卡和风险确认。
- Modify `frontend/src/pages/AdminDashboardPage.tsx`: 企业全景内容和日期。
- Modify `frontend/src/pages/AdminLayout.tsx`: 两个一级入口。
- Modify `frontend/src/pages/EnterpriseOverviewPage.tsx`: 企业全景页面入口。
- Modify `backend/tests/test_root_chat_scope.py`.
- Modify `backend/tests/test_assistant_adapters.py`.
- Modify `backend/tests/test_chat_context.py`.
- Modify `backend/tests/test_assistant_actions.py`.
- Create `backend/tests/test_conversation_intents.py`.
- Create `backend/tests/test_form_previews.py`.
- Create `backend/tests/test_conversation_e2e.py`.
- Create `backend/tests/test_intent_extractor.py`.
- Modify `frontend/src/dashboardFormat.test.ts`.
- Modify `frontend/src/assistantPresentation.test.ts`.
- Create `frontend/src/chatBusinessIntent.test.ts`.
- Create `frontend/src/adminAssistantState.test.ts`.
- Create `frontend/src/adminNavigation.test.ts`.

---

### Task 1: 固定正确数据库配置并修复企业全景日期基线

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_security_config.py`
- Modify: `frontend/src/dashboardFormat.ts`
- Modify: `frontend/src/dashboardFormat.test.ts`
- Modify: `frontend/src/pages/AdminDashboardPage.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`

**Interfaces:**
- Produces: `initialDashboardDateRange(now: Date) -> { start: string; end: string }`，使用浏览器本地年月日。
- Runtime only: worktree `backend/.env` 使用项目完整 LLM/JWT/加密配置，并把 `DATABASE_URL` 指向 `/Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/data/app.db`；不得提交 `.env`。

- [ ] **Step 1: 运行已有失败测试**

```bash
cd backend && .venv/bin/python -m pytest tests/test_security_config.py -q
cd ../frontend && node --experimental-strip-types src/dashboardFormat.test.ts
```

Expected: 日期测试因 `initialDashboardDateRange` 不存在而失败。

- [ ] **Step 2: 实现本地日期范围**

Add to `frontend/src/dashboardFormat.ts`:

```ts
function localDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function initialDashboardDateRange(now: Date): { start: string; end: string } {
  return {
    start: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`,
    end: localDate(now),
  };
}
```

Initialize both dashboard states from one captured result; do not mix `toISOString()` with local dates.

- [ ] **Step 3: 完成安全开发配置并验证真实库**

Keep production secret validation unchanged, use `admin123` only as the development fallback, and display the demo credential only on `localhost`/`127.0.0.1`. Verify without printing secrets:

```bash
cd backend
.venv/bin/python - <<'PY'
from app.config import get_settings
s = get_settings()
assert s.database_url == "sqlite:////Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/data/app.db"
assert bool(s.llm_api_key.strip())
print("database and llm configuration loaded")
PY
```

- [ ] **Step 4: 运行定向验证**

```bash
cd backend && .venv/bin/python -m pytest tests/test_security_config.py -q
cd ../frontend && node --experimental-strip-types src/dashboardFormat.test.ts && npm run build
```

Expected: PASS; 2026-09-01 00:30 本地时间得到 `{start: "2026-09-01", end: "2026-09-01"}`。

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_security_config.py frontend/src/dashboardFormat.ts frontend/src/dashboardFormat.test.ts frontend/src/pages/AdminDashboardPage.tsx frontend/src/pages/LoginPage.tsx
git commit -m "fix: restore local data and dashboard dates"
```

### Task 2: 定义统一对话计划与白名单导航

**Files:**
- Modify: `backend/app/assistant/planner.py`
- Modify: `backend/app/assistant/registry.py`
- Create: `backend/app/assistant/navigation.py`
- Create: `backend/tests/test_conversation_intents.py`
- Modify: `backend/tests/test_root_chat_scope.py`

**Interfaces:**
- Produces: `KnowledgePlan`, `FormPreviewPlan`, `NavigationPlan` dataclasses.
- Produces: `ConversationPlan = ActionPlan | KnowledgePlan | FormPreviewPlan | NavigationPlan | ClarificationPlan`.
- Produces: `allowed_route_keys(principal: Principal) -> frozenset[str]`.
- Produces low-risk actions `attendance_summary` and `expense_summary`.

- [ ] **Step 1: 写意图矩阵失败测试**

```python
@pytest.mark.parametrize(("text", "kind", "value"), [
    ("查询一下最近的项目", "action", "list_projects"),
    ("查看一下今天考勤", "action", "attendance_summary"),
    ("这个月支出怎么样", "action", "expense_summary"),
    ("看看我有哪些未完成工单", "action", "list_tickets"),
    ("我要请假三天", "form", "leave"),
    ("电脑有问题帮我找信息部处理", "form", "ticket"),
    ("报销昨天打车 86 元", "form", "expense"),
    ("查看工单", "navigation", "tickets"),
    ("打开企业全景", "navigation", "overview"),
    ("公司的请假制度是什么", "knowledge", None),
])
def test_conversation_plan_matrix(root_principal, text, kind, value):
    plan = plan_input(text, root_principal, db=None)
    assert plan_kind(plan) == kind
    assert plan_value(plan) == value
```

Also assert arbitrary SQL, arbitrary URLs, and incomplete destructive commands remain `ClarificationPlan`.

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/python -m pytest tests/test_conversation_intents.py tests/test_root_chat_scope.py -q
```

Expected: FAIL because the new plan types and route registry are absent.

- [ ] **Step 3: 实现计划类型和匹配顺序**

```python
@dataclass(frozen=True)
class KnowledgePlan:
    question: str

@dataclass(frozen=True)
class FormPreviewPlan:
    form: Literal["leave", "ticket", "expense"]
    text: str

@dataclass(frozen=True)
class NavigationPlan:
    route_key: str
```

Matching order: explicit registered action, form creation, navigation, live query, clearly ambiguous business command, knowledge fallback. Valid route keys are `tickets`, `expenses`, `organization`, `projects`, `contracts`, `knowledge`, `schedules`, `payroll`, `overview`, and `assistant`.

- [ ] **Step 4: 注册查询输入模型并运行测试**

```python
class AttendanceQueryInput(BaseModel):
    department_id: str | None = None
    attendance_date: date | None = None

class ExpenseSummaryInput(BaseModel):
    department_id: str | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
```

Register both actions as low risk for `admin`, `employee`, `hr`, `manager`, and `finance`. Run the same pytest command; expected PASS.

Extend `list_tickets` authorization to `employee` while keeping the adapter's existing requester/assignee/department visibility predicate; employees must not receive the admin-wide result set.

- [ ] **Step 5: Commit**

```bash
git add backend/app/assistant/planner.py backend/app/assistant/registry.py backend/app/assistant/navigation.py backend/tests/test_conversation_intents.py backend/tests/test_root_chat_scope.py
git commit -m "feat: define conversational business plans"
```

### Task 3: 实现实时查询与直接执行

**Files:**
- Modify: `backend/app/assistant/adapters.py`
- Modify: `backend/app/assistant/service.py`
- Modify: `backend/tests/test_assistant_adapters.py`
- Modify: `backend/tests/test_assistant_actions.py`

**Interfaces:**
- Produces: `execute_low_risk_query(db, principal, plan) -> dict[str, Any]`.
- Produces: attendance result `{date, active_employees, recorded, missing, status_counts}`.
- Produces: expense result `{month, count, amount, status_counts, route_key}`.

- [ ] **Step 1: 扩展失败测试**

Keep the existing RED attendance test and add employee-only expense visibility plus this direct-execution assertion:

```python
def test_low_risk_query_executes_without_confirmation_row(db, root_principal):
    result = execute_low_risk_query(db, root_principal, plan_for("list_projects"))
    assert result["count"] == 1
    assert db.query(AssistantAction).count() == 0
```

- [ ] **Step 2: 运行失败测试**

```bash
cd backend && .venv/bin/python -m pytest tests/test_assistant_adapters.py tests/test_assistant_actions.py -q
```

Expected: FAIL because the live adapters and direct execution are absent.

- [ ] **Step 3: 实现 role-aware 查询 adapter**

Admin/hr/manager attendance aggregates only authorized active/probation employees; employee attendance uses only `principal.user_id`. Expense summary computes local-month UTC boundaries and applies `ExpenseService.visibility_predicate`. Return Decimal totals as strings, bounded JSON, and no employee names in attendance aggregate.

- [ ] **Step 4: 实现直接执行入口**

```python
def execute_low_risk_query(db: Session, principal: Principal, plan: ActionPlan) -> dict[str, Any]:
    definition = _registered_definition(plan)
    if definition.risk_level != "low":
        raise HTTPException(status.HTTP_409_CONFLICT, "query requires preview")
    if not principal.has_role(*definition.required_roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "principal is not authorized for this action")
    adapter = _ACTION_ADAPTERS.get(definition.name)
    if adapter is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "assistant query is unsupported")
    payload = _normalize_json(plan.input.model_dump(mode="python"))
    return _normalized_adapter_result(adapter(_AdapterSession(db), principal, payload))
```

Register both adapters, remove the duplicate `_list_tickets` key, run the same tests, and expect PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/assistant/adapters.py backend/app/assistant/service.py backend/tests/test_assistant_adapters.py backend/tests/test_assistant_actions.py
git commit -m "feat: execute live assistant queries"
```

### Task 4: 统一表单预览并扩展 `/chat/ask` 业务事件

**Files:**
- Create: `backend/app/assistant/form_previews.py`
- Modify: `backend/app/assistant/schemas.py`
- Modify: `backend/app/routers/schedule.py`
- Modify: `backend/app/routers/tickets.py`
- Modify: `backend/app/routers/expenses.py`
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/agents/orchestrator.py`
- Create: `backend/tests/test_form_previews.py`
- Create: `backend/tests/test_conversation_e2e.py`
- Modify: `backend/tests/test_chat_context.py`

**Interfaces:**
- Produces: `preview_form(form, text, today=None) -> dict[str, Any]`.
- Produces SSE nodes `query_result`, `form_preview`, `navigation`, `action_preview`, plus existing knowledge nodes.
- Existing preview HTTP response shapes remain unchanged.

- [ ] **Step 1: 写共享预览与 SSE 失败测试**

```python
def test_shared_form_previews_extract_fields():
    leave = preview_form("leave", "我要从明天开始请假两天，家里有事", today=date(2026, 8, 31))
    ticket = preview_form("ticket", "电脑网络有问题，帮我找信息部处理")
    expense = preview_form("expense", "报销昨天打车 86 元")
    assert leave["start_date"] == "2026-09-01"
    assert ticket["is_ticket_request"] is True
    assert expense["total_amount"] == "86"

def test_chat_business_query_skips_rag(client, admin_headers, monkeypatch):
    rag = AsyncMock()
    monkeypatch.setattr(chat, "run_ask", rag)
    events = ask_events(client, admin_headers, "查看今天考勤")
    assert any(event["node"] == "query_result" for event in events)
    rag.assert_not_awaited()
```

- [ ] **Step 2: 运行失败测试**

```bash
cd backend && .venv/bin/python -m pytest tests/test_form_previews.py tests/test_conversation_e2e.py tests/test_chat_context.py -q
```

Expected: FAIL because the shared previews and business SSE nodes are absent.

- [ ] **Step 3: 抽取 preview 并保持旧接口**

Move pure ticket and expense parsing from their routers into `form_previews.py`; delegate leave parsing to `schedule.service.preview_leave`. Each existing preview router returns its current Pydantic model from the shared dict.

- [ ] **Step 4: 按 plan 类型分流并持久化可读消息**

After thread creation and before RAG context loading:

```python
plan = plan_input(payload.question, principal, db)
if isinstance(plan, NavigationPlan):
    return business_stream(thread, "navigation", route_key=plan.route_key)
if isinstance(plan, FormPreviewPlan):
    return business_stream(thread, "form_preview", form=plan.form, preview=preview_form(plan.form, plan.text))
if isinstance(plan, ActionPlan) and plan.action.risk_level == "low":
    return query_stream(thread, plan.action.name, execute_low_risk_query(db, principal, plan))
if isinstance(plan, ActionPlan):
    return action_stream(thread, create_preview(db, principal, thread.id, plan))
```

`KnowledgePlan` continues into RAG. Persist user input and readable assistant summaries, never raw URLs or debug events. Run the same pytest command; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/assistant/form_previews.py backend/app/assistant/schemas.py backend/app/routers/schedule.py backend/app/routers/tickets.py backend/app/routers/expenses.py backend/app/routers/chat.py backend/app/agents/orchestrator.py backend/tests/test_form_previews.py backend/tests/test_conversation_e2e.py backend/tests/test_chat_context.py
git commit -m "feat: stream conversational business events"
```

### Task 5: 增加 LLM 结构化补全并完成管理动作目录

**Files:**
- Create: `backend/app/assistant/intent_extractor.py`
- Modify: `backend/app/assistant/planner.py`
- Modify: `backend/app/assistant/registry.py`
- Modify: `backend/app/assistant/adapters.py`
- Modify: `backend/app/routers/chat.py`
- Create: `backend/tests/test_intent_extractor.py`
- Modify: `backend/tests/test_assistant_actions.py`

**Interfaces:**
- Produces: `async plan_conversation(text, principal, db) -> ConversationPlan`.
- LLM candidate schema: `{kind, name, arguments, route_key}`; every field is untrusted until server validation.
- Expands the registry to existing organization, schedule, asset, finance, collaboration, payroll, security, and department-memory mutations.

Exact capability groups:

```text
organization: create/update org unit; create/update employee; employment event; reset password
schedule: update work schedule; create/delete holiday; create/delete attendance; review leave
assets: create/update/delete project, contract, document
finance: create/update/delete/submit expense; approve/reject/cancel approval; pay expense
collaboration: create/delete/dispatch ticket; create/update todo
payroll: update settings; generate payroll
security: create/update/delete sensitive keyword; delete sensitive event
memory: create/update/delete department memory
```

Reset password, deletion, approval, payment, employment termination, and security changes are high risk. Payroll generation is batch risk. Creates and ordinary updates use the existing one-confirmation high-risk policy.

- [ ] **Step 1: 写 LLM 信任边界失败测试**

```python
@pytest.mark.asyncio
async def test_llm_candidate_is_revalidated(monkeypatch, root_principal, db):
    monkeypatch.setattr(intent_extractor, "call_json", AsyncMock(return_value={
        "kind": "action", "name": "run_sql", "arguments": {"sql": "DROP TABLE users"},
    }))
    plan = await plan_conversation("清空用户", root_principal, db)
    assert isinstance(plan, ClarificationPlan)

@pytest.mark.asyncio
async def test_llm_failure_keeps_rule_intents_available(monkeypatch, root_principal, db):
    monkeypatch.setattr(intent_extractor, "call_json", AsyncMock(side_effect=RuntimeError("offline")))
    plan = await plan_conversation("查看今天考勤", root_principal, db)
    assert isinstance(plan, ActionPlan)
    assert plan.action.name == "attendance_summary"
```

- [ ] **Step 2: 运行失败测试**

```bash
cd backend && .venv/bin/python -m pytest tests/test_intent_extractor.py tests/test_assistant_actions.py -q
```

Expected: FAIL because async planning and the expanded catalog are absent.

- [ ] **Step 3: 实现规则优先、LLM 补全、白名单复核**

Rules always run first. Only clearly business-oriented text that rules cannot fully parameterize calls `call_json`. Validate candidate name with `get_action`, arguments with the registered Pydantic input model, route key with `allowed_route_keys`, and use server-owned risk metadata. Any exception returns the safe rule result or `ClarificationPlan`.

The model prompt lists only actions authorized for the principal and their input field names; it never includes secrets or database rows.

Update `backend/app/routers/chat.py` to replace the synchronous `plan_input(...)` call introduced in Task 4 with `await plan_conversation(...)`.

- [ ] **Step 4: 用现有 service 完成 adapter 并验证事务边界**

Each adapter calls the corresponding existing service and returns bounded JSON. Add a parameterized assertion that every registry action has an adapter and an adapter-session test that rejects `commit`, `rollback`, `close`, `begin`, and `begin_nested`.

```bash
cd backend && .venv/bin/python -m pytest tests/test_intent_extractor.py tests/test_assistant_actions.py tests/test_assistant_adapters.py -q
```

Expected: PASS; unknown actions, invalid payloads, unauthorized roles, and risk downgrades are rejected.

- [ ] **Step 5: Commit**

```bash
git add backend/app/assistant/intent_extractor.py backend/app/assistant/planner.py backend/app/assistant/registry.py backend/app/assistant/adapters.py backend/app/routers/chat.py backend/tests/test_intent_extractor.py backend/tests/test_assistant_actions.py
git commit -m "feat: expand controlled conversational actions"
```

### Task 6: 建立前端事件呈现和安全路由映射

**Files:**
- Create: `frontend/src/assistantPresentation.ts`
- Modify: `frontend/src/assistantPresentation.test.ts`
- Create: `frontend/src/components/AssistantResultCard.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/chat.ts`

**Interfaces:**
- Produces: `answerFromEvent(event) -> string | null`.
- Produces: `formatAssistantResult(intent, result) -> string`.
- Produces: `routeForKey(role, key, params?) -> string | null`.
- Produces discriminated `AssistantBusinessEvent` types for query, form, navigation, and action.

- [ ] **Step 1: 扩展已有失败测试**

```ts
assertEqual(routeForKey?.("employee", "tickets"), "/collaboration");
assertEqual(routeForKey?.("admin", "tickets"), "/admin/tickets");
assertEqual(routeForKey?.("admin", "run_sql"), null);
assertEqual(
  formatAssistantResult?.("expense_summary", {
    month: "2026-08", count: 2, amount: "186.00", status_counts: { draft: 1, paid: 1 },
  }),
  "2026-08 本月费用共 2 笔，合计 ¥186.00。",
);
```

- [ ] **Step 2: 运行失败测试**

```bash
cd frontend && node --experimental-strip-types src/assistantPresentation.test.ts
```

Expected: FAIL because `assistantPresentation.ts` does not exist.

- [ ] **Step 3: 实现 closed route table 和纯函数**

```ts
const ROUTES: Record<Role, Record<string, string>> = {
  admin: {
    tickets: "/admin/tickets", expenses: "/admin/expenses", organization: "/admin/organization",
    projects: "/admin/projects", contracts: "/admin/contracts", knowledge: "/admin/knowledge",
    schedules: "/admin/work-schedules", payroll: "/admin/payroll", overview: "/admin/overview",
    assistant: "/admin/assistant",
  },
  employee: {
    tickets: "/collaboration", expenses: "/expenses", organization: "/organization",
    overview: "/dashboard", assistant: "/chat",
  },
};
```

Unknown keys return `null`; query parameters use `URLSearchParams` only.

- [ ] **Step 4: 实现结果卡并验证构建**

`AssistantResultCard` renders the readable summary, at most five safe list rows, and one optional navigation button. It never renders raw JSON or HTML.

```bash
cd frontend && node --experimental-strip-types src/assistantPresentation.test.ts && npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/assistantPresentation.ts frontend/src/assistantPresentation.test.ts frontend/src/components/AssistantResultCard.tsx frontend/src/types/index.ts frontend/src/api/chat.ts
git commit -m "feat: present assistant business events"
```

### Task 7: 接入员工 ChatPage 和 root/admin 管理助手

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`
- Modify: `frontend/src/pages/AdminAssistantPage.tsx`
- Modify: `frontend/src/components/AssistantActionCard.tsx`
- Modify: `frontend/src/chatIntent.ts`
- Create: `frontend/src/chatBusinessIntent.test.ts`
- Create: `frontend/src/adminAssistantState.test.ts`

**Interfaces:**
- Produces: `decideChatBusinessEffect(event, role)` for employee UI effects.
- Produces: `reduceAdminAssistantEvent(state, event)` for admin conversation state.
- Reuses existing leave, ticket, expense, and attendance dialogs.

- [ ] **Step 1: 写员工和管理员状态失败测试**

```ts
assertEqual(decideChatBusinessEffect({ node: "navigation", route_key: "tickets" }, "employee").route, "/collaboration");
assertEqual(decideChatBusinessEffect({ node: "form_preview", form: "leave", preview: leave }, "employee").dialog, "leave");

const state = reduceAdminAssistantEvent(initialState, {
  node: "final", status: "completed", answer: "制度要求提前一天申请。", citations: [],
});
assertEqual(state.messages.at(-1)?.content, "制度要求提前一天申请。");
```

- [ ] **Step 2: 运行失败测试**

```bash
cd frontend
node --experimental-strip-types src/chatBusinessIntent.test.ts
node --experimental-strip-types src/adminAssistantState.test.ts
```

Expected: FAIL because both helpers are absent.

- [ ] **Step 3: ChatPage 消费统一事件**

Add `useNavigate`. Resolve navigation route keys and navigate for explicit view/open commands. Fill existing Dialog state from `form_preview`. Append a structured assistant message for `query_result`. Stop sending three preview HTTP requests before `/chat/ask`; keep legacy `shouldPreview*` only as a temporary fallback when the server produces no business event.

- [ ] **Step 4: 管理助手改为正常聊天并回归**

Append the user bubble immediately, stream answer deltas into one assistant bubble, render final answers with `AnswerContent`, attach query results with `AssistantResultCard`, and keep action confirmation bound to `action_id`, `parameter_hash`, and the server phrase. Do not render raw `node: status` rows.

```bash
cd frontend
node --experimental-strip-types src/chatBusinessIntent.test.ts
node --experimental-strip-types src/adminAssistantState.test.ts
node --experimental-strip-types src/assistantPresentation.test.ts
node --experimental-strip-types src/scheduleFormat.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/AdminAssistantPage.tsx frontend/src/components/AssistantActionCard.tsx frontend/src/chatIntent.ts frontend/src/chatBusinessIntent.test.ts frontend/src/adminAssistantState.test.ts
git commit -m "feat: make chat pages conversational workspaces"
```

### Task 8: 收敛管理入口、完成企业全景并做全量验收

**Files:**
- Modify: `frontend/src/pages/AdminLayout.tsx`
- Modify: `frontend/src/pages/AdminDashboardPage.tsx`
- Modify: `frontend/src/pages/EnterpriseOverviewPage.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/adminNavigation.ts`
- Create: `frontend/src/adminNavigation.test.ts`
- Modify: `backend/tests/test_conversation_e2e.py`
- Modify: `README.md`
- Modify: `PRD.md`

**Interfaces:**
- Produces: `primaryAdminRoutes()` returning only management assistant and enterprise overview.
- Produces: `overviewAssistantHref(prompt, departmentId?)`.
- Keeps all detail routes and `/admin/dashboard -> /admin/overview`.

- [ ] **Step 1: 写导航失败测试**

```ts
assertEqual(JSON.stringify(primaryAdminRoutes()), JSON.stringify([
  { to: "/admin/assistant", label: "管理助手" },
  { to: "/admin/overview", label: "企业全景" },
]));
assertEqual(
  overviewAssistantHref("查看本月费用", "dept/a"),
  "/admin/assistant?prompt=%E6%9F%A5%E7%9C%8B%E6%9C%AC%E6%9C%88%E8%B4%B9%E7%94%A8&department=dept%2Fa",
);
```

- [ ] **Step 2: 收敛导航并完善全景**

Render only `primaryAdminRoutes()` in the main navigation while keeping notification, account switcher, logout, and all routes. Rename all visible “管理驾驶舱” copy to “企业全景”. Add an “向管理助手提问” link carrying the current date and department filters. Keep every metric drilldown.

- [ ] **Step 3: 运行完整自动化测试**

```bash
cd backend && .venv/bin/python -m pytest -q
cd ../frontend
for test_file in src/*.test.ts; do node --experimental-strip-types "$test_file"; done
npm run lint
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 4: 启动项目并做浏览器验收**

Verify real data read-only before browser writes:

```bash
cd backend
.venv/bin/python - <<'PY'
from app.db import SessionLocal
from app.models import Department, Document, User
db = SessionLocal()
try:
    assert db.query(User).count() >= 12
    assert db.query(Department).count() >= 5
    assert db.query(Document).count() >= 9
    assert {"gjk", "zwx", "xyz", "finance"}.issubset({u.username for u in db.query(User).all()})
    print("real database verified")
finally:
    db.close()
PY
```

Then verify in the browser:

```text
admin/admin123: 知识问答、最近项目、今日考勤、本月支出、打开工单、一个创建动作的确认和取消
employee: 知识问答、我要请假、电脑有问题帮我找谁、查看工单、报销 86 元、查看本月流水
enterprise overview: 页面加载、日期合法、关键指标下钻、向管理助手提问
degraded: LLM 不可用时今日考勤、本月支出、查看工单仍工作
security: 任意 SQL、任意 URL、越权部门和未确认高风险动作均被拒绝
```

Write scenarios use isolated fixture data; do not delete or rewrite existing real records.

- [ ] **Step 5: 更新文档、最终审查并提交**

Update product copy and document the five response types and confirmation policy. Run:

```bash
git diff --check
git status --short
rg -n "run_sql|DROP TABLE|eval\(|exec\(|dangerouslySetInnerHTML" backend/app frontend/src
```

Expected: no `.env`, database, backup, node_modules, virtualenv, or secret is staged; unsafe terms appear only in explicit rejection tests or already-reviewed code.

```bash
git add frontend/src/pages/AdminLayout.tsx frontend/src/pages/AdminDashboardPage.tsx frontend/src/pages/EnterpriseOverviewPage.tsx frontend/src/App.tsx frontend/src/adminNavigation.ts frontend/src/adminNavigation.test.ts backend/tests/test_conversation_e2e.py README.md PRD.md
git commit -m "feat: complete conversational enterprise workspace"
```
