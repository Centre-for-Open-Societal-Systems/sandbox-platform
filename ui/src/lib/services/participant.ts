/** Portal registration, portal and public content calls. */

import { api } from "@/lib/api-client";
import type {
  ApiLog,
  ApiLogDetail,
  Country,
  DropdownItem,
  FaqGroup,
  ListQuery,
  Pagination,
  Participant,
  PromotionRequest,
  PublicHome,
  SupportQuery,
  TermSection,
  ParticipantSession,
} from "@/types/api";

const OPTIONS = { audience: "participant" as const };

export interface SignupPayload {
  first_name: string;
  last_name: string;
  country_code: string;
  mobile_number: string;
  email_id: string;
  category_id: number;
  company_name: string;
  password: string;
  declaration: boolean;
}

interface SignupResult {
  unique_id: string;
  masked_email: string;
  otp_validity_seconds: number;
  /** True while the server sends no mail: the code is the fixed development one (000000). */
  is_fixed_otp?: boolean;
}

interface RegistrationState {
  unique_id: string;
  first_name: string | null;
  email_id: string | null;
  masked_email: string;
  country_code: string;
  is_email_verified: boolean;
}

export const participantApi = {
  // ---------------------------------------------------- registration
  checkEmail: (emailId: string) =>
    api.post<{ available: boolean }>("/participant/auth/check-email", { email_id: emailId }),

  signup: (payload: SignupPayload) => api.post<SignupResult>("/participant/auth/signup", payload),

  verifyEmail: (uniqueId: string, otp: string) =>
    api.post<{ unique_id: string; already_verified: boolean }>("/participant/auth/verify-email", {
      unique_id: uniqueId,
      otp,
    }),

  resendOtp: (uniqueId: string) =>
    api.post<{ masked_email: string; otp_validity_seconds: number; is_fixed_otp?: boolean }>("/participant/auth/resend-otp", {
      unique_id: uniqueId,
    }),

  registrationState: (uniqueId: string) =>
    api.post<RegistrationState>("/participant/auth/registration-state", { unique_id: uniqueId }),

  // ------------------------------------------------------------ auth
  login: (emailId: string, password: string) =>
    api.post<ParticipantSession>("/participant/auth/login", { email_id: emailId, password }),

  logout: () => api.post<null>("/participant/auth/logout", undefined, OPTIONS),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<null>(
      "/participant/auth/change-password",
      { old_password: oldPassword, new_password: newPassword },
      OPTIONS,
    ),

  /** `is_fixed_otp`: no mail on this server, so the reset uses the fixed code (000000). */
  forgotPassword: (emailId: string) =>
    api.post<{ is_fixed_otp?: boolean } | null>("/participant/auth/forgot-password", { email_id: emailId }),

  resetPassword: (token: string, newPassword: string) =>
    api.post<null>("/participant/auth/reset-password", { token, new_password: newPassword }),

  /** Development reset while mail is off: email + the fixed code instead of the emailed link. */
  resetPasswordWithCode: (emailId: string, otp: string, newPassword: string) =>
    api.post<null>("/participant/auth/reset-password", {
      email_id: emailId,
      otp,
      new_password: newPassword,
    }),

  // ---------------------------------------------------------- portal
  profile: () => api.get<Participant>("/participant/profile", OPTIONS),

  updateProfile: (formData: FormData) => {
    // The endpoint accepts multipart so the optional ID proof can ride along.
    return api.upload<Participant>("/participant/profile", formData, OPTIONS, "PUT");
  },

  profileCompleteness: () =>
    api.get<{ is_complete: boolean; missing_fields: string[] }>(
      "/participant/profile/completeness",
      OPTIONS,
    ),

  dashboard: () =>
    api.get<{
      api_calls_today: number;
      api_calls_month: number;
      api_calls_period: number;
      usage_trend: Array<{ label: string; value: number }>;
      top_endpoints: Array<{ label: string; value: number }>;
      environments: string[];
      is_profile_complete: boolean;
    }>("/participant/dashboard", OPTIONS),

  requestPromotion: (formData: FormData) =>
    api.upload<{ request_id: number; status: number }>(
      "/participant/promotion-requests",
      formData,
      OPTIONS,
    ),

  promotionRequests: () => api.get<PromotionRequest[]>("/participant/promotion-requests", OPTIONS),

  createQuery: (subject: string, description: string, queryType?: number) =>
    api.post<SupportQuery>(
      "/participant/queries",
      { subject, description, query_type: queryType },
      OPTIONS,
    ),

  listQueries: () => api.get<SupportQuery[]>("/participant/queries", OPTIONS),

  apiHistoryDetail: (logId: number) =>
    api.get<ApiLogDetail>(`/participant/api-history/${logId}`, OPTIONS),

  apiHistory: async (query: ListQuery) => {
    const page = await api.post<{ logs: ApiLog[]; pagination: Pagination }>(
      "/participant/api-history",
      query,
      OPTIONS,
    );
    return page;
  },
};

/** Unauthenticated content the marketing pages and registration form need. */
export const publicApi = {
  home: () => api.get<PublicHome>("/home"),
  faqs: () => api.get<FaqGroup[]>("/faqs"),
  terms: () => api.get<TermSection[]>("/terms"),
  countries: (onlyLive = false) => api.get<Country[]>("/countries", { query: { only_live: onlyLive } }),
  masters: (kind: string, parentId?: number) =>
    api.get<DropdownItem[]>(`/masters/${kind}`, { query: { parent_id: parentId } }),
  areas: (level: number, parentId?: number) =>
    api.get<DropdownItem[]>("/geography/areas", { query: { level, parent_id: parentId } }),
};
