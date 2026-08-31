import { create } from "zustand";
import type { DepartmentMembership, Role } from "../types";

/** 一个被记住的账号（含上次登录拿到的令牌，用于免密快速切换）。 */
export interface SavedAccount {
  userId: string;
  username: string;
  role: Role;
  departmentId: string | null;
  departments: DepartmentMembership[];
  roles: string[];
  token: string;
  /** 令牌过期时间（毫秒时间戳），从 JWT 的 exp 解析而来。 */
  expiresAt: number;
  lastUsedAt: number;
}

interface AuthState {
  token: string | null;
  userId: string | null;
  username: string | null;
  role: Role | null;
  departmentId: string | null;
  departments: DepartmentMembership[];
  roles: string[];
  /** 本机记住的全部账号，按最近使用排序。 */
  accounts: SavedAccount[];
  login: (
    token: string,
    userId: string,
    username: string,
    role: Role,
    departmentId: string | null,
    departments: DepartmentMembership[],
    roles?: string[],
    remember?: boolean,
  ) => void;
  /** 退出当前会话，但账号仍保留在已记住列表里，方便下次一键切回。 */
  logout: () => void;
  /** 切换到某个已记住的账号（令牌有效时直接切换）。 */
  switchTo: (userId: string) => SavedAccount | null;
  /** 用新令牌刷新某个已记住账号的信息。 */
  updateAccount: (userId: string, patch: Partial<SavedAccount>) => void;
  /** 彻底忘记某个账号。 */
  removeAccount: (userId: string) => void;
}

const STORAGE_KEY = "eirs_auth";
const ACCOUNTS_KEY = "eirs_accounts";

/** 从 JWT 里解析过期时间；解析失败时当作已过期，走重新登录。 */
function tokenExpiresAt(token: string): number {
  try {
    const payload = token.split(".")[1];
    if (!payload) return 0;
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

function loadAccounts(): SavedAccount[] {
  try {
    const raw = localStorage.getItem(ACCOUNTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SavedAccount[]) : [];
  } catch {
    return [];
  }
}

function loadSession(): Pick<AuthState, "token" | "userId" | "username" | "role" | "departmentId" | "departments" | "roles"> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { token: null, userId: null, username: null, role: null, departmentId: null, departments: [], roles: [] };
    return { userId: null, departments: [], roles: [], ...JSON.parse(raw) };
  } catch {
    return { token: null, userId: null, username: null, role: null, departmentId: null, departments: [], roles: [] };
  }
}

function saveAccounts(accounts: SavedAccount[]) {
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
}

function saveSession(session: Pick<AuthState, "token" | "userId" | "username" | "role" | "departmentId" | "departments" | "roles">) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export const useAuthStore = create<AuthState>((set, get) => ({
  ...loadSession(),
  accounts: loadAccounts(),

  login: (token, userId, username, role, departmentId, departments, roles = [], remember = true) => {
    const session = { token, userId, username, role, departmentId, departments, roles };
    saveSession(session);
    let accounts = get().accounts;
    if (remember) {
      const account: SavedAccount = {
        userId, username, role, departmentId, departments, roles, token,
        expiresAt: tokenExpiresAt(token),
        lastUsedAt: Date.now(),
      };
      accounts = [account, ...accounts.filter((a) => a.userId !== userId)];
      saveAccounts(accounts);
    }
    set({ ...session, accounts });
  },

  logout: () => {
    // 保留 accounts，只清掉当前会话
    const cleared = { token: null, userId: null, username: null, role: null, departmentId: null, departments: [], roles: [] };
    saveSession(cleared);
    set(cleared);
  },

  switchTo: (userId) => {
    const account = get().accounts.find((a) => a.userId === userId);
    if (!account) return null;
    const session = {
      token: account.token,
      userId: account.userId,
      username: account.username,
      role: account.role,
      departmentId: account.departmentId,
      departments: account.departments,
      roles: account.roles ?? [],
    };
    saveSession(session);
    const accounts = [
      { ...account, lastUsedAt: Date.now() },
      ...get().accounts.filter((a) => a.userId !== userId),
    ];
    saveAccounts(accounts);
    set({ ...session, accounts });
    return account;
  },

  updateAccount: (userId, patch) => {
    const accounts = get().accounts.map((a) => (a.userId === userId ? { ...a, ...patch } : a));
    saveAccounts(accounts);
    const current = get();
    if (current.userId === userId) {
      const updated = accounts.find((a) => a.userId === userId);
      if (updated) {
        const session = {
          token: updated.token, userId: updated.userId, username: updated.username,
          role: updated.role, departmentId: updated.departmentId, departments: updated.departments,
          roles: updated.roles ?? [],
        };
        saveSession(session);
        set({ ...session, accounts });
        return;
      }
    }
    set({ accounts });
  },

  removeAccount: (userId) => {
    const accounts = get().accounts.filter((a) => a.userId !== userId);
    saveAccounts(accounts);
    if (get().userId === userId) {
      const cleared = { token: null, userId: null, username: null, role: null, departmentId: null, departments: [], roles: [] };
      saveSession(cleared);
      set({ ...cleared, accounts });
      return;
    }
    set({ accounts });
  },
}));

/** 判断某个已记住账号的令牌是否还没过期。 */
export function isAccountFresh(account: SavedAccount | null | undefined): boolean {
  if (!account?.token) return false;
  // 留 30 秒余量，避免刚好过期
  return account.expiresAt > Date.now() + 30_000;
}
