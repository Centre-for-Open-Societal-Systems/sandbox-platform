/** API catalogue calls, for both the console and the portal. */

import { api } from "@/lib/api-client";
import type {
  CatalogMenuProduct,
  Endpoint,
  EndpointDetail,
  EndpointSample,
  EndpointSchema,
  ListQuery,
  Pagination,
  Product,
  ProductCategory,
  ProductDetail,
  TryItResult,
} from "@/types/api";

const ADMIN = { audience: "admin" as const };
const PORTAL = { audience: "participant" as const };

interface PagedRows<T> {
  pagination: Pagination;
  [key: string]: T[] | Pagination;
}

function rows<T>(page: PagedRows<T>, key: string): T[] {
  return (page[key] as T[]) ?? [];
}

export const catalogApi = {
  // ----------------------------------------------------------- console
  listProducts: async (query: ListQuery) => {
    const page = await api.post<PagedRows<Product>>("/admin/products/list", query, ADMIN);
    return { products: rows<Product>(page, "products"), pagination: page.pagination };
  },

  listProductCategories: async () => {
    const page = await api.post<PagedRows<ProductCategory>>(
      "/admin/product-categories/list",
      { page: 1, limit: 200, sort_by: "sort_order", sort_dir: "asc" },
      ADMIN,
    );
    return rows<ProductCategory>(page, "categories");
  },

  getProduct: (productId: number) => api.get<ProductDetail>(`/admin/products/${productId}`, ADMIN),

  createProduct: (payload: Record<string, unknown>) =>
    api.post<Product>("/admin/products", payload, ADMIN),

  updateProduct: (payload: Record<string, unknown>) =>
    api.put<Product>("/admin/products", payload, ADMIN),

  publishProduct: (id: number, isPublished: boolean) =>
    api.post<Product>("/admin/products/publish", { id, is_published: isPublished }, ADMIN),

  deleteProduct: (productId: number) => api.delete<null>(`/admin/products/${productId}`, ADMIN),

  uploadProductAssets: (productId: number, files: FormData) =>
    api.upload<Product>(`/admin/products/${productId}/assets`, files, ADMIN),

  importSpec: (productId: number, specText: string, replaceExisting = false) =>
    api.post<{ created: number; updated: number; total: number }>(
      "/admin/products/import-spec",
      { product_id: productId, spec_text: specText, replace_existing: replaceExisting },
      ADMIN,
    ),

  listEndpoints: async (query: ListQuery) => {
    const page = await api.post<PagedRows<Endpoint>>("/admin/endpoints/list", query, ADMIN);
    return { endpoints: rows<Endpoint>(page, "endpoints"), pagination: page.pagination };
  },

  getEndpoint: (endpointId: number) =>
    api.get<EndpointDetail>(`/admin/endpoints/${endpointId}`, ADMIN),

  createEndpoint: (payload: Record<string, unknown>) =>
    api.post<Endpoint>("/admin/endpoints", payload, ADMIN),

  updateEndpoint: (payload: Record<string, unknown>) =>
    api.put<Endpoint>("/admin/endpoints", payload, ADMIN),

  publishEndpoint: (id: number, isPublished: boolean) =>
    api.post<Endpoint>("/admin/endpoints/publish", { id, is_published: isPublished }, ADMIN),

  deleteEndpoint: (endpointId: number) => api.delete<null>(`/admin/endpoints/${endpointId}`, ADMIN),

  listSchemas: (endpointId: number) =>
    api.get<EndpointSchema[]>(`/admin/endpoints/${endpointId}/schemas`, ADMIN),

  createSchema: (payload: Record<string, unknown>) =>
    api.post<EndpointSchema>("/admin/schemas", payload, ADMIN),

  updateSchema: (payload: Record<string, unknown>) =>
    api.put<EndpointSchema>("/admin/schemas", payload, ADMIN),

  deleteSchema: (schemaId: number) => api.delete<null>(`/admin/schemas/${schemaId}`, ADMIN),

  generateSchema: (sample: unknown) =>
    api.post<Record<string, unknown>>("/admin/schemas/generate", { sample }, ADMIN),

  // --------------------------------------------------------- public
  publicProducts: () => api.get<Product[]>("/catalog/products"),

  publicProduct: (productId: number) => api.get<ProductDetail>(`/catalog/products/${productId}`),

  // ------------------------------------------------------------ portal
  portalProducts: () => api.get<Product[]>("/participant/catalog/products", PORTAL),

  /** Every published product with its end-points in one call (ETag-revalidated). */
  portalMenu: () =>
    api.get<CatalogMenuProduct[]>("/participant/catalog/menu", { ...PORTAL, cache: "no-cache" }),

  portalProduct: (productId: number) =>
    api.get<ProductDetail>(`/participant/catalog/products/${productId}`, PORTAL),

  portalEndpoint: (endpointId: number) =>
    api.get<EndpointDetail>(`/participant/catalog/endpoints/${endpointId}`, PORTAL),

  endpointSample: (endpointId: number, statusCode = "200") =>
    api.get<EndpointSample>(`/participant/catalog/endpoints/${endpointId}/sample`, {
      ...PORTAL,
      query: { status_code: statusCode },
    }),

  tryIt: (payload: Record<string, unknown>) =>
    api.post<TryItResult>("/participant/try-it", payload, PORTAL),

  codeSample: (endpointId: number, language: string, environment: string) =>
    api.post<{ language: string; code: string }>(
      "/participant/code-sample",
      { endpoint_id: endpointId, language, environment },
      PORTAL,
    ),

  convertCurl: (curlCommand: string) =>
    api.post<{
      method: string;
      url: string;
      path: string;
      headers: Record<string, string>;
      query_params: Record<string, string>;
      body: unknown;
    }>("/participant/curl-convert", { curl_command: curlCommand }, PORTAL),
};
