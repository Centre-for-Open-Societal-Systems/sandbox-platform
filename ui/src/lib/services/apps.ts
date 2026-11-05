/** API products, participant apps and their keys (participant portal + console). */

import { api } from "@/lib/api-client";
import type {
  AdminApp,
  ApiProduct,
  ApiProductDetail,
  ApiProductPayload,
  AppCreated,
  AppToken,
  AvailableApiProduct,
  EndpointOptionGroup,
  GatewayAuth,
  IamAccountState,
  IssuedCredential,
  ListQuery,
  Pagination,
  ParticipantApp,
} from "@/types/api";

const PORTAL = { audience: "participant" as const };
const ADMIN = { audience: "admin" as const };

export interface AppPayload {
  name: string;
  description?: string | null;
  callback_url?: string | null;
  allowed_ips?: string[];
}

// ------------------------------------------------------------- participant
export const appsApi = {
  availableProducts: () => api.get<AvailableApiProduct[]>("/participant/api-products", PORTAL),

  list: () => api.get<ParticipantApp[]>("/participant/apps", PORTAL),

  get: (appId: string) => api.get<ParticipantApp>(`/participant/apps/${appId}`, PORTAL),

  create: (payload: AppPayload & { api_product_ids: number[] }) =>
    api.post<AppCreated>("/participant/apps", payload, PORTAL),

  update: (appId: string, payload: AppPayload) =>
    api.put<ParticipantApp>(`/participant/apps/${appId}`, payload, PORTAL),

  remove: (appId: string) => api.delete<null>(`/participant/apps/${appId}`, PORTAL),

  requestProducts: (appId: string, apiProductIds: number[]) =>
    api.post<ParticipantApp>(`/participant/apps/${appId}/products`, { api_product_ids: apiProductIds }, PORTAL),

  withdrawProduct: (appId: string, apiProductId: number) =>
    api.delete<ParticipantApp>(`/participant/apps/${appId}/products/${apiProductId}`, PORTAL),

  issueKey: (appId: string) => api.post<IssuedCredential>(`/participant/apps/${appId}/credentials`, undefined, PORTAL),

  revokeKey: (appId: string, credentialId: string) =>
    api.delete<ParticipantApp>(`/participant/apps/${appId}/credentials/${credentialId}`, PORTAL),

  /** How the gateway identifies callers (API key, partner token or app token). */
  gatewayAuth: () => api.get<GatewayAuth>("/participant/gateway-auth", PORTAL),

  /** The app's access token: the sandbox makes the client-credentials request (secret stays server-side). */
  token: (appId: string) => api.post<AppToken>(`/participant/apps/${appId}/token`, undefined, PORTAL),
};

// ----------------------------------------------------------------- console
export const adminAppsApi = {
  listProducts: (query: ListQuery) =>
    api.post<{ api_products: ApiProduct[]; pagination: Pagination }>("/admin/api-products/list", query, ADMIN),

  getProduct: (id: number) => api.get<ApiProductDetail>(`/admin/api-products/${id}`, ADMIN),

  endpointOptions: () => api.get<EndpointOptionGroup[]>("/admin/api-products/endpoint-options", ADMIN),

  createProduct: (payload: ApiProductPayload) =>
    api.post<ApiProductDetail>("/admin/api-products", payload, ADMIN),

  updateProduct: (id: number, payload: ApiProductPayload) =>
    api.put<ApiProductDetail>(`/admin/api-products/${id}`, payload, ADMIN),

  publishProduct: (id: number, isPublished: boolean) =>
    api.post<ApiProduct>("/admin/api-products/publish", { id, is_published: isPublished }, ADMIN),

  deleteProduct: (id: number) => api.delete<null>(`/admin/api-products/${id}`, ADMIN),

  listApps: (query: ListQuery) =>
    api.post<{ apps: AdminApp[]; pagination: Pagination }>("/admin/apps/list", query, ADMIN),

  getApp: (id: number) => api.get<AdminApp>(`/admin/apps/${id}`, ADMIN),

  decide: (id: number, apiProductId: number, decision: "approve" | "reject" | "revoke", remarks?: string) =>
    api.post<AdminApp>(`/admin/apps/${id}/products/${apiProductId}/${decision}`, { remarks: remarks || null }, ADMIN),

  /** Approve a new (or rejected) app: open product requests are granted and its first key issued. */
  approveApp: (id: number, remarks?: string) =>
    api.post<AdminApp>(`/admin/apps/${id}/approve`, { remarks: remarks || null }, ADMIN),

  rejectApp: (id: number, reason: string) => api.post<AdminApp>(`/admin/apps/${id}/reject`, { reason }, ADMIN),

  revokeApp: (id: number, reason: string) => api.post<AdminApp>(`/admin/apps/${id}/revoke`, { reason }, ADMIN),

  restoreApp: (id: number) => api.post<AdminApp>(`/admin/apps/${id}/restore`, undefined, ADMIN),

  resync: (id: number) => api.post<AdminApp>(`/admin/apps/${id}/gateway-sync`, undefined, ADMIN),

  /** A participant's Keycloak user and roles. */
  iamAccount: (participantId: number) =>
    api.get<IamAccountState>(`/admin/participants/${participantId}/iam-account`, ADMIN),

  retryIamAccount: (participantId: number) =>
    api.post<IamAccountState>(`/admin/participants/${participantId}/iam-account/retry`, undefined, ADMIN),
};
