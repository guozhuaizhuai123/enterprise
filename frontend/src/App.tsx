import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import AdminLayout from "./pages/AdminLayout";
import DepartmentsPage from "./pages/DepartmentsPage";
import DepartmentDetailPage from "./pages/DepartmentDetailPage";
import ChatPage from "./pages/ChatPage";
import SensitiveEventsPage from "./pages/SensitiveEventsPage";
import WorkSchedulesPage from "./pages/WorkSchedulesPage";
import CollaborationPage from "./pages/CollaborationPage";
import AdminTicketsPage from "./pages/AdminTicketsPage";
import OrganizationPage from "./pages/OrganizationPage";
import ExpensePage from "./pages/ExpensePage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import AdminProjectsPage from "./pages/AdminProjectsPage";
import AdminContractsPage from "./pages/AdminContractsPage";
import AdminProjectWorkspacePage from "./pages/AdminProjectWorkspacePage";
import AdminKnowledgePage from "./pages/AdminKnowledgePage";
import PayrollPage from "./pages/PayrollPage";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuthStore } from "./store/auth";

export default function App() {
  // 把已登录路由树按当前账号 userId 重挂载：切换账号时 userId 变化，React 会
  // 卸载重建当前页面，挂载时拉取数据的 effect 自动用新令牌重拉，历史会话 /
  // 知识文档 / 待办等全部刷新为新账号的数据，无需在每个页面单独处理。
  const userId = useAuthStore((s) => s.userId);
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute role="admin" />}>
          <Route path="/admin" element={<AdminLayout key={userId} />}>
            <Route index element={<DepartmentsPage />} />
            <Route path="departments/:departmentId" element={<DepartmentDetailPage />} />
            <Route path="work-schedules" element={<WorkSchedulesPage />} />
            <Route path="sensitive-events" element={<SensitiveEventsPage />} />
            <Route path="tickets" element={<AdminTicketsPage />} />
            <Route path="organization" element={<OrganizationPage />} />
            <Route path="approvals" element={<Navigate to="/admin/expenses?status=pending_approval" replace />} />
            <Route path="expenses" element={<ExpensePage />} />
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="projects" element={<AdminProjectsPage />} />
            <Route path="projects/:projectId" element={<AdminProjectWorkspacePage />} />
            <Route path="contracts" element={<AdminContractsPage />} />
            <Route path="knowledge" element={<AdminKnowledgePage />} />
            <Route path="payroll" element={<PayrollPage />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute role="employee" />}>
          <Route path="/chat" element={<ChatPage key={userId} />} />
          <Route path="/collaboration" element={<CollaborationPage key={userId} />} />
          <Route path="/approvals" element={<Navigate to="/expenses?status=pending_approval" replace />} />
          <Route path="/expenses" element={<ExpensePage key={userId} />} />
          <Route path="/applications" element={<Navigate to="/expenses" replace />} />
          <Route path="/dashboard" element={<AdminDashboardPage key={userId} />} />
          <Route path="/organization" element={<OrganizationPage key={userId} />} />
        </Route>

        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
