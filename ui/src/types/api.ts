/** Shapes returned by the OAN sandbox API. */

export interface Envelope<T> {
  message: string;
  status: boolean;
  code: number;
  data: T;
}

export interface Pagination {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
}

export interface Paged<T> {
  pagination: Pagination;
  [rows: string]: T[] | Pagination;
}

export interface ListQuery {
  page?: number;
  limit?: number;
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  [key: string]: unknown;
}

export interface DropdownItem {
  label: string;
  value: number | string;
  extra?: Record<string, unknown>;
}

export interface PermissionFlag {
  id: number;
  status: boolean;
}

export interface PermissionNode {
  permission_id: number;
  menu_name: string | null;
  parent_id: number | null;
  has_submenu: boolean;
  is_allowed: boolean;
  children: PermissionNode[];
}

// ------------------------------------------------------------------ admin
export interface AdminSession {
  first_name: string | null;
  last_name: string | null;
  email_id: string | null;
  mobile_no: string | null;
  is_master: boolean;
  role: string;
  country_code: string | null;
  admin_area_code: string | null;
  access_token: string;
  refresh_token: string;
  token_expiry: number;
  token_issued_at: string;
  auth_key: string;
  permissions: PermissionFlag[];
}

export interface AdminUser {
  admin_id: number;
  unique_id: string;
  first_name: string | null;
  last_name: string | null;
  email_id: string | null;
  mobile_no: string | null;
  login_name: string;
  role_id: number | null;
  role_name: string | null;
  is_master: boolean;
  is_enabled: boolean;
  is_activated: boolean;
  country_code: string | null;
  admin_area_code: string | null;
  description: string | null;
  added_date: string | null;
}

export interface Role {
  role_id: number;
  unique_id: string;
  role_name: string;
  role_level: number | null;
  checker_maker: number;
  is_editable: boolean;
  is_enabled: boolean;
  added_date: string | null;
  permission_ids: number[];
  user_count: number;
}

export interface DashboardCounters {
  total_participants: number;
  /** Signed up but never entered the emailed verification code. */
  unverified_participants: number;
  sandbox_participants: number;
  uat_pending: number;
  uat_participants: number;
  prod_pending: number;
  prod_participants: number;
  rejected_participants: number;
  total_products: number;
  published_products: number;
  total_endpoints: number;
  api_calls_today: number;
  api_calls_month: number;
  open_queries: number;
}

export interface SeriesPoint {
  label: string;
  value: number;
}

export interface AdminDashboard {
  counters: DashboardCounters;
  registrations_trend: SeriesPoint[];
  api_usage_trend: SeriesPoint[];
  participants_by_area: SeriesPoint[];
  top_endpoints: SeriesPoint[];
}

// ------------------------------------------------------------------- user
export interface ParticipantSession {
  participant_id: number;
  unique_id: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  email_id: string | null;
  country_code: string;
  environments: string[];
  is_profile_complete: boolean;
  is_uat_requested: boolean;
  is_prod_requested: boolean;
  access_token: string;
  refresh_token: string;
  token_expiry: number;
  token_issued_at: string;
  auth_key: string;
}

export interface Participant {
  participant_id: number;
  unique_id: string;
  first_name: string | null;
  last_name: string | null;
  display_name: string;
  company_name: string | null;
  email_id: string | null;
  mobile_number: string | null;
  profile_type: string | null;
  organization_registration_number: string | null;
  website: string | null;
  country_code: string;
  admin_area_code_l1: string | null;
  admin_area_code_l2: string | null;
  category_id: number | null;
  sub_category_id: number | null;
  participant_type_id: number | null;
  service_domain: string | null;
  operating_area: string | null;
  description: string | null;
  authorized_person_name: string | null;
  authorized_person_designation: string | null;
  authorized_person_address: string | null;
  is_email_verified: boolean;
  is_profile_complete: boolean;
  is_approved: number;
  is_activated: number;
  is_rejected: boolean;
  rejection_reason: string | null;
  is_sandbox_approved: boolean;
  is_uat_requested: boolean;
  is_uat_approved: boolean;
  is_uat_rejected: boolean;
  is_prod_requested: boolean;
  is_prod_approved: boolean;
  is_prod_rejected: boolean;
  is_enabled: boolean;
  register_date: string | null;
  approved_date: string | null;
  uat_approved_date: string | null;
  prod_approved_date: string | null;
}

