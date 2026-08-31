# Root 管理员双入口与管理助手实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 root 管理员通过“管理助手”和“企业全景”两个入口完成全量知识查询、经营查询和已注册业务操作，并为所有写操作提供预览确认与审计。

**Architecture:** 在现有 FastAPI 聊天链路之上增加服务端受控动作层。动作注册表定义权限、风险、参数模型、预览和执行处理器；助手只调用注册动作，执行仍委托现有业务 service。前端复用现有流式问答视觉和企业全景数据，主导航收敛为两个入口，原页面保留为深链/详情抽屉。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/Alembic, Pydantic v2, React 19, TypeScript, React Router, Zustand, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-31-root-admin-assistant-design.md`

## Global Constraints

- root 管理员没有部门归属时默认拥有全部部门知识和管理查询范围；员工不能获得该范围。
- AI 只能调用注册动作，不能执行任意 SQL、任意 HTTP 请求或模型生成业务代码。
- 所有写操作必须先预览；高风险、隐私敏感、批量和跨部门操作需要明确确认，批量或跨部门高风险操作需要二次确认。
- 服务端重新校验角色、范围、参数摘要、对象版本、确认令牌有效期和幂等键。
- 密码、令牌等秘密信息不得进入助手回答；隐私敏感访问必须审计。
- 不删除现有业务页面和 service；`/admin/dashboard` 重定向到 `/admin/overview`。
- 使用现有项目测试工具；后端运行 `pytest`，前端运行 `npm test` 和 `npm run build`。

## File Map

- Create `backend/app/assistant/registry.py`: 注册动作定义、风险级别和动作查找。
- Create `backend/app/assistant/service.py`: 动作预览、确认、执行和审计编排。
- Create `backend/app/assistant/planner.py`: 将助手输入映射为结构化动作计划和澄清问题。
- Create `backend/app/assistant/schemas.py`: 动作计划、预览、确认和执行结果的数据结构。
- Modify `backend/app/models.py`: 持久化待确认动作和执行状态。
- Create `backend/migrations/versions/0013_assistant_actions.py`: 新表迁移。
- Modify `backend/app/access.py`: root 全量部门范围解析。
- Modify `backend/app/routers/chat.py`: root 聊天范围、动作事件和确认接口。
- Modify `backend/app/schemas.py`: 对外动作响应模型。
- Create `backend/tests/test_assistant_actions.py`: 动作生命周期、风险和幂等测试。
- Create `backend/tests/test_root_chat_scope.py`: root/员工检索范围测试。
- Create `frontend/src/pages/AdminAssistantPage.tsx`: 管理助手页面。
- Create `frontend/src/pages/EnterpriseOverviewPage.tsx`: 企业全景页面入口。
- Create `frontend/src/components/AssistantActionCard.tsx`: 查询、预览、确认、进度和结果卡片。
- Modify `frontend/src/api/chat.ts`: 管理助手流式请求和动作确认 API。
- Modify `frontend/src/types/index.ts`: 动作事件和结果类型。
- Modify `frontend/src/App.tsx`: 新路由和旧路由兼容重定向。
- Modify `frontend/src/pages/AdminLayout.tsx`: 仅保留两个一级入口。
- Create `frontend/src/assistantAction.test.ts`: 动作卡片状态和确认行为测试。
- Modify `frontend/src/pages/AdminDashboardPage.tsx`: 抽出或复用企业全景内容。

### Task 1: 建立动作持久化与类型协议

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/migrations/versions/0013_assistant_actions.py`
- Create: `backend/app/assistant/__init__.py`
- Create: `backend/app/assistant/schemas.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_assistant_actions.py`

