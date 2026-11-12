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

/** A fresh admin invitation: the set-password link (valid 24 h, once; a newer one replaces it). */
export interface AdminInvite {
  invite_url: string;
  /** The invitation was also emailed (mail is on). */
  emailed: boolean;
}

export interface AdminUserCreated extends AdminUser {
  /** Set when the user was invited instead of given a password. */
  invitation: AdminInvite | null;
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

export interface DashboardApiHealth {
  total_calls: number;
  success: number;
  client_errors: number;
  /** 5xx responses plus calls that got no response. */
  server_errors: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
}

export interface DashboardEndpointStat {
  method: string | null;
  endpoint_url: string;
  product_name: string | null;
  calls: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
}

export type DashboardPeriod = "today" | "week" | "month";

export interface AdminDashboard {
  counters: DashboardCounters;
  period: DashboardPeriod;
  registrations_trend: SeriesPoint[];
  api_usage_trend: SeriesPoint[];
  api_health: DashboardApiHealth;
  top_endpoints: DashboardEndpointStat[];
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

/** The signing key read from a production request (certificate or pasted public key). */
export interface PartnerKeyInfo {
  algorithm: string;
  fingerprint_sha256: string;
  source: "certificate" | "public_key";
  certificate: {
    subject: string;
    common_name: string | null;
    issuer: string;
    serial_number: string;
    not_before: string;
    not_after: string;
    self_signed: boolean;
  } | null;
}

export interface PromotionDetails {
  public_key?: string;
  /** Read by the server from the certificate / public key. */
  key?: PartnerKeyInfo;
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
  /** When an answer is due (SUPPORT_SLA_HOURS after it was raised); null without an SLA. */
  due_date?: string | null;
  /** Still open or in progress past its due date. */
  is_overdue?: boolean;
  /** Console list only: who raised the query. */
  participant_name?: string | null;
  email_id?: string | null;
  company_name?: string | null;
  /** Reference quoted by the participant and in mails, e.g. TKT-000123. */
  ticket_no?: string;
  /** When the participant last wrote and no one has answered yet (the SLA clock). */
  awaiting_since?: string | null;
  last_message_date?: string | null;
  /** Who wrote last: participant or admin. */
  last_message_by?: "participant" | "admin" | null;
  closed_date?: string | null;
  message_count?: number;
  /** The other side wrote after you last opened the ticket. */
  unread?: boolean;
}

export interface SupportMessage {
  message_id: number;
  /** participant, admin, or system (a status event). */
  author_type: "participant" | "admin" | "system";
  author_name: string | null;
  body: string;
  /** Staff-only note (console only). */
  is_internal: boolean;
  channel: string;
  /** When the mail for this message went out; null = no mail. */
  notified_date: string | null;
  added_date: string | null;
}

/** A ticket with its conversation, oldest message first. */
export interface SupportThread extends SupportQuery {
  messages: SupportMessage[];
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

/** GET /admin/gateway/status: whether "Pull from gateway" is offered. */
export interface GatewayStatus {
  enabled: boolean;
  gateway_type: "apisix" | "kong";
  admin_url_configured: boolean;
  /** Gateways the console can pull from: UAT, plus PRODUCTION when it has its own. */
  environments?: ("UAT" | "PRODUCTION")[];
}

export interface GatewaySyncRow {
  endpoint_id?: number;
  product_id: number | null;
  product_name: string;
  method: string;
  path: string | null;
  changes?: string[];
}

/** POST /admin/gateway/sync. Lists are capped; the *_count fields are complete. */
export interface GatewaySyncReport {
  gateway_type: "apisix" | "kong";
  /** Which gateway was read. */
  environment?: "UAT" | "PRODUCTION";
  dry_run: boolean;
  services: number;
  routes: number;
  operations: number;
  products_created: { product_id: number | null; product_name: string }[];
  created: GatewaySyncRow[];
  updated: GatewaySyncRow[];
  unchanged: number;
  skipped: { route: string; path: string; reason: string }[];
  missing: GatewaySyncRow[];
  created_count: number;
  updated_count: number;
  skipped_count: number;
  missing_count: number;
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
/** TRYIT: made from the portal's try-it console; DIRECT: called on the gateway with an app key. */
export type ApiCallSource = "TRYIT" | "DIRECT";

export interface ApiLog {
  id: number;
  correlation_id: string | null;
  transaction_id: string | null;
  source: ApiCallSource;
  app_id: number | null;
  app_name: string | null;
  participant_id: number | null;
  participant_name: string | null;
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
  upstream_latency_ms: number | null;
  request_size: number | null;
  response_size: number | null;
  response_time: string | null;
  request_headers: Record<string, unknown> | null;
  request_body: unknown;
  response_body: unknown;
}

export type ApiUsageGroup =
  | "participant"
  | "participant_endpoint"
  | "endpoint"
  | "app"
  | "product"
  | "day"
  | "status";

/** One row of the usage / billing report: calls counted for one group. */
export interface ApiUsageRow {
  participant_id: number | null;
  participant_name: string | null;
  email_id: string | null;
  country_code: string | null;
  app_id: number | null;
  app_name: string | null;
  product_id: number | null;
  product_name: string | null;
  method: string | null;
  endpoint_url: string | null;
  day: string | null;
  status_code: number | null;
  endpoints_used: number | null;
  apps_used: number | null;
  total_calls: number;
  success_calls: number;
  client_errors: number;
  server_errors: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
  first_call: string | null;
  last_call: string | null;
}

export interface ApiUsageCount {
  label: string;
  value: number;
}

export interface ApiUsageSummary {
  total_calls: number;
  success_calls: number;
  client_errors: number;
  server_errors: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
  partners: number;
  apps: number;
  endpoints: number;
  first_call: string | null;
  last_call: string | null;
  by_status_code: ApiUsageCount[];
  by_source: ApiUsageCount[];
  by_day: ApiUsageCount[];
}

export interface ApiUsageOptions {
  products: { product_id: number; name: string }[];
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

// ------------------------------------------------------ API products & apps
export type ApprovalType = "AUTO" | "MANUAL";

/** One catalogue endpoint inside an API product. */
export interface ApiProductEndpoint {
  endpoint_id: number;
  product_id: number;
  product_name: string | null;
  display_name: string | null;
  method: string | null;
  endpoint_url: string | null;
}

export interface ApiProduct {
  api_product_id: number;
  unique_id: string;
  name: string;
  display_name: string;
  description: string | null;
  approval_type: ApprovalType;
  is_published: boolean;
  is_enabled: boolean;
  country_code: string | null;
  sort_order: number;
  /** Gateway limits for apps with this product; null = no limit. */
  rate_limit_per_minute: number | null;
  quota_per_day: number | null;
  endpoint_count: number;
  app_count: number;
  added_date: string | null;
  modify_date: string | null;
}

export interface ApiProductDetail extends ApiProduct {
  endpoints: ApiProductEndpoint[];
}

export interface ApiProductPayload {
  name: string;
  display_name: string;
  description: string | null;
  approval_type: ApprovalType;
  is_published: boolean;
  sort_order: number;
  endpoint_ids: number[];
  rate_limit_per_minute: number | null;
  quota_per_day: number | null;
}

/** Picker data: catalogue endpoints grouped by catalogue product. */
export interface EndpointOptionGroup {
  product_id: number;
  product_name: string;
  is_gateway_published: boolean;
  endpoints: {
    endpoint_id: number;
    display_name: string | null;
    method: string | null;
    endpoint_url: string | null;
    is_published: boolean;
    is_gateway_published: boolean;
  }[];
}

/** An API product as a participant sees it when creating an app. */
export interface AvailableApiProduct {
  api_product_id: number;
  name: string;
  display_name: string;
  description: string | null;
  approval_type: ApprovalType;
  rate_limit_per_minute: number | null;
  quota_per_day: number | null;
  endpoints: ApiProductEndpoint[];
}

export interface AppSubscription {
  api_product_id: number;
  name: string;
  display_name: string;
  rate_limit_per_minute: number | null;
  quota_per_day: number | null;
  /** 0 pending, 1 approved, 2 rejected, 3 revoked. */
  status: number;
  status_label: string;
  remarks: string | null;
  requested_date: string | null;
  decided_date: string | null;
  /** The APIs this product lets the app call. */
  endpoints: ApiProductEndpoint[];
}

export interface AppCredential {
  credential_id: string;
  /** Full key for the app's owner; null for administrators and revoked keys. */
  api_key: string | null;
  /** The secret is in clear only when a key is issued, rotated or revealed (once); null in lists. */
  api_secret: string | null;
  api_key_prefix: string;
  api_secret_hint: string;
  /** 1 active, 2 revoked, 3 expired. */
  status: number;
  status_label: string;
  issued_date: string | null;
  revoked_date: string | null;
  last_used_date: string | null;
  /** The key stops working then (null = never). */
  expires_date: string | null;
  /** The secret was already shown; rotate the key to get a new one. */
  secret_viewed: boolean;
}

/** Returned when the owner issues a new key: key and secret in clear. */
export interface IssuedCredential extends AppCredential {
  api_key: string;
  api_secret: string;
}

/** How the gateway identifies a caller (GATEWAY_PARTNER_AUTH), for the try-it page. */
export interface GatewayAuth {
  mode: "apikey" | "keycloak" | "oauth";
  app_key_header: string;
  token_header: string;
  /** OAuth: where an app gets its token (client credentials). */
  token_url: string | null;
  grant_type: string | null;
}

/** An app's access token: client credentials with its API key + secret ("Get token"). */
export interface AppToken {
  token_url: string;
  grant_type: string;
  client_id: string;
  header: string;
  access_token: string;
  token_type: string;
  expires_in: number;
  expires_at: string | null;
  claims: Record<string, unknown>;
}

export type GatewaySyncStatus = "PENDING" | "SYNCED" | "FAILED" | "DISABLED";

export interface ParticipantApp {
  app_id: string;
  name: string;
  description: string | null;
  environment: string;
  /** 0 awaiting approval (no key yet), 1 active, 2 revoked, 3 rejected by an administrator. */
  status: number;
  status_label: string;
  /** Why the administrator revoked or rejected the app. */
  revoked_reason: string | null;
  /** IP whitelist (IPs / CIDRs); empty = any address. */
  allowed_ips: string[];
  /** Limits the gateway applies (null = none, or limits switched off). */
  rate_limit_per_minute: number | null;
  quota_per_day: number | null;
  /** Calls logged in the last minute / 24 hours when that limit is set (approximate). */
  calls_last_minute: number | null;
  calls_today: number | null;
  gateway_consumer: string | null;
  gateway_status: GatewaySyncStatus;
  gateway_error: string | null;
  gateway_synced_at: string | null;
  gateway_warnings: string[];
  products: AppSubscription[];
  credentials: AppCredential[];
  added_date: string | null;
  modify_date: string | null;
}

export interface AdminApp extends ParticipantApp {
  id: number;
  participant_id: number;
  participant_name: string | null;
  participant_email: string | null;
  company_name: string | null;
  gateway_routes: string[];
}

/** A new app waits for an administrator, so it has no credential yet. */
export interface AppCreated {
  app: ParticipantApp;
  credential: IssuedCredential | null;
}

/** The try-it form sent with a code-sample request. */
export interface CodeSampleForm {
  path_params: Record<string, string>;
  query_params: Record<string, string>;
  headers: Record<string, string>;
  has_body: boolean;
  body: unknown;
  /** Show the call as this app: its API key goes in the `apikey` header. */
  app_id: string | null;
}

/** A participant's user in Keycloak (API login): one per participant, roles = approved environments. */
export interface IamAccount {
  realm: string;
  /** Keycloak username: the participant's email address. */
  username: string;
  /** Shared client tokens are requested from. */
  client_id: string;
  token_url: string;
  grant_type: "password";
  /** Environment roles held: sandbox, uat, production. */
  roles: string[];
  status: "ACTIVE" | "DISABLED" | "FAILED";
  /** Keycloak has the current portal password. */
  password_synced: boolean;
  added_date: string | null;
  synced_at: string | null;
  error?: string | null;
  keycloak_id?: string | null;
  /** Console only: the user's page in the Keycloak admin console. */
  console_url?: string | null;
  /** Consent Manager partner portal and Partner Management; null when not configured. */
  partner_portal?: PartnerPortalAccount | null;
}

/** What the sandbox set up for the OpenG2P Consent Manager partner portal. */
export interface PartnerPortalAccount {
  /** Keycloak attribute / CM claim partner_id, e.g. oan-p-42. */
  partner_id: string | null;
  /** The CM partner portal client; null when the portal is not configured. */
  client_id: string | null;
  role: string;
  /** The user holds the portal client role. */
  portal_access: boolean;
  /** Partner Management provisioning is switched on. */
  pm_enabled: boolean;
  /** The partner in Partner Management, e.g. PARTNER_OAN_P_42. */
  pm_partner_id: string | null;
  pm_status: "ACTIVE" | "DISABLED" | "FAILED" | null;
  pm_error?: string | null;
  pm_synced_at?: string | null;
}

export interface IamAccountState {
  /** Keycloak provisioning is switched on for this deployment. */
  enabled: boolean;
  account: IamAccount | null;
}

/** An email template in the console (CMS). */
export interface EmailTemplate {
  template_id: number;
  template_code: string;
  template_name: string;
  subject: string | null;
  body_text: string | null;
  variables: string[] | null;
  locale: string;
  is_enabled: boolean;
  modify_date: string | null;
}

/** A template rendered with sample values, for the console preview. */
export interface EmailTemplatePreview {
  subject: string;
  body_html: string;
  placeholders: string[];
}
