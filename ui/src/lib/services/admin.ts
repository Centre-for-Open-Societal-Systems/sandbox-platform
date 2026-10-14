/** Back-office console API calls. */

import { api } from "@/lib/api-client";
import type {
  AdminDashboard,
  AdminParticipantDetail,
  AdminSession,
  AdminUser,
  ApiLog,
  DropdownItem,
  ListQuery,
  PermissionFlag,
  PermissionNode,
  Pagination,
  Participant,
  Role,
  SupportQuery,
  UserActionLog,
} from "@/types/api";

const OPTIONS = { audience: "admin" as const };

interface PagedRows<T> {
  pagination: Pagination;
  [key: string]: T[] | Pagination;
}

function rows<T>(page: PagedRows<T>, key: string): T[] {
  return (page[key] as T[]) ?? [];
}

// ------------------------------------------------------------------- auth
export const adminApi = {
  login: (username: string, password: string) =>
    api.post<AdminSession>("/admin/auth/login", { username, password }),

  logout: () => api.post<null>("/admin/auth/logout", undefined, OPTIONS),

  profile: () => api.get<AdminUser>("/admin/auth/profile", OPTIONS),

  dashboard: () => api.get<AdminDashboard>("/admin/auth/dashboard", OPTIONS),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<null>(
      "/admin/auth/change-password",
      { old_password: oldPassword, new_password: newPassword },
      OPTIONS,
    ),

  /** `is_fixed_otp`: no mail on this server, so the reset uses the fixed code (000000). */
  forgotPassword: (emailId: string) =>
    api.post<{ is_fixed_otp?: boolean } | null>("/admin/auth/forgot-password", { email_id: emailId }),

  setPassword: (token: string, newPassword: string) =>
    api.post<null>("/admin/auth/set-password", { token, new_password: newPassword }),

  /** Development reset while mail is off: email + the fixed code instead of the emailed link. */
  setPasswordWithCode: (emailId: string, otp: string, newPassword: string) =>
    api.post<null>("/admin/auth/set-password", { email_id: emailId, otp, new_password: newPassword }),

  // ------------------------------------------------ back-office users
  listUsers: async (query: ListQuery) => {
    const page = await api.post<PagedRows<AdminUser>>("/admin/users/list", query, OPTIONS);
    return { users: rows<AdminUser>(page, "users"), pagination: page.pagination };
  },

  getUser: (adminId: number) => api.get<AdminUser>(`/admin/users/${adminId}`, OPTIONS),

  createUser: (payload: Record<string, unknown>) =>
    api.post<AdminUser>("/admin/users", payload, OPTIONS),

  updateUser: (payload: Record<string, unknown>) =>
    api.put<AdminUser>("/admin/users", payload, OPTIONS),

  toggleUser: (id: number, isEnabled?: boolean) =>
    api.post<AdminUser>("/admin/users/toggle", { id, is_enabled: isEnabled }, OPTIONS),

  deleteUser: (adminId: number) =>
    api.delete<null>(`/admin/users/${adminId}`, OPTIONS),

  resendInvite: (adminId: number) =>
    api.post<null>(`/admin/users/${adminId}/invite`, undefined, OPTIONS),

  // ------------------------------------------------------------- roles
  listRoles: async (query: ListQuery) => {
    const page = await api.post<PagedRows<Role>>("/admin/roles/list", query, OPTIONS);
    return { roles: rows<Role>(page, "roles"), pagination: page.pagination };
  },

  roleDropdown: () => api.get<DropdownItem[]>("/admin/roles/dropdown", OPTIONS),

  getRole: (roleId: number) => api.get<Role>(`/admin/roles/${roleId}`, OPTIONS),

  createRole: (payload: Record<string, unknown>) =>
    api.post<Role>("/admin/roles", payload, OPTIONS),

  updateRole: (payload: Record<string, unknown>) => api.put<Role>("/admin/roles", payload, OPTIONS),

  toggleRole: (id: number, isEnabled?: boolean) =>
    api.post<Role>("/admin/roles/toggle", { id, is_enabled: isEnabled }, OPTIONS),

  deleteRole: (roleId: number) => api.delete<null>(`/admin/roles/${roleId}`, OPTIONS),

  // ------------------------------------------------------- permissions
  permissions: (roleId?: number) =>
    api.get<PermissionNode[]>("/admin/permissions", { ...OPTIONS, query: { role_id: roleId } }),

  updatePermissions: (roleId: number, permissions: PermissionFlag[]) =>
    api.put<null>("/admin/permissions", { role_id: roleId, permissions }, OPTIONS),

  // -------------------------------------------------------- participants
  listParticipants: async (query: ListQuery, environment?: string) => {
    const page = await api.post<PagedRows<Participant>>("/admin/participants/list", query, {
      ...OPTIONS,
      query: environment ? { environment } : undefined,
    });
    return { participants: rows<Participant>(page, "participants"), pagination: page.pagination };
  },

  /** Participants who asked for the environment and await a decision. */
  listPending: async (query: ListQuery, environment: string) => {
    const page = await api.post<PagedRows<Participant>>("/admin/participants/pending", query, {
      ...OPTIONS,
      query: { environment },
    });
    return { participants: rows<Participant>(page, "participants"), pagination: page.pagination };
  },

  listRejected: async (query: ListQuery, environment?: string) => {
    const page = await api.post<PagedRows<Participant>>("/admin/participants/rejected", query, {
      ...OPTIONS,
      query: environment ? { environment } : undefined,
    });
    return { participants: rows<Participant>(page, "participants"), pagination: page.pagination };
  },

  getParticipant: (participantId: number) =>
    api.get<AdminParticipantDetail>(`/admin/participants/${participantId}`, OPTIONS),

  /** A participant's uploaded document (ID proof, certificate), fetched with the admin session. */
  participantFile: (path: string) => api.file(`/files/${path.replace(/^\/+/, "")}`, OPTIONS),

  approveEnvironment: (participantId: number, environment: string, remarks?: string) =>
    api.post<Participant>("/admin/participants/approve", { participant_id: participantId, environment, remarks }, OPTIONS),

  rejectParticipant: (participantId: number, environment: string, reason: string) =>
    api.post<Participant>(
      "/admin/participants/reject",
      { participant_id: participantId, environment, rejection_reason: reason },
      OPTIONS,
    ),

  toggleParticipant: (id: number, isEnabled?: boolean) =>
    api.post<Participant>("/admin/participants/toggle", { id, is_enabled: isEnabled }, OPTIONS),

  deleteParticipant: (participantId: number) =>
    api.delete<null>(`/admin/participants/${participantId}`, OPTIONS),

  exportParticipants: (filters: Record<string, unknown>, format: "xlsx" | "csv" = "xlsx") =>
    api.download("/admin/participants/export", { format, filters }, OPTIONS),

  // ----------------------------------------------------------- queries
  listQueries: async (query: ListQuery) => {
    const page = await api.post<PagedRows<SupportQuery>>(
      "/admin/participants/queries/list",
      query,
      OPTIONS,
    );
    return { queries: rows<SupportQuery>(page, "queries"), pagination: page.pagination };
  },

  respondToQuery: (queryId: number, response: string, status = 2) =>
    api.post<null>(
      "/admin/participants/queries/respond",
      { query_id: queryId, response, status },
      OPTIONS,
    ),

  // -------------------------------------------------------------- logs
  apiHistory: async (query: ListQuery) => {
    const page = await api.post<PagedRows<ApiLog>>("/admin/logs/api-history", query, OPTIONS);
    return { logs: rows<ApiLog>(page, "logs"), pagination: page.pagination };
  },

  apiHistoryDetail: (logId: number) => api.get<ApiLog>(`/admin/logs/api-history/${logId}`, OPTIONS),

  userTracking: async (query: ListQuery) => {
    const page = await api.post<PagedRows<UserActionLog>>(
      "/admin/logs/user-tracking",
      query,
      OPTIONS,
    );
    return { logs: rows<UserActionLog>(page, "logs"), pagination: page.pagination };
  },

  exportApiHistory: (filters: Record<string, unknown>, format: "xlsx" | "csv" = "xlsx") =>
    api.download("/admin/logs/api-history/export", { format, filters }, OPTIONS),

  exportUserTracking: (filters: Record<string, unknown>, format: "xlsx" | "csv" = "xlsx") =>
    api.download("/admin/logs/user-tracking/export", { format, filters }, OPTIONS),
};