**Interfaces:**
- `AssistantAction` ORM 字段：`id`, `thread_id`, `user_id`, `tool_name`, `risk_level`, `status`, `payload_json`, `preview_json`, `parameter_hash`, `object_versions_json`, `confirmation_phrase`, `expires_at`, `confirmed_at`, `executed_at`, `idempotency_key`, `result_json`, `error_code`, `created_at`, `updated_at`。
- `ActionRisk = Literal["low", "sensitive", "high", "batch"]`。
- `ActionStatus = Literal["preview", "confirmed", "executing", "completed", "cancelled", "expired", "failed"]`。
- `ActionPreview`, `ActionChange`, `ActionConfirmRequest`, `ActionResult` 为 Pydantic 对外结构。

- [ ] **Step 1: 写失败测试，覆盖动作创建、过期和唯一幂等键**

```python
def test_action_preview_stores_hash_and_expires(db):
    action = AssistantAction(
        id="act-1",
        thread_id="thread-1",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        payload_json={"name": "研发平台"},
        preview_json={"summary": "新建研发平台"},
        parameter_hash="sha256:expected",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="idem-act-1",
    )
    db.add(action)
    db.commit()
    assert action.status == "preview"
    assert action.parameter_hash
    assert action.expires_at is not None

def test_idempotency_key_is_unique(db):
    # 第二个相同 key 必须被数据库约束拒绝，不能产生第二次业务执行。
    first = AssistantAction(
        id="act-1", user_id="admin", tool_name="create_project",
        risk_level="high", status="preview", idempotency_key="same-key",
    )
    second = AssistantAction(
        id="act-2", user_id="admin", tool_name="create_project",
        risk_level="high", status="preview", idempotency_key="same-key",
    )
    db.add_all([first, second])
    with pytest.raises(IntegrityError):
        db.commit()
```

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_assistant_actions.py -q`

Expected: FAIL because the ORM model and schema do not exist.

- [ ] **Step 3: 添加 ORM、迁移和 Pydantic 类型**

为 `AssistantAction` 建立索引 `(user_id, thread_id, status)` 和唯一约束 `(user_id, idempotency_key)`；迁移必须兼容现有 SQLite 数据库。

- [ ] **Step 4: 运行测试并检查迁移**

Run: `cd backend && pytest tests/test_assistant_actions.py -q && alembic upgrade head`

Expected: PASS; 新表创建成功，旧表数据不变。

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/assistant backend/app/schemas.py backend/migrations/versions/0013_assistant_actions.py backend/tests/test_assistant_actions.py
git commit -m "feat: add assistant action persistence protocol"
```

### Task 2: 实现 root 范围和动作注册表

**Files:**
- Modify: `backend/app/access.py`
- Create: `backend/app/assistant/registry.py`
- Create: `backend/app/assistant/planner.py`
- Test: `backend/tests/test_root_chat_scope.py`
- Modify: `backend/tests/test_access.py`

**Interfaces:**
- `resolve_department_scope(allowed_department_ids, requested_department_ids, *, is_root=False, db=None) -> tuple[str, ...]`：root 且未指定范围时由调用方传入全部部门 ID。
- `ActionDefinition(name, input_model, required_roles, risk_level, preview, execute, sensitive_read=False)`。
- `get_action(name) -> ActionDefinition | None`。
- `list_actions() -> tuple[ActionDefinition, ...]`。
- `plan_input(text, principal, db) -> ActionPlan | None`；无法安全识别时返回 `ClarificationPlan`，不得调用写处理器。

- [ ] **Step 1: 写失败测试，覆盖 root 无部门、员工越权和动作白名单**

