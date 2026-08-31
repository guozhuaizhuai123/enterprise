import axios from "axios";
import { apiClient, API_BASE } from "./client";
import type { DepartmentMembership, Role } from "../types";

export interface LoginResponse {
  user_id: string;
  access_token: string;
  role: Role;
  department_id: string | null;
  departments: DepartmentMembership[];
  username: string;
  roles: string[];
}

export interface MeResponse {
  user_id: string;
  username: string;
  role: Role;
  department_id: string | null;
  departments: DepartmentMembership[];
  roles: string[];
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await apiClient.post<LoginResponse>("/auth/login", { username, password });
  return res.data;
}

/** 校验令牌是否仍然有效，返回当前用户信息；失效会抛 401。 */
export async function fetchMe(token?: string): Promise<MeResponse> {
  if (token) {
    // 校验「其他已记住账号」的令牌时不能用 apiClient：它的 401 拦截器会
    // 直接把当前登录态清掉并跳登录页。这里用独立实例避免误伤当前会话。
    const res = await axios.get<MeResponse>(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.data;
  }
  const res = await apiClient.get<MeResponse>("/auth/me");
  return res.data;
}
