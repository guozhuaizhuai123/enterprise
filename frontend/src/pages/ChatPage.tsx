import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import {
  askQuestion,
  cancelAssistantAction,
  confirmAssistantAction,
  getThreadContextSettings,
  updateThreadContextSettings,
} from "../api/chat";
import { deleteThread, listMessages, listMyDocuments, listThreads } from "../api/kb";
import { getChatSettings } from "../api/memory";
import {
  createLeaveRequest,
  createMyTodayAttendance,
  getMyTodayAttendance,
  getMyWorkSchedule,
  previewLeave,
} from "../api/schedule";
import { createExpense, previewExpense } from "../api/expenses";
import { createTicket, listDepartments, listParticipants, previewTicket } from "../api/tickets";
import PipelineFlow, { initialPipelineState, type PipelineState } from "../components/PipelineFlow";
import MyDocumentsPanel from "../components/MyDocumentsPanel";
import AnswerContent from "../components/AnswerContent";
import AssistantActionCard from "../components/AssistantActionCard";
import AssistantResultCard from "../components/AssistantResultCard";
import ChatContextToolbar from "../components/ChatContextToolbar";
import DocumentScopeDialog from "../components/DocumentScopeDialog";
import { getThreadStateAfterDeletion } from "../threadDeletion";
import { applyRetrievalEvent, verificationWarning } from "../pipelineState";
import UserMemoryDialog from "../components/UserMemoryDialog";
import EmployeeHeader from "../components/EmployeeHeader";
import TicketRequestNotice from "../components/TicketRequestNotice";
import LeaveRequestDialog, { type LeaveRequestPayload } from "../components/LeaveRequestDialog";
import TicketPreviewDialog from "../components/TicketPreviewDialog";
import ExpensePreviewDialog from "../components/ExpensePreviewDialog";
import WorkScheduleCard from "../components/WorkScheduleCard";
import AttendanceHistoryDialog from "../components/AttendanceHistoryDialog";
import AttendanceCheckinDialog from "../components/AttendanceCheckinDialog";
import { DEFAULT_MEMORY_LEVEL } from "../chatContext";
import { formatLeaveRange } from "../scheduleFormat";
import { decideAttendanceGate, shouldRefreshWorkSchedule } from "../attendanceGate";
import { routeForKey, type AssistantResultPresentation } from "../assistantPresentation";
import {
  decideChatPageOutcome,
  fallbackFormForQuestion,
  type ChatFormKind,
  type ChatFormPreview,
} from "../chatBusinessIntent";
import type {
  AssistantActionPreview,
  AssistantActionResult,
  AttendanceStatus,
  Citation,
  Department,
  DocumentItem,
  ExpenseDraft,
  MemoryLevel,
  MessageItem,
  MyWorkSchedule,
  LeavePreview,
  PipelineEvent,
  ThreadContextSettings,
  ThreadItem,
  TicketPreview,
  TicketType,
  ExpensePreview,
  UserOption,
} from "../types";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  streaming?: boolean;
  verificationWarning?: string;
  result?: AssistantResultPresentation;
  action?: AssistantActionPreview;
}