```python
def test_root_can_use_all_departments():
    assert resolve_department_scope((), None, is_root=True, db=db) == ("d1", "d2")

def test_employee_cannot_request_unassigned_department():
    with pytest.raises(PermissionError):
        resolve_department_scope(("d1",), ("d2",), is_root=False)

def test_unknown_action_is_not_registered():
    assert get_action("run_sql") is None
```

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_root_chat_scope.py tests/test_access.py -q`

Expected: FAIL because root scope and registry interfaces are absent.

- [ ] **Step 3: 实现 root scope 和最小动作目录**

注册只读知识/部门/项目/合同/费用/审批/工单查询，以及组织、项目、合同、知识、费用草稿、请假、工单、审批、付款、薪酬、删除等动作的名称、输入模型、角色和风险元数据；执行函数先引用现有 service，不能复制业务规则。

- [ ] **Step 4: 运行测试并做动作白名单审查**

Run: `cd backend && pytest tests/test_root_chat_scope.py tests/test_access.py -q`

Expected: PASS; `run_sql`, 任意 URL 和未注册名称均不可规划。

- [ ] **Step 5: Commit**

```bash
git add backend/app/access.py backend/app/assistant/registry.py backend/app/assistant/planner.py backend/tests/test_root_chat_scope.py backend/tests/test_access.py
git commit -m "feat: add root scope and controlled action registry"
```

### Task 3: 实现预览、确认、执行和审计服务

**Files:**
- Modify: `backend/app/assistant/service.py`
- Modify: `backend/app/audit/service.py`
- Modify: `backend/app/models.py` if audit relation fields are required
- Test: `backend/tests/test_assistant_actions.py`

**Interfaces:**
- `create_preview(db, principal, thread_id, plan) -> ActionPreview`。
- `confirm_action(db, principal, action_id, request) -> ActionResult | ActionPreview`。
- `cancel_action(db, principal, action_id) -> ActionResult`。
- `execute_action(db, principal, action_id, *, confirmation_phrase=None) -> ActionResult`。
- `is_confirmation_valid(action, principal, request) -> tuple[bool, str | None]`。

- [ ] **Step 1: 写失败测试，覆盖普通写、高风险写、敏感查询和版本冲突**

```python
def test_write_action_never_executes_before_confirmation(db, principal):
    preview = create_preview(db, principal, "thread-1", plan_for_create_project())
    assert preview.requires_confirmation is True
    assert db.query(Project).count() == 0

def test_expired_or_changed_action_is_rejected(db, principal):
    preview = create_preview(db, principal, "thread-1", plan_for_update_employee("employee-1"))
    expire(preview.action_id)
    result = confirm_action(
        db,
        principal,
        preview.action_id,
        ActionConfirmRequest(confirmation_phrase="确认执行", expected_parameter_hash=preview.parameter_hash),
    )
    assert result.status in {"expired", "failed"}

def test_high_risk_requires_explicit_phrase_and_audit(db, principal):
    preview = create_preview(db, principal, "thread-1", plan_for_payment("expense-1"))
    rejected = confirm_action(
        db,
        principal,
        preview.action_id,
        ActionConfirmRequest(confirmation_phrase="同意"),
    )
    assert rejected.status == "failed"
    assert db.query(AuditLog).filter_by(entity_id=preview.action_id, action="confirmation_rejected").count() == 1
```

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_assistant_actions.py -q`

Expected: FAIL because preview and confirmation services are absent.

- [ ] **Step 3: 实现哈希、令牌和动作状态机**

对规范化后的工具名、参数、目标对象版本和数据范围计算 `parameter_hash`；确认时重新读取对象并比较版本。普通写操作使用一次明确确认，高风险、敏感查询、批量和跨部门动作按注册元数据要求确认词或二次确认。动作执行在事务中调用现有 service，成功后写 `result_json` 和审计事件，重复幂等键返回原结果。

- [ ] **Step 4: 运行后端动作测试**

Run: `cd backend && pytest tests/test_assistant_actions.py -q`

Expected: PASS; 未确认、过期、参数变化、权限不足和版本冲突均不落库。

- [ ] **Step 5: Commit**

```bash
git add backend/app/assistant/service.py backend/app/audit/service.py backend/app/models.py backend/tests/test_assistant_actions.py
git commit -m "feat: enforce assistant confirmations and audit"
```

### Task 4: 接入聊天路由和结构化动作事件

