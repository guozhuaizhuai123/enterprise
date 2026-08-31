import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import type { Role } from "../types";

export function ProtectedRoute({ role }: { role: Role }) {
  const { token, role: currentRole } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  if (currentRole !== role) return <Navigate to="/login" replace />;
  return <Outlet />;
}