export interface PromotionRequest {
  request_id: number;
  participant_id: number;
  target_environment: string;
  status: number;
  remarks: string | null;
  rejection_reason: string | null;
  certificate_path: string | null;
  document_path: string | null;
  /** Move-to-production answers, when the request carried them. */
  extra_data: PromotionDetails | null;
  added_date: string | null;
  reviewed_date: string | null;
}

export interface PromotionDetails {
  public_key?: string;
  endpoint_ids?: number[];
  daily_volume?: number;
  integration_contact?: string;
  escalation_contact?: string;
}

/** Console participant detail: the profile plus documents and access requests. */
export interface AdminParticipantDetail extends Participant {
  id_proof: string | null;
  requests: PromotionRequest[];
}

export interface SupportQuery {
  query_id: number;
  participant_id: number | null;
  query_type: number | null;
  subject: string | null;
  description: string | null;
  status: number;
  response: string | null;
  added_date: string | null;
  responded_date: string | null;
  /** Console list only: who raised the query. */
  participant_name?: string | null;
  email_id?: string | null;
  company_name?: string | null;
}

// ---------------------------------------------------------------- catalog
export interface Product {
  product_id: number;
  unique_id: string;
  product_name: string;
  display_name: string | null;
  description: string | null;
  product_note: string | null;
  category_id: number | null;
  category_name: string | null;
  country_code: string | null;
  product_icon: string | null;
  flow_chart: string | null;
  product_documentation_pdf: string | null;
  api_doc_version: string | null;
  is_published: boolean;
  is_gateway_published: boolean;
  is_manual: boolean;
  sort_order: number;
  product_keywords: string[] | null;
  endpoint_count: number;
  added_date: string | null;
  modify_date: string | null;
}

/** One product of the portal's API menu (``GET /participant/catalog/menu``). */
export interface CatalogMenuProduct {
  product_id: number;
  product_name: string;
  display_name: string | null;
  category_name: string | null;
  endpoints: Pick<Endpoint, "endpoint_id" | "display_name" | "endpoint_url" | "method" | "api_type">[];
}

export interface ProductCategory {
  category_id: number;
  category_name: string;
  description: string | null;
  sort_order: number;
}

export interface ProductDetail extends Product {
  page_text: string | null;
  key_features: string | null;
  meta_key: string | null;
  meta_desc: string | null;
  endpoints: Endpoint[];
}

export interface Endpoint {
  endpoint_id: number;
  unique_id: string;
  product_id: number;
  product_name: string | null;
  display_name: string | null;
  description: string | null;
  endpoint_url: string | null;
  method: string | null;
  api_type: string | null;
  country_code: string | null;
  area_scoped: boolean;
  is_published: boolean;
  is_gateway_published: boolean;
  has_mapper: boolean;
  mapper_id: number | null;
  sort_order: number;
  api_keywords: string[] | null;
  added_date: string | null;
}

export interface EndpointDetail extends Endpoint {
  sandbox_api_url: string | null;
  uat_api_url: string | null;
  prod_api_url: string | null;
  /** Try-it pre-fill (portal responses only). */
  sample?: EndpointSample;
  /** Where calls really go per environment (own URL, else the API gateway); null = mock. */
  resolved_upstreams?: Record<string, string | null>;
  path_params: Record<string, unknown> | null;
  query_params: Record<string, unknown> | null;
  header_params: Record<string, unknown> | null;
  request_schema: Record<string, unknown> | null;
  request_sample: unknown;
  schemas: EndpointSchema[];
}