**Files:**
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/agents/orchestrator.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_root_chat_scope.py`
- Test: `backend/tests/test_chat_context.py`

**Interfaces:**
- `POST /chat/ask` 继续接受现有 `AskRequest`，新增 `action_preview`, `action_result`, `clarification` 事件。
- `POST /chat/actions/{action_id}/confirm` 接受 `ActionConfirmRequest`，返回 `ActionResult`。
- `POST /chat/actions/{action_id}/cancel` 返回取消结果。
- `run_ask` 对 root 使用全部部门 ID，对结构化动作调用 planner/service；纯知识问答继续使用现有 SSE 节点。

- [ ] **Step 1: 写失败 API 测试**

```python
def test_root_chat_returns_knowledge_answer_without_department_membership(client, admin_token):
    response = client.post("/chat/ask", headers=admin_token, json={"question": "研发部制度是什么"})
    assert response.status_code == 200

def test_chat_write_returns_preview_event_and_confirm_endpoint(client, admin_token):
    events = stream_events(client, "/chat/ask", {"question": "新建研发项目"}, admin_token)
    action_id = find_event(events, "action_preview")["action_id"]
    result = client.post(f"/chat/actions/{action_id}/confirm", headers=admin_token, json={"confirmation_phrase": "确认执行"})
    assert result.status_code == 200
```

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_root_chat_scope.py tests/test_chat_context.py -q`

Expected: FAIL because root scope and action endpoints are not connected.

- [ ] **Step 3: 接入 root scope、planner 和动作 SSE 事件**

保持既有 `thread`、`sensitive_gate`、`retrieval`、`answer`、`faithfulness_check` 事件兼容；动作路径至少发送 `thread`, `action_preview` 或 `clarification`, `action_result`, `[DONE]`。确认接口只消费当前用户可见的动作。

- [ ] **Step 4: 运行完整后端测试**

Run: `cd backend && pytest -q`

Expected: PASS，现有员工问答、敏感门禁、上下文设置和所有业务回归测试通过。

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat.py backend/app/agents/orchestrator.py backend/app/schemas.py backend/tests/test_root_chat_scope.py backend/tests/test_chat_context.py
git commit -m "feat: connect admin assistant actions to chat"
```

### Task 5: 构建管理助手前端和确认卡片

**Files:**
- Create: `frontend/src/pages/AdminAssistantPage.tsx`
- Create: `frontend/src/components/AssistantActionCard.tsx`
- Modify: `frontend/src/api/chat.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/assistantAction.test.ts`

**Interfaces:**
- `AssistantActionEvent` discriminated union：`action_preview | clarification | action_result`。
- `confirmAssistantAction(actionId, confirmationPhrase?) -> Promise<ActionResult>`。
- `cancelAssistantAction(actionId) -> Promise<ActionResult>`。
- `AdminAssistantPage` 复用 `AnswerContent`, `PipelineFlow`, 线程加载和 SSE 解析逻辑，但不复制员工考勤门禁。

- [ ] **Step 1: 写失败组件测试**

```tsx
it("renders preview and does not confirm until the user clicks", async () => {
  render(<AssistantActionCard action={preview} onConfirm={onConfirm} onCancel={onCancel} />);
  expect(screen.getByText("待确认")).toBeInTheDocument();
  expect(onConfirm).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "确认执行" }));
  expect(onConfirm).toHaveBeenCalledWith(preview.action_id, "确认执行");
});
```

- [ ] **Step 2: 运行失败测试**

Run: `cd frontend && npm test -- --run src/assistantAction.test.ts`

Expected: FAIL because action event types, API functions and component do not exist.

- [ ] **Step 3: 实现事件类型、API 和助手页面**

预览卡片显示摘要、风险、变更、影响数量、过期时间和确认要求；高风险或批量动作显示确认词输入框；处理中禁用重复提交；过期、取消、失败和部分成功使用不同状态。助手输入直接调用 `/chat/ask`，不再使用请假/费用/工单关键词前置分流。

- [ ] **Step 4: 运行前端测试和类型检查**

Run: `cd frontend && npm test -- --run src/assistantAction.test.ts && npm run build`

Expected: PASS and TypeScript build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminAssistantPage.tsx frontend/src/components/AssistantActionCard.tsx frontend/src/api/chat.ts frontend/src/types/index.ts frontend/src/assistantAction.test.ts
git commit -m "feat: add admin assistant action cards"
```

