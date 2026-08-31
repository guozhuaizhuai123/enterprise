export type Role = "admin" | "employee";

export type MemoryLevel = 1 | 2 | 3 | 4 | 5;
export type DocumentScopeMode = "all" | "selected";

export interface MemoryItem {
  id: string;
  title: string;
  content: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ThreadContextSettings {
  memory_level: MemoryLevel;
  document_scope_mode: DocumentScopeMode;
  document_ids: string[];
}

export interface UserChatSettings {
  default_memory_level: MemoryLevel;
}

export interface DepartmentMemoryItem extends MemoryItem {
  department_id: string;
  created_by: string;
  updated_by: string;
}

export interface Department {
  id: string;
  name: string;
  created_at: string;
}

export interface Employee {
  id: string;
  username: string;
  password: string | null;
  department_id: string;
  departments?: DepartmentMembership[];
  created_at: string;
}

export type EmploymentStatus = "probation" | "active" | "suspended" | "terminated";
export type OrgRole = "employee" | "hr" | "manager" | "finance";

export interface OrgUnit {
  id: string;
  name: string;
  code: string | null;
  parent_id: string | null;
  manager_id: string | null;
  manager_name: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrgMembership {
  department_id: string;
  department_name: string;
  position: string;
  is_primary: boolean;
  joined_at: string | null;
  left_at: string | null;
}

export interface OrgEmployee {
  id: string;
  username: string;
  full_name: string;
  phone: string;
  email: string;
  hire_date: string | null;
  termination_date: string | null;
  status: EmploymentStatus;
  position: string;
  level: string;
  manager_id: string | null;
  manager_name: string;
  salary: string;
  notes: string;
  department_id: string | null;
  departments: OrgMembership[];
  roles: string[];
  created_at: string;
  updated_at: string;
}

export interface OrgEmployeeInput {
  username: string;
  password: string;
  full_name: string;
  department_ids: string[];
  primary_department_id: string;
  phone?: string;
  email?: string;
  hire_date?: string | null;
  status?: EmploymentStatus;
  position?: string;
  level?: string;
  manager_id?: string | null;
  salary?: string;
  roles?: OrgRole[];
}

export type OrgEmployeeUpdate = Partial<
  Omit<OrgEmployeeInput, "username" | "password">
> & { termination_date?: string | null; notes?: string };

export type ApprovalStatus = "pending_approval" | "approved" | "rejected" | "cancelled";
export type ApprovalActionType = "submit" | "approve" | "reject" | "cancel";

export interface ApprovalTask {
  id: string;
  instance_id: string;
  entity_type: string;
  entity_id: string;
  requester_id: string;
  requester_name: string;
  node_name: string;
  sequence: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  assignee_id: string | null;
  assignee_role: string | null;
  department_id: string | null;
  instance_status: ApprovalStatus;
  version: number;
  created_at: string;
  acted_at: string | null;
}

export interface ApprovalActionRecord {
  id: string;
  task_id: string | null;
  actor_id: string;
  actor_name: string;
  action: ApprovalActionType;
  comment: string;
  from_status: string;
  to_status: string;
  created_at: string;
}

export interface ApprovalHandler {
  id: string;
  username: string;
  display_name: string;
}

export interface ApprovalRouteStep {
  sequence: number;
  name: string;
  status: "approved" | "pending" | "rejected" | "cancelled" | "upcoming";
  handlers: ApprovalHandler[];
}

export interface ApprovalInstance {
  id: string;
  workflow_code: string;
  workflow_name: string;
  entity_type: string;
  entity_id: string;
  requester_id: string;
  requester_name: string;
  status: ApprovalStatus;
  current_node_sequence: number;
  version: number;
  submitted_at: string;
  completed_at: string | null;
  updated_at: string;
  tasks: ApprovalTask[];
  actions: ApprovalActionRecord[];
  approval_route: ApprovalRouteStep[];
  can_approve: boolean;
  can_reject: boolean;
  can_cancel: boolean;
}

/** 审批人视角的一条已处理记录（我的审批历史）。 */
export interface ApprovalHistoryItem {
  id: string;
  instance_id: string;
  entity_type: string;
  entity_id: string;
  node_name: string;
  sequence: number;
  requester_id: string;
  requester_name: string;
  action: ApprovalActionType;
  comment: string;
  actor_name: string;
  from_status: string;
  to_status: string;
  instance_status: string;
  created_at: string;
}

export interface ExpenseItem {
  id?: string;
  expense_date: string;
  category: string;
  description: string;
  vendor: string;
  invoice_no: string;
  amount: string;
  tax_amount: string;
  sort_order?: number;
}

export interface ExpenseAttachment {
  id: string;
  file_id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ExpensePayment {
  id: string;
  paid_by: string;
  amount: string;
  currency: string;
  method: string;
  reference: string;
  payment_date: string;
  created_at: string;
}

export interface ExpenseClaim {
  id: string;
  claim_no: string;
  requester_id: string;
  requester_name: string;
  department_id: string | null;
  department_name?: string;
  title: string;
  purpose: string;
  project_code: string;
  currency: string;
  total_amount: string;
  status: "draft" | "pending_approval" | "rejected" | "payment_pending" | "paid" | "cancelled";
  approval_instance_id: string | null;
  version: number;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  items: ExpenseItem[];
  attachments: ExpenseAttachment[];
  payment: ExpensePayment | null;
}

export interface PayrollSetting {
  auto_enabled: boolean;
  pay_day: number;
  generation_lead_days: number;
  currency: string;
  approval_role: string;
  updated_at: string;
}

export interface PayrollLine {
  id: string;
  employee_id: string;
  employee_name: string;
  salary_input: string;
  gross_amount: string;
  net_amount: string;
}

export interface PayrollRun {
  id: string;
  period: string;
  pay_date: string;
  generation_date: string;
  status: string;
  expense_claim_id: string | null;
  total_amount: string;
  generated_at: string | null;
  created_at: string;
  lines: PayrollLine[];
}

export interface ExpenseDraft {
  title: string;
  purpose: string;
  project_code: string;
  currency: "CNY";
  total_amount: string;
  items: ExpenseItem[];
}

export interface DashboardMetricBucket {
  count: number;
  amount: string;
}

export interface DashboardOverview {
  period_start: string;
  period_end: string;
  timezone: string;
  organization: { active_employees: number; departments: number } | null;
  expenses: Record<string, DashboardMetricBucket>;
  approvals: { pending: number };
  operations: {
    pending_leave_requests: number;
    attendance_missing_today: number;
    unfinished_todos: number;
  };
  monthly_expenses: Array<{ month: string; count: number; amount: string }>;
}

export interface DepartmentMembership {
  id: string;
  name: string;
  position: string;
  access_level: string;
}

export interface DocumentItem {
  id: string;
  department_id: string;
  title: string;
  category: string;
  sensitive: boolean;
  owner_id: string | null;
  owner_name: string;
  owner_active: boolean;
  project_id: string | null;
  project_name: string;
  contract_id: string | null;
  contract_name: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentItem {
  content: string;
}

export interface UserOption {
  id: string;
  username: string;
  role: Role;
  department_name?: string;
  departments?: string[];
  department_ids?: string[];
}

export interface SensitiveEvent {
  id: string;
  user_id: string | null;
  username: string;
  department_name: string;
  question: string;
  matched_keyword: string;
  reason: string;
  created_at: string;
}

export interface SensitiveKeyword {
  id: string;
  keyword: string;
  enabled: boolean;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleDay {
  weekday: number;
  enabled: boolean;
  start_time: string;
  end_time: string;
  updated_at?: string | null;
}

export interface LeaveRequest {
  id: string;
  user_id: string;
  username: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export type HolidayScope = "company" | "department";

export interface HolidayPeriod {
  id: string;
  name: string;
  scope_type: HolidayScope;
  department_id: string | null;
  department_name: string;
  start_date: string;
  end_date: string;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type AttendanceStatus = "present" | "late" | "absent" | "remote";

export interface AttendanceRecord {
  id: string;
  user_id: string;
  username: string;
  attendance_date: string;
  status: AttendanceStatus;
  note: string;
  recorded_by: string;
  created_at: string;
  updated_at: string;
}

export interface AttendanceHistory {
  year: number;
  period_start: string;
  period_end: string;
  scheduled_work_days: number;
  organization_holiday_days: number;
  weekly_rest_days: number;
  approved_leave_days: number;
  expected_attendance_days: number;
  recorded_attendance_days: number;
  unrecorded_attendance_days: number;
  present_days: number;
  late_days: number;
  absent_days: number;
  remote_days: number;
  attendance_rate: number | null;
  leave_requests: LeaveRequest[];
  holidays: HolidayPeriod[];
  attendance_records: AttendanceRecord[];
}

export interface MyWorkSchedule {
  days: ScheduleDay[];
  leave_requests: LeaveRequest[];
  holidays: HolidayPeriod[];
}

export interface EmployeeWorkSchedule {
  user_id: string;
  username: string;
  days: ScheduleDay[];
}

export interface LeavePreview {
  is_leave_request: boolean;
  leave_type: string | null;
  start_date: string | null;
  end_date: string | null;
  reason: string;
}

export interface Citation {
  tag: string;
  document_id: string;
  title: string;
  snippet: string;
}

export interface ThreadItem {
  id: string;
  title: string;
  created_at: string;
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export type NodeKey = "sensitive_gate" | "retrieval" | "answer" | "faithfulness_check";
export type NodeStatus = "idle" | "running" | "done" | "blocked";

export interface PipelineEvent {
  node: string;
  status: string;
  [key: string]: unknown;
}
export interface AssistantActionPreview { action_id:string; tool_name:string; risk_level:string; summary:string; confirmation_phrase?:string|null; confirmation_step:number; confirmation_steps_required:number; expires_at?:string|null; parameter_hash?:string|null; changes?: Array<{field:string; before?:unknown; after?:unknown}> }
export interface AssistantActionResult { action_id:string; status:string; result?:Record<string,unknown>|null; error_code?:string|null }

export type TicketType = "same_department" | "cross_department" | "question" | "issue";
export interface Ticket {
  id: string;
  requester_id: string;
  requester_name: string;
  target_user_id: string | null;
  target_user_name: string;
  department_id: string | null;
  department_name: string;
  ticket_type: TicketType;
  subject: string;
  description: string;
  status: string;
  requested_department_id: string | null;
  requested_department_name: string;
  requires_admin: boolean;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}
export interface TicketMessage { id: string; ticket_id: string; sender_id: string; sender_name: string; content: string; created_at: string; }
export interface Todo { id: string; assignee_id: string; assignee_name: string; created_by: string; creator_name: string; ticket_id: string | null; title: string; description: string; status: string; due_at: string | null; completed_at: string | null; created_at: string; updated_at: string; }
export interface TicketEvent { id: string; ticket_id: string | null; todo_id: string | null; actor_id: string; actor_name: string; event_type: string; detail: string; created_at: string; }
export interface Notification { id: string; ticket_id: string | null; todo_id: string | null; approval_instance_id: string | null; expense_claim_id: string | null; kind: string; content: string; read_at: string | null; created_at: string; }

export interface TicketPreview {
  is_ticket_request: boolean;
  ticket_type: TicketType | null;
  subject: string | null;
  description: string | null;
  target_username: string | null;
  department_name: string | null;
}

export interface ExpensePreview {
  is_expense_request: boolean;
  title: string | null;
  purpose: string | null;
  total_amount: string | null;
  category: string | null;
  department_name: string | null;
  description: string | null;
}

// ---------------------------------------------------------------------------
// 项目管理与合同管理
// ---------------------------------------------------------------------------

export type ProjectType = "internal" | "client" | "rd" | "other";
export type ProjectStatus = "preparing" | "active" | "closed" | "paused" | "cancelled";

export interface Project {
  id: string;
  code: string;
  name: string;
  type: ProjectType;
  status: ProjectStatus;
  department_id: string | null;
  department_name: string;
  manager_id: string | null;
  manager_name: string;
  start_date: string | null;
  end_date: string | null;
  budget: string | null;
  description: string;
  contract_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectWorkspace {
  project: Project;
  contracts: Contract[];
  documents: DocumentItem[];
}

export interface ProjectInput {
  code: string;
  name: string;
  type: ProjectType;
  status: ProjectStatus;
  department_id: string | null;
  manager_id: string | null;
  start_date: string | null;
  end_date: string | null;
  budget: string | null;
  description: string;
}

export type ContractType = "purchase" | "sales" | "service" | "lease" | "nda" | "other";
export type ContractStatus = "draft" | "reviewing" | "active" | "fulfilled" | "expired" | "terminated";

export interface Contract {
  id: string;
  code: string;
  name: string;
  type: ContractType;
  status: ContractStatus;
  project_id: string | null;
  project_name: string;
  party_a: string;
  party_b: string;
  amount: string | null;
  currency: string;
  sign_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  owner_id: string | null;
  owner_name: string;
  description: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContractInput {
  code: string;
  name: string;
  type: ContractType;
  status: ContractStatus;
  project_id: string | null;
  party_a: string;
  party_b: string;
  amount: string | null;
  currency: string;
  sign_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  owner_id: string | null;
  description: string;
}
