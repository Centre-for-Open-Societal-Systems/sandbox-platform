/**
 * Sanitise administrator-authored rich text before it is rendered as HTML.
 *
 * Terms sections and product "key features" are stored as HTML and rendered
 * with `dangerouslySetInnerHTML`. DOMPurify strips scripts, event handlers,
 * `javascript:` URLs and other active content, keeping ordinary formatting.
 * The isomorphic build works in server components (jsdom) and in the browser.
 */

import DOMPurify from "isomorphic-dompurify";

/** HTML safe to pass to `dangerouslySetInnerHTML`; empty for null/undefined. */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) {
    return "";
  }
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select"],
  });
}