interface ActiveAskRequest {
  generation: number;
  controller: AbortController;
  originThreadId: string | null;
  readyThreadId: string | null;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const FORM_LABELS: Record<ChatFormKind, string> = {
  leave: "请假",
  ticket: "工单",
  expense: "报销",
};

function newThreadContext(memoryLevel: MemoryLevel = DEFAULT_MEMORY_LEVEL): ThreadContextSettings {
  return {
    memory_level: memoryLevel,
    document_scope_mode: "all",
    document_ids: [],
  };
}

// sensitive_gate/retrieval finish in milliseconds (no LLM call), so without an
// artificial minimum hold time their "running" state never renders visibly
// before "done" arrives right behind it — the pipeline looks static instead
// of stepping through nodes. answer/faithfulness_check are left at 0 so the
// real token-by-token streaming isn't slowed down.
function pipelineStepDelay(node: string, status: string): number {
  if ((node === "sensitive_gate" || node === "retrieval") && (status === "running" || status === "done")) {
    return 350;
  }
  return 0;
}

export default function ChatPage() {
  const { departments } = useAuthStore();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pipeline, setPipeline] = useState<PipelineState>(initialPipelineState);
  const [asking, setAsking] = useState(false);
  const [contextSettings, setContextSettings] = useState<ThreadContextSettings>(() => newThreadContext());
  const [savingContext, setSavingContext] = useState(false);
  const [loadingContext, setLoadingContext] = useState(false);
  const [documentScopeOpen, setDocumentScopeOpen] = useState(false);
  const [contextNotice, setContextNotice] = useState("");
  const [contextError, setContextError] = useState("");
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [workSchedule, setWorkSchedule] = useState<MyWorkSchedule | null>(null);
  const [leavePreview, setLeavePreview] = useState<LeavePreview | null>(null);
  const [submittingLeave, setSubmittingLeave] = useState(false);
  const [attendanceHistoryOpen, setAttendanceHistoryOpen] = useState(false);
  const [attendanceHistoryVersion, setAttendanceHistoryVersion] = useState(0);
  const [pendingAttendanceQuestion, setPendingAttendanceQuestion] = useState<string | null>(null);
  const [loginAttendanceOpen, setLoginAttendanceOpen] = useState(false);
  const [checkingAttendance, setCheckingAttendance] = useState(false);
  const [submittingAttendance, setSubmittingAttendance] = useState(false);
  const [attendanceError, setAttendanceError] = useState("");
  const [leaveError, setLeaveError] = useState("");
  const [ticketPreview, setTicketPreview] = useState<TicketPreview | null>(null);
  const [submittingTicket, setSubmittingTicket] = useState(false);
  const [ticketError, setTicketError] = useState("");
  const [expensePreview, setExpensePreview] = useState<ExpensePreview | null>(null);
  const [submittingExpense, setSubmittingExpense] = useState(false);
  const [expenseError, setExpenseError] = useState("");
  const [participants, setParticipants] = useState<UserOption[]>([]);
  const [allDepartments, setAllDepartments] = useState<Department[]>([]);
  const [actionResults, setActionResults] = useState<Record<string, AssistantActionResult>>({});
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);
  const threadIdRef = useRef<string | null>(null);
  const threadLoadVersionRef = useRef(0);
  const defaultMemoryLevelRef = useRef<MemoryLevel>(DEFAULT_MEMORY_LEVEL);
  const askGenerationRef = useRef(0);
  const activeAskRef = useRef<ActiveAskRequest | null>(null);

  useEffect(() => {
    listThreads().then(setThreads).catch(() => {});
    listMyDocuments().then(setDocuments).catch(() => {});
    getMyWorkSchedule().then(setWorkSchedule).catch(() => {});
    listParticipants().then(setParticipants).catch(() => {});
    listDepartments().then(setAllDepartments).catch(() => {});
    void loadNewThreadContext(threadLoadVersionRef.current);
    // 当天首次登录时检查考勤，未登记则弹出打卡选项
    getMyTodayAttendance()
      .then((attendance) => {
        if (decideAttendanceGate(attendance) === "require-attendance") {
          setLoginAttendanceOpen(true);
          setAttendanceError("");
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const refreshSchedule = () => {
      if (!shouldRefreshWorkSchedule(document.visibilityState)) return;
      getMyWorkSchedule().then(setWorkSchedule).catch(() => {});
    };
    const intervalId = window.setInterval(refreshSchedule, 5000);
    window.addEventListener("focus", refreshSchedule);
    document.addEventListener("visibilitychange", refreshSchedule);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshSchedule);
      document.removeEventListener("visibilitychange", refreshSchedule);
    };
  }, []);

  useEffect(() => () => {
    askGenerationRef.current += 1;
    activeAskRef.current?.controller.abort();
    activeAskRef.current = null;
  }, []);

  async function loadNewThreadContext(loadVersion: number) {
    setLoadingContext(true);
    getChatSettings()
      .then((settings) => {
        defaultMemoryLevelRef.current = settings.default_memory_level;
        if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === null) {
          setContextSettings(newThreadContext(settings.default_memory_level));
        }
      })
      .catch(() => {})
      .finally(() => {
        if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === null) {
          setLoadingContext(false);
        }
      });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!contextNotice) return;
    const timeoutId = window.setTimeout(() => setContextNotice(""), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [contextNotice]);

  async function openThread(id: string) {
    if (activeAskRef.current !== null) return;
    const loadVersion = ++threadLoadVersionRef.current;
    threadIdRef.current = id;
    setThreadId(id);
    setLoadingContext(true);
    setSavingContext(false);
    setDocumentScopeOpen(false);
    setContextNotice("");
    setContextError("");
    setContextSettings(newThreadContext(defaultMemoryLevelRef.current));
    setMessages([]);
    setPipeline(initialPipelineState);
    try {
      const [msgs, settings] = await Promise.all([
        listMessages(id),
        getThreadContextSettings(id),
      ]);
      if (loadVersion !== threadLoadVersionRef.current || threadIdRef.current !== id) return;
      setMessages(
        msgs.map((m: MessageItem) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations ?? [],
        })),
      );
      setContextSettings(settings);
      setLoadingContext(false);
    } catch {
      if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === id) {
        setContextSettings(newThreadContext(defaultMemoryLevelRef.current));
        setContextError("会话设置加载失败，请点击该会话重试或新建会话");
      }
    }
  }

  function newThread() {
    if (activeAskRef.current !== null) return;
    const loadVersion = ++threadLoadVersionRef.current;
    threadIdRef.current = null;
    setThreadId(null);
    setMessages([]);
    setPipeline(initialPipelineState);
    setContextSettings(newThreadContext(defaultMemoryLevelRef.current));
    setLoadingContext(true);
    setSavingContext(false);
    setDocumentScopeOpen(false);
    setContextNotice("");
    setContextError("");
    void loadNewThreadContext(loadVersion);
  }

  function openDocumentScope() {
    setDocumentScopeOpen(true);
    listMyDocuments().then(setDocuments).catch(() => {
      setContextError("文档列表加载失败，请稍后重试");
    });
  }

  async function saveContextSettings(next: ThreadContextSettings): Promise<void> {
    if (next.document_scope_mode === "selected" && next.document_ids.length === 0) {
      setContextError("请至少选择一份文档，或切换为全部文档");
      throw new Error("selected document scope is empty");
    }

    if (threadId === null) {
      setContextSettings(next);
      setContextError("");
      return;
    }

    const targetThreadId = threadId;
    const loadVersion = threadLoadVersionRef.current;
    const previous = contextSettings;
    setSavingContext(true);
    setContextError("");
    try {
      const saved = await updateThreadContextSettings(targetThreadId, next);
      if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === targetThreadId) {
        setContextSettings(saved);
      }
    } catch (error) {
      if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === targetThreadId) {
        setContextSettings(previous);
        setContextError("会话设置保存失败，已保留原设置");
      }
      throw error;
    } finally {
      if (loadVersion === threadLoadVersionRef.current && threadIdRef.current === targetThreadId) {
        setSavingContext(false);
      }
    }
  }

  async function applyDocumentScope(next: ThreadContextSettings): Promise<void> {
    await saveContextSettings(next);
    setDocumentScopeOpen(false);
  }

  async function handleDeleteThread(thread: ThreadItem) {
    if (activeAskRef.current !== null || deletingThreadId !== null) return;
    if (!confirm(`确定删除会话“${thread.title}”？其中的聊天记录也会被删除。`)) return;

    setDeletingThreadId(thread.id);
    try {
      await deleteThread(thread.id);
      const next = getThreadStateAfterDeletion(threads, threadId, thread.id);
      setThreads(next.threads);
      if (next.currentThreadDeleted) newThread();
    } catch {
      alert("删除会话失败，请稍后重试");
    } finally {
      setDeletingThreadId(null);
    }
  }

  async function handleAsk() {
    const question = input.trim();
    if (!question || activeAskRef.current !== null || savingContext || loadingContext || submittingLeave || checkingAttendance || submittingAttendance || submittingTicket || submittingExpense) return;
    setCheckingAttendance(true);
    setContextError("");
    try {
      const attendance = await getMyTodayAttendance();
      if (decideAttendanceGate(attendance) === "require-attendance") {
        setPendingAttendanceQuestion(question);
        setAttendanceError("");
        return;
      }
    } catch {
      setContextError("今日考勤状态检查失败，请稍后重试");
      return;
    } finally {
      setCheckingAttendance(false);
    }
    await processQuestion(question);
  }

  // 后端的对话规划层已经决定了这句话属于知识问答、实时查询、表单预填、页面
  // 导航还是受控动作，所以这里不再抢先发三个 preview 请求；只有后端完全没有
  // 给出业务事件时（例如旧版本后端）才退回本地规则。
  async function processQuestion(question: string) {
    const sawBusinessEvent = await askKnowledgeQuestion(question);
    if (sawBusinessEvent) return;
    await runFallbackFormPreview(question);
  }

  async function runFallbackFormPreview(question: string) {
    const form = fallbackFormForQuestion(question);
    if (form === null) return;
    try {
      if (form === "leave") {
        const preview = await previewLeave(question);
        if (!preview.is_leave_request) return;
        setLeavePreview(preview);
        setLeaveError("");
        return;
      }
      if (form === "expense") {
        const preview = await previewExpense(question);
        if (!preview.is_expense_request) return;
        setExpensePreview(preview);
        setExpenseError("");
        return;
      }
      const preview = await previewTicket(question);
      if (!preview.is_ticket_request) return;
      setTicketPreview(preview);
      setTicketError("");
    } catch {
      // 兜底路径失败时保留已经给出的知识回答，不覆盖聊天内容
    }
  }

  function updateAssistantMessage(assistantId: string, patch: Partial<ChatMessage>) {
    setMessages((current) =>
      current.map((message) => (message.id === assistantId ? { ...message, ...patch } : message)),
    );
  }

  function openFormDialog(form: ChatFormKind, preview: ChatFormPreview) {
    if (form === "leave") {
      setLeavePreview(preview as LeavePreview);
      setLeaveError("");
      return;
    }
    if (form === "ticket") {
      setTicketPreview(preview as TicketPreview);
      setTicketError("");
      return;
    }
    setExpensePreview(preview as ExpensePreview);
    setExpenseError("");
  }

  async function confirmChatAction(action: AssistantActionPreview) {
    if (actionBusyId !== null) return;
    setActionBusyId(action.action_id);
    try {
      const response = await confirmAssistantAction(
        action.action_id,
        action.confirmation_phrase || "确认执行",
        action.parameter_hash || "",
      );
      if ("status" in response) {
        setActionResults((current) => ({ ...current, [action.action_id]: response as AssistantActionResult }));
        if ((response as AssistantActionResult).status === "completed") {
          setContextNotice("操作已执行完成");
        }
      } else {
        setMessages((current) =>
          current.map((message) =>
            message.action?.action_id === action.action_id
              ? { ...message, action: response as AssistantActionPreview }
              : message,
          ),
        );
      }
    } catch {
      setContextError("操作执行失败，请重新发起");
    } finally {
      setActionBusyId(null);
    }
  }

  async function cancelChatAction(action: AssistantActionPreview) {
    if (actionBusyId !== null) return;
    setActionBusyId(action.action_id);
    try {
      const result = await cancelAssistantAction(action.action_id);
      setActionResults((current) => ({ ...current, [action.action_id]: result }));
    } catch {
      setContextError("操作取消失败，请稍后重试");
    } finally {
      setActionBusyId(null);
    }
  }

  async function submitTodayAttendance(status: AttendanceStatus, note: string) {
    if (submittingAttendance) return;
    const question = pendingAttendanceQuestion;
    const fromLogin = loginAttendanceOpen;
    if (question === null && !fromLogin) return;
    setSubmittingAttendance(true);
    setAttendanceError("");
    try {
      try {
        await createMyTodayAttendance({ status, note });
      } catch {
        const current = await getMyTodayAttendance().catch(() => null);
        if (current === null) throw new Error("attendance submission failed");
      }
      setPendingAttendanceQuestion(null);
      setLoginAttendanceOpen(false);
      setAttendanceHistoryVersion((current) => current + 1);
      setContextNotice("今日打卡已登记，管理员核定结果为准");
      if (question !== null) {
        await processQuestion(question);
      }
    } catch {
      setAttendanceError("打卡失败，请稍后重试");
    } finally {
      setSubmittingAttendance(false);
    }
  }

  async function submitLeave(payload: LeaveRequestPayload) {
    setSubmittingLeave(true);
    setLeaveError("");
    try {
      const request = await createLeaveRequest(payload);
      const now = Date.now();
      // 问题气泡已经在提问时追加过，这里只补充办理结果
      setMessages((current) => [
        ...current,
        {
          id: `leave-assistant-${now}`,
          role: "assistant",
          content: `请假申请已提交，等待管理员审批。\n\n类型：${request.leave_type}\n日期：${formatLeaveRange(request.start_date, request.end_date)}`,
          citations: [],
        },
      ]);
      setInput("");
      setLeavePreview(null);
      setContextNotice("请假申请已提交，管理员批准后会自动同步上班安排");
      setWorkSchedule(await getMyWorkSchedule());
    } catch {
      setLeaveError("提交失败，日期可能与已有申请冲突或不包含工作日");
    } finally {
      setSubmittingLeave(false);
    }
  }

  const ticketTypeLabels: Record<TicketType, string> = {
    same_department: "同部门协助",
    cross_department: "跨部门协助",
    question: "业务询问",
    issue: "问题反馈",
  };

  async function submitTicket(data: { ticket_type: TicketType; subject: string; description: string; target_user_id?: string; department_id?: string; requested_department_id?: string }) {
    setSubmittingTicket(true);
    setTicketError("");
    try {
      const ticket = await createTicket(data);
      const now = Date.now();
      setMessages((current) => [
        ...current,
        {
          id: `ticket-assistant-${now}`,
          role: "assistant",
          content: `工单已提交，相关同事会收到通知。\n\n主题：${ticket.subject}\n类型：${ticketTypeLabels[ticket.ticket_type] ?? ticket.ticket_type}\n状态：${ticket.status}`,
          citations: [],
        },
      ]);
      setInput("");
      setTicketPreview(null);
      setTicketError("");
      setContextNotice("工单已提交，相关人员会收到消息通知");
    } catch {
      setTicketError("提交失败，请稍后重试");
    } finally {
      setSubmittingTicket(false);
    }
  }

  async function submitExpense(data: ExpenseDraft) {
    setSubmittingExpense(true);
    setExpenseError("");
    try {
      const claim = await createExpense(data);
      const now = Date.now();
      setMessages((current) => [
        ...current,
        {
          id: `expense-assistant-${now}`,
          role: "assistant",
          content: `报销单已创建，请在报销页面提交审批。\n\n标题：${claim.title}\n金额：¥${claim.total_amount}\n状态：${claim.status}`,
          citations: [],
        },
      ]);
      setInput("");
      setExpensePreview(null);
      setExpenseError("");
      setContextNotice("报销单已创建，请在报销页面提交审批");
    } catch {
      setExpenseError("创建失败，请稍后重试");
    } finally {
      setSubmittingExpense(false);
    }
  }

  async function askKnowledgeQuestion(question: string): Promise<boolean> {
    if (contextSettings.document_scope_mode === "selected" && contextSettings.document_ids.length === 0) {
      setContextError("请重新选择文档范围后再提问");
      openDocumentScope();
      return true;
    }
    const askingThreadId = threadId;
    const initialContext = contextSettings;
    const generation = ++askGenerationRef.current;
    const controller = new AbortController();
    activeAskRef.current = {
      generation,
      controller,
      originThreadId: askingThreadId,
      readyThreadId: null,
    };
    setInput("");
    setAsking(true);
    setContextError("");
    setContextNotice("");
    setPipeline(initialPipelineState);

    const userMsg: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: question, citations: [] };
    const assistantId = `local-assistant-${Date.now()}`;
    setMessages((prev) => [...prev, userMsg, { id: assistantId, role: "assistant", content: "", citations: [], streaming: true }]);

    let citationsMeta: Citation[] = [];
    let sawBusinessEvent = false;
    const eventQueue: PipelineEvent[] = [];
    let draining = false;

    async function drainQueue() {
      if (draining) return;
      draining = true;
      try {
        while (eventQueue.length > 0) {
          if (!requestOwnsCurrentView(generation)) {
            eventQueue.length = 0;
            break;
          }
          const evt = eventQueue.shift()!;
          const handledAsBusiness = handlePipelineEvent(evt, assistantId, generation, (c) => {
            citationsMeta = c;
          });
          if (handledAsBusiness) sawBusinessEvent = true;
          const delay = pipelineStepDelay(evt.node as string, evt.status as string);
          if (delay > 0) await sleep(delay);
        }
      } finally {
        draining = false;
      }
    }

    try {
      await askQuestion(
        question,
        askingThreadId,
        (evt: PipelineEvent) => {
          if (!requestOwnsCurrentView(generation)) return;
          eventQueue.push(evt);
          void drainQueue();
        },
        askingThreadId === null
          ? { initialContext, signal: controller.signal }
          : { signal: controller.signal },
      );
      while (draining || eventQueue.length > 0) {
        await sleep(30);
      }
    } catch (error) {
      if (requestOwnsCurrentView(generation) && !(error instanceof DOMException && error.name === "AbortError")) {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: "请求失败，请稍后重试", streaming: false } : m)),
        );
      }
    } finally {
      if (activeAskRef.current?.generation === generation) {
        activeAskRef.current = null;
        setAsking(false);
        listThreads()
          .then((nextThreads) => {
            if (askGenerationRef.current === generation && activeAskRef.current === null) {
              setThreads(nextThreads);
            }
          })
          .catch(() => {});
      }
    }

    void citationsMeta;
    return sawBusinessEvent;
  }

  function requestOwnsCurrentView(generation: number): boolean {
    const request = activeAskRef.current;
    if (request === null || request.generation !== generation) return false;
    const owningThreadId = request.originThreadId ?? request.readyThreadId;
    return owningThreadId === null
      ? threadIdRef.current === null
      : threadIdRef.current === owningThreadId;
  }

  function handlePipelineEvent(
    evt: PipelineEvent,
    assistantId: string,
    generation: number,
    setCitationsRef: (c: Citation[]) => void,
  ): boolean {
    if (!requestOwnsCurrentView(generation)) return false;
    const node = evt.node as string;
    const status = evt.status as string;

    if (node === "thread" && status === "ready") {
      const request = activeAskRef.current;
      const readyThreadId = typeof evt.thread_id === "string" ? evt.thread_id : null;
      if (request === null || readyThreadId === null) return false;
      if (request.originThreadId !== null) {
        return false;
      }
      request.readyThreadId = readyThreadId;
      threadIdRef.current = readyThreadId;
      setThreadId(readyThreadId);
      return false;
    }

    // 统一业务事件：导航、表单预填、实时查询、受控动作、澄清
    const outcome = decideChatPageOutcome(evt, "employee");
    if (outcome.kind !== "none") {
      if (outcome.kind === "navigate") {
        updateAssistantMessage(assistantId, { content: outcome.notice, streaming: false });
        navigate(outcome.href);
        return true;
      }
      if (outcome.kind === "form") {
        updateAssistantMessage(assistantId, {
          content: `已根据你的描述整理好${FORM_LABELS[outcome.form]}表单，请确认后提交。`,
          streaming: false,
        });
        openFormDialog(outcome.form, outcome.preview);
        return true;
      }
      if (outcome.kind === "action") {
        updateAssistantMessage(assistantId, {
          content: outcome.content,
          streaming: false,
          action: outcome.preview,
        });
        return true;
      }
      updateAssistantMessage(assistantId, {
        content: outcome.content,
        streaming: false,
        result: outcome.result,
      });
      return true;
    }

    if (node === "scope" && status === "adjusted") {
      const documentIds = Array.isArray(evt.document_ids)
        ? evt.document_ids.filter((id): id is string => typeof id === "string")
        : [];
      if (documentIds.length > 0) {
        setContextSettings((current) => ({
          ...current,
          document_scope_mode: "selected",
          document_ids: documentIds,
        }));
        setContextNotice(`部分文档已失效，范围已调整为 ${documentIds.length} 份文档`);
      }
      return false;
    }

    if (node === "retrieval") {
      const matchedCount = (evt.matched as unknown[] | undefined)?.length ?? 0;
      setPipeline((prev) =>
        applyRetrievalEvent(prev, status === "running" ? "running" : "done", matchedCount),
      );
      return false;
    }

    if (node === "sensitive_gate") {
      setPipeline((prev) => ({
        ...prev,
        [node]: {
          status: status === "running" ? "running" : "done",
          detail:
            status === "done" && (evt.is_sensitive as boolean)
              ? (evt.reason as string)
              : undefined,
        },
      }));
      return false;
    }

    if (node === "answer") {
      if (status === "running") {
        const meta = (evt.citations_meta as Citation[]) ?? [];
        setCitationsRef(meta);
        setPipeline((prev) => ({ ...prev, answer: { status: "running" } }));
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, citations: meta } : m)),
        );
      } else if (status === "streaming") {
        const delta = (evt.delta as string) ?? "";
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + delta } : m)),
        );
      } else if (status === "done") {
        setPipeline((prev) => ({ ...prev, answer: { status: "done" } }));
      }
      return false;
    }

    if (node === "faithfulness_check") {
      const available = evt.available !== false;
      const faithful = evt.faithful as boolean | null | undefined;
      const concern = (evt.concern as string | undefined) ?? "";
      const warning = verificationWarning({ available, faithful, concern });
      setPipeline((prev) => ({
        ...prev,
        faithfulness_check: {
          status: status === "running" ? "running" : "done",
          detail: status === "done" && warning ? warning : undefined,
        },
      }));
      if (status === "done" && warning) {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId ? { ...message, verificationWarning: warning } : message,
          ),
        );
      }
      return false;
    }

    if (node === "final") {
      const finalAnswer = (evt.answer as string) ?? "";
      const citations = (evt.citations as Citation[]) ?? [];
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: finalAnswer, citations, streaming: false } : m,
        ),
      );
      if (status === "blocked") {
        setPipeline((prev) => {
          const next = { ...prev };
          (Object.keys(next) as (keyof PipelineState)[]).forEach((key) => {
            if (next[key].status === "running") next[key] = { status: "blocked" };
          });
          return next;
        });
      }
      if (evt.error_code === "document_scope_empty") {
        setContextError("所选文档已失效，请重新选择文档范围");
        openDocumentScope();
      }
    }
    return false;
  }

  const departmentLabels = Object.fromEntries(
    departments.map((department) => [department.id, department.name]),
  );
  const myDepartmentIds = departments.map((department) => department.id);
  const contextControlsDisabled = asking || savingContext || loadingContext || submittingLeave || checkingAttendance || submittingAttendance || submittingTicket || submittingExpense;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <EmployeeHeader extra={<button onClick={() => setMemoryOpen(true)} className="text-sm text-slate-500 hover:text-indigo-600">我的记忆</button>} />
      <TicketRequestNotice />

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-[300px] border-r border-slate-200 bg-white p-4 flex flex-col gap-4 overflow-y-auto">
          <MyDocumentsPanel />
          <div className="border-t border-slate-200 pt-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-slate-600">历史会话</h3>
              <button onClick={newThread} disabled={asking} className="text-xs text-indigo-600 hover:text-indigo-800 disabled:cursor-not-allowed disabled:opacity-40">
                新建会话
              </button>
            </div>
            <ul className="space-y-1 max-h-48 overflow-y-auto">
              {threads.map((t) => (
                <li key={t.id} className="flex items-center gap-1">
                  <button
                    onClick={() => void openThread(t.id)}
                    disabled={asking}
                    className={`min-w-0 flex-1 text-left text-sm truncate px-2 py-1 rounded disabled:cursor-not-allowed disabled:opacity-40 ${
                      threadId === t.id ? "bg-indigo-50 text-indigo-700" : "text-slate-500 hover:bg-slate-50"
                    }`}
                  >
                    {t.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteThread(t)}
                    disabled={asking || deletingThreadId !== null}
                    aria-label={`删除会话：${t.title}`}
                    className="shrink-0 rounded px-1.5 py-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {deletingThreadId === t.id ? "删除中" : "删除"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <main className="flex-1 flex flex-col">
          <WorkScheduleCard schedule={workSchedule} onOpenHistory={() => setAttendanceHistoryOpen(true)} />
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {messages.length === 0 && (
              <p className="text-sm text-slate-400 text-center mt-20">向企业知识库提问，答案会附带来源引用</p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-2xl rounded-lg px-4 py-3 text-sm ${
                    m.role === "user" ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-800"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <>
                      <AnswerContent text={m.content || (m.streaming ? "思考中..." : "")} citations={m.citations} />
                      {m.result && (
                        <AssistantResultCard
                          result={m.result}
                          href={routeForKey("employee", m.result.routeKey)}
                        />
                      )}
                      {m.action && (
                        <div className="mt-3">
                          <AssistantActionCard
                            action={m.action}
                            busy={actionBusyId === m.action.action_id}
                            result={actionResults[m.action.action_id] ?? null}
                            onConfirm={() => void confirmChatAction(m.action!)}
                            onCancel={() => void cancelChatAction(m.action!)}
                          />
                        </div>
                      )}
                      {m.verificationWarning && (
                        <div
                          className={`mt-3 rounded-md border px-3 py-2 text-xs leading-relaxed ${
                            m.verificationWarning === "大模型溯源核查已完毕，未发现明显问题"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                              : "border-amber-200 bg-amber-50 text-amber-800"
                          }`}
                        >
                          {m.verificationWarning}
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-slate-200 bg-white p-4">
            <div className="min-h-5 px-1 pb-1 text-xs" aria-live="polite">
              {contextError ? (
                <span className="text-red-600">{contextError}</span>
              ) : contextNotice ? (
                <span className="text-amber-700">{contextNotice}</span>
              ) : null}
            </div>
            <ChatContextToolbar
              value={contextSettings}
              disabled={contextControlsDisabled}
              onMemoryLevelChange={(memoryLevel) => {
                void saveContextSettings({ ...contextSettings, memory_level: memoryLevel }).catch(() => {});
              }}
              onOpenDocumentScope={openDocumentScope}
            />
            <div className="flex gap-2 rounded-b-md border border-slate-300 bg-white p-2">
              <input
                className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="输入你的问题..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleAsk();
                  }
                }}
                disabled={contextControlsDisabled}
              />
              <button
                onClick={handleAsk}
                disabled={contextControlsDisabled}
                className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
              >
                {asking ? "提问中..." : checkingAttendance ? "检查考勤..." : "发送"}
              </button>
            </div>
          </div>
        </main>

        <aside className="w-[340px] border-l border-slate-200 bg-white p-4 overflow-y-auto">
          <h3 className="text-sm font-medium text-slate-600 mb-2">Agent 执行流程</h3>
          <PipelineFlow state={pipeline} />
        </aside>
      </div>
      <UserMemoryDialog open={memoryOpen} onClose={() => setMemoryOpen(false)} />
      <AttendanceHistoryDialog open={attendanceHistoryOpen} onClose={() => setAttendanceHistoryOpen(false)} refreshKey={attendanceHistoryVersion} />
      {(pendingAttendanceQuestion !== null || loginAttendanceOpen) && (
        <AttendanceCheckinDialog
          mode={loginAttendanceOpen ? "login" : "question"}
          saving={submittingAttendance}
          error={attendanceError}
          onConfirm={(status, note) => void submitTodayAttendance(status, note)}
          onClose={() => {
            if (!submittingAttendance) {
              setPendingAttendanceQuestion(null);
              setLoginAttendanceOpen(false);
              setAttendanceError("");
            }
          }}
        />
      )}
      <LeaveRequestDialog
        open={leavePreview !== null}
        preview={leavePreview}
        saving={submittingLeave}
        error={leaveError}
        onConfirm={(payload) => void submitLeave(payload)}
        onClose={() => {
          if (!submittingLeave) {
            setLeavePreview(null);
            setLeaveError("");
          }
        }}
      />
      <TicketPreviewDialog
        open={ticketPreview !== null}
        preview={ticketPreview}
        participants={participants}
        departments={allDepartments}
        myDepartmentIds={myDepartmentIds}
        saving={submittingTicket}
        error={ticketError}
        onConfirm={(data) => void submitTicket(data)}
        onClose={() => {
          if (!submittingTicket) {
            setTicketPreview(null);
            setTicketError("");
          }
        }}
      />
      <ExpensePreviewDialog
        open={expensePreview !== null}
        preview={expensePreview}
        saving={submittingExpense}
        error={expenseError}
        onConfirm={(data) => void submitExpense(data)}
        onClose={() => {
          if (!submittingExpense) {
            setExpensePreview(null);
            setExpenseError("");
          }
        }}
      />
      <DocumentScopeDialog
        open={documentScopeOpen}
        documents={documents}
        departmentLabels={departmentLabels}
        value={contextSettings}
        saving={savingContext || asking}
        onApply={applyDocumentScope}
        onClose={() => {
          if (!savingContext && !asking) setDocumentScopeOpen(false);
        }}
      />
    </div>
  );
}
