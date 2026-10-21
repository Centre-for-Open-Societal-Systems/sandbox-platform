/**
 * Console screen permissions.
 *
 * Ids mirror `app/core/permissions.py` on the backend. They are append-only:
 * renumbering one silently repoints existing role grants. Names may change
 * (they did when "participant" became "user"); the numbers must not.
 */

export const Permission = {
  ADMIN_USER_MANAGEMENT: 1,
  AUM_VIEW_USER_LIST: 2,
  AUM_ADD_NEW_USER: 3,
  AUM_MANAGE_ROLES: 4,
  API_CATALOGUE: 5,
  PARTICIPANT_MANAGEMENT: 6,
  ALL_PARTICIPANTS: 7,
  UAT_PARTICIPANTS: 8,
  UAT_APPROVAL_PENDING: 9,
  UAT_REJECTED_PARTICIPANTS: 10,
  PROD_PARTICIPANTS: 11,
  PROD_APPROVAL_PENDING: 12,
  PROD_REJECTED_PARTICIPANTS: 13,
  AUDIT_LOGS: 14,
  USER_TRACKING: 15,
  API_HISTORY: 16,
  MASTER_ENTRY: 17,
  CATEGORY: 18,
  MAPPER: 19,
  MANAGE_GEOGRAPHY: 20,
  FAQ_TYPE: 21,
  USER_QUERIES: 22,
  CMS: 23,
  FAQS: 24,
  TERMS_AND_CONDITIONS: 25,
  EMAIL_TEMPLATE: 26,
  COUNTRY_MANAGEMENT: 27,
  NETWORK_PARTICIPANTS: 28,
} as const;

export type PermissionId = (typeof Permission)[keyof typeof Permission];