export interface EndpointSchema {
  schema_id: number;
  endpoint_id: number;
  status_code: string;
  header_json: Record<string, unknown> | null;
  path_params: Record<string, unknown> | null;
  req_schema: Record<string, unknown> | null;
  req_json: unknown;
  res_schema: Record<string, unknown> | null;
  res_json: unknown;
  is_enabled: boolean;
  added_date: string | null;
}

export interface EndpointSample {
  endpoint_id: number;
  method: string | null;
  path: string | null;
  path_params: Record<string, unknown>;
  query_params: Record<string, unknown>;
  headers: Record<string, string>;
  body: unknown;
  request_schema: Record<string, unknown> | null;
  response_schema: Record<string, unknown> | null;
  response_sample: unknown;
}


export interface TryItResult {
  status_code: number;
  latency_ms: number;
  headers: Record<string, string>;
  body: unknown;
  request_url: string;
  transaction_id: string;
  error: string | null;
}

// ---------------------------------------------------------------- masters
export interface LookupEntry {
  id: number;
  name: string;
  sort_order: number;
  country_code: string | null;
  parent_id: number | null;
  code: string | null;
  is_enabled: boolean;
  added_date: string | null;
}

export interface Country {
  country_id: number;
  country_code: string;
  country_code3: string | null;
  country_name: string;
  currency_code: string | null;
  dial_code: string | null;
  default_locale: string;
  supported_locales: string[] | null;
  level_labels: Record<string, string> | null;
  level_depth: number;
  is_live: boolean;
  is_enabled: boolean;
}

export interface AdminArea {
  area_id: number;
  country_code: string;
  area_code: string;
  area_name: string;
  area_name_local: string | null;
  level: number;
  level_label: string | null;
  parent_id: number | null;
  path: string | null;
  is_api_data_enabled: boolean;
  is_enabled: boolean;
  child_count: number;
}

// ---------------------------------------------------------------- content
export interface Faq {
  faq_id: number;
  type_id: number;
  faq_type: string | null;
  question: string;
  answer: string | null;
  sort_order: number;
  locale: string;
  is_enabled: boolean;
  added_date: string | null;
}

export interface FaqGroup {
  type_id: number;
  faq_type: string;
  sort_order: number;
  faqs: Faq[];
}

export interface TermSection {
  table_id: number;
  sidebar_title: string;
  term_content: string | null;
  sort_order: number;
  locale: string;
  country_code: string | null;
  is_enabled: boolean;
  modify_date: string | null;
}

export interface HomeBlock {
  block_id: number;
  block_key: string;
  title: string | null;
  subtitle: string | null;
  body: string | null;
  image_path: string | null;
  content: Record<string, unknown> | null;
  sort_order: number;
  locale: string;
  is_enabled: boolean;
}

export interface PublicHome {
  blocks: HomeBlock[];
  stats: Record<string, number>;
  featured_products: Array<{
    product_id: number;
    product_name: string;
    description: string | null;
    product_icon: string | null;
  }>;
  countries: Array<{ country_code: string; country_name: string; is_live: boolean }>;
}

// ------------------------------------------------------------------- logs
export interface ApiLog {
  id: number;
  correlation_id: string | null;
  transaction_id: string | null;
  participant_id: number | null;
  product_id: number | null;
  endpoint_id: number | null;
  environment: string | null;
  method: string | null;
  endpoint_url: string | null;
  target_url: string | null;
  status_code: number | null;
  error_message: string | null;
  latency_ms: number | null;
  client_ip: string | null;
  request_time: string | null;
  log_timestamp: string | null;
}

export interface ApiLogDetail extends ApiLog {
  entity_id: string | null;
  response_time: string | null;
  request_headers: Record<string, unknown> | null;
  request_body: unknown;
  response_body: unknown;
}

export interface UserActionLog {
  id: number;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  entity: string | null;
  entity_id: string | null;
  description: string | null;
  ip_address: string | null;
  correlation_id: string | null;
  changes: Record<string, unknown> | null;
  timestamp: string | null;
}