### Task 6: 收敛双入口和企业全景

**Files:**
- Create: `frontend/src/pages/EnterpriseOverviewPage.tsx`
- Modify: `frontend/src/pages/AdminDashboardPage.tsx`
- Modify: `frontend/src/pages/AdminLayout.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/adminNavigation.ts`
- Test: `frontend/src/adminNavigation.test.ts`
- Test: `frontend/src/phase1Smoke.test.ts`

**Interfaces:**
- root 登录默认导航 `/admin/assistant`。
- `/admin/overview` 渲染 `EnterpriseOverviewPage`。
- `/admin/dashboard` 使用 `<Navigate to="/admin/overview" replace />`。
- 企业全景卡片通过 `navigate(`/admin/assistant?prompt=${encodeURIComponent(prompt)}`)` 把筛选条件交给助手。

- [ ] **Step 1: 写失败导航测试**

```ts
it("exposes only assistant and enterprise overview as primary admin entries", () => {
  expect(primaryAdminRoutes()).toEqual([
    { to: "/admin/assistant", label: "管理助手" },
    { to: "/admin/overview", label: "企业全景" },
  ]);
});
```

- [ ] **Step 2: 运行失败测试**

Run: `cd frontend && npm test -- --run src/adminNavigation.test.ts`

Expected: FAIL because the old navigation still exposes multiple groups.

- [ ] **Step 3: 实现路由、布局和企业全景入口**

把原管理驾驶舱内容迁移到企业全景页面或提取共享组件；顶部只保留两个一级入口，保留账号切换、通知和退出。原有详情页不删除，改由全景卡片、助手结果和必要的次级链接进入。保留旧 dashboard 重定向。

- [ ] **Step 4: 运行前端测试、构建和手工路由检查**

Run: `cd frontend && npm test -- --run src/adminNavigation.test.ts src/phase1Smoke.test.ts && npm run build`

Expected: PASS; root 登录后进入助手，旧 dashboard 链接重定向到全景。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/EnterpriseOverviewPage.tsx frontend/src/pages/AdminDashboardPage.tsx frontend/src/pages/AdminLayout.tsx frontend/src/App.tsx frontend/src/pages/LoginPage.tsx frontend/src/adminNavigation.ts frontend/src/adminNavigation.test.ts frontend/src/phase1Smoke.test.ts
git commit -m "feat: consolidate admin navigation into two entries"
```

### Task 7: 端到端验收与文档更新

**Files:**
- Modify: `README.md`
- Modify: `PRD.md`
- Create: `backend/tests/test_admin_assistant_e2e.py`
- Modify: `frontend/src/phase1Smoke.test.ts`

- [ ] **Step 1: 写端到端验收测试**

覆盖以下场景：root 查询跨部门知识；root 查询费用趋势；root 创建项目得到预览；确认后项目落库；付款/删除/改薪无确认不能执行；员工请求 root 范围被拒绝；全景卡片跳转助手。

- [ ] **Step 2: 运行全量测试**

Run: `cd backend && pytest -q`；`cd frontend && npm test -- --run && npm run build`

Expected: 所有后端和前端测试通过，构建无 TypeScript 错误。

- [ ] **Step 3: 启动服务做真实路由检查**

Run backend with `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` and frontend with `cd frontend && npm run dev`; sign in as root and employee, verify both navigation entries, one knowledge query, one preview/confirmation action, one expired confirmation, and one enterprise overview deep link.

- [ ] **Step 4: 更新产品文档**

在 `README.md` 和 `PRD.md` 中将“管理驾驶舱”改为“企业全景”，补充 root 管理助手、双入口和确认审计规则；不得出现来源项目名称作为产品文案。

- [ ] **Step 5: Commit**

```bash
git add README.md PRD.md backend/tests/test_admin_assistant_e2e.py frontend/src/phase1Smoke.test.ts
git commit -m "docs: document admin assistant dual entry workflow"
```
