/** Master data and geography administration. */

import { api } from "@/lib/api-client";
import type {
  AdminArea,
  Country,
  Faq,
  FaqGroup,
  HomeBlock,
  LookupEntry,
  ListQuery,
  Pagination,
  TermSection,
} from "@/types/api";

const OPTIONS = { audience: "admin" as const };

interface PagedRows<T> {
  pagination: Pagination;
  [key: string]: T[] | Pagination;
}

function rows<T>(page: PagedRows<T>, key: string): T[] {
  return (page[key] as T[]) ?? [];
}

/** Lookup tables the generic master endpoints serve, keyed by URL segment. */
export const LOOKUP_KINDS = [
  { kind: "participant-type", label: "Participant Type" },
  { kind: "service-domain", label: "Service Domain" },
  { kind: "operating-area", label: "Operating Area" },
  { kind: "category", label: "Business Category" },
  { kind: "sub-category", label: "Sub-category" },
] as const;

export const mastersApi = {
  listLookup: (kind: string, params?: { country_code?: string; parent_id?: number; search?: string }) =>
    api.get<LookupEntry[]>(`/admin/lookups/${kind}`, { ...OPTIONS, query: params }),

  createLookup: (kind: string, payload: Record<string, unknown>) =>
    api.post<LookupEntry>(`/admin/lookups/${kind}`, payload, OPTIONS),

  updateLookup: (kind: string, payload: Record<string, unknown>) =>
    api.put<LookupEntry>(`/admin/lookups/${kind}`, payload, OPTIONS),

  toggleLookup: (kind: string, id: number, isEnabled?: boolean) =>
    api.post<LookupEntry>(`/admin/lookups/${kind}/toggle`, { id, is_enabled: isEnabled }, OPTIONS),

  deleteLookup: (kind: string, id: number) =>
    api.delete<null>(`/admin/lookups/${kind}/${id}`, OPTIONS),

  // ------------------------------------------------------- countries
  listCountries: () => api.get<Country[]>("/admin/countries", OPTIONS),

  getCountry: (countryCode: string) => api.get<Country>(`/admin/countries/${countryCode}`, OPTIONS),

  createCountry: (payload: Record<string, unknown>) =>
    api.post<Country>("/admin/countries", payload, OPTIONS),

  updateCountry: (countryCode: string, payload: Record<string, unknown>) =>
    api.put<Country>(`/admin/countries/${countryCode}`, payload, OPTIONS),

  // ------------------------------------------------------- geography
  listAreas: (payload: Record<string, unknown>) =>
    api.post<AdminArea[]>("/admin/areas/list", payload, OPTIONS),

  areaTree: (countryCode: string, maxLevel = 2) =>
    api.get<AdminArea[]>("/admin/areas/tree", {
      ...OPTIONS,
      query: { country_code: countryCode, max_level: maxLevel },
    }),

  createArea: (payload: Record<string, unknown>) =>
    api.post<AdminArea>("/admin/areas", payload, OPTIONS),

  updateArea: (payload: Record<string, unknown>) =>
    api.put<AdminArea>("/admin/areas", payload, OPTIONS),

  toggleArea: (id: number, isEnabled?: boolean) =>
    api.post<AdminArea>("/admin/areas/toggle", { id, is_enabled: isEnabled }, OPTIONS),

  toggleAreaApiData: (areaId: number, enabled: boolean) =>
    api.post<AdminArea>(`/admin/areas/${areaId}/api-data`, undefined, {
      ...OPTIONS,
      query: { enabled },
    }),
};

export const contentApi = {
  listFaqTypes: async (query: ListQuery) => {
    const page = await api.post<PagedRows<FaqGroup>>("/admin/faq-types/list", query, OPTIONS);
    return { types: rows<FaqGroup>(page, "types"), pagination: page.pagination };
  },

  faqTypeDropdown: () =>
    api.get<Array<{ label: string; value: number }>>("/admin/faq-types/dropdown", OPTIONS),

  createFaqType: (payload: Record<string, unknown>) =>
    api.post<FaqGroup>("/admin/faq-types", payload, OPTIONS),

  updateFaqType: (payload: Record<string, unknown>) =>
    api.put<FaqGroup>("/admin/faq-types", payload, OPTIONS),

  deleteFaqType: (typeId: number) => api.delete<null>(`/admin/faq-types/${typeId}`, OPTIONS),

  listFaqs: async (query: ListQuery, typeId?: number) => {
    const page = await api.post<PagedRows<Faq>>("/admin/faqs/list", query, {
      ...OPTIONS,
      query: { type_id: typeId },
    });
    return { faqs: rows<Faq>(page, "faqs"), pagination: page.pagination };
  },

  createFaq: (payload: Record<string, unknown>) => api.post<Faq>("/admin/faqs", payload, OPTIONS),

  updateFaq: (payload: Record<string, unknown>) => api.put<Faq>("/admin/faqs", payload, OPTIONS),

  toggleFaq: (id: number, isEnabled?: boolean) =>
    api.post<Faq>("/admin/faqs/toggle", { id, is_enabled: isEnabled }, OPTIONS),

  deleteFaq: (faqId: number) => api.delete<null>(`/admin/faqs/${faqId}`, OPTIONS),

  listTerms: async (query: ListQuery) => {
    const page = await api.post<PagedRows<TermSection>>("/admin/terms/list", query, OPTIONS);
    return { terms: rows<TermSection>(page, "terms"), pagination: page.pagination };
  },

  createTerm: (payload: Record<string, unknown>) =>
    api.post<TermSection>("/admin/terms", payload, OPTIONS),

  updateTerm: (payload: Record<string, unknown>) =>
    api.put<TermSection>("/admin/terms", payload, OPTIONS),

  deleteTerm: (tableId: number) => api.delete<null>(`/admin/terms/${tableId}`, OPTIONS),

  listEmailTemplates: async (query: ListQuery) => {
    const page = await api.post<PagedRows<Record<string, unknown>>>(
      "/admin/email-templates/list",
      query,
      OPTIONS,
    );
    return {
      templates: rows<Record<string, unknown>>(page, "templates"),
      pagination: page.pagination,
    };
  },

  saveEmailTemplate: (payload: Record<string, unknown>) =>
    api.post<Record<string, unknown>>("/admin/email-templates", payload, OPTIONS),

  sendTestMail: (payload: Record<string, unknown>) =>
    api.post<{ sent: boolean }>("/admin/email-templates/test", payload, OPTIONS),

  listHomeBlocks: (locale = "en") =>
    api.get<HomeBlock[]>("/admin/home-blocks", { ...OPTIONS, query: { locale } }),
};
