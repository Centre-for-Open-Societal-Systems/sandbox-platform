/** Password strength rules; the backend enforces the same set (`validate_password_strength`). */
export const PASSWORD_RULES: Array<{ label: string; test: (value: string) => boolean }> = [
  { label: "8+ characters", test: (value) => value.length >= 8 },
  { label: "Upper & lower case", test: (value) => /[a-z]/.test(value) && /[A-Z]/.test(value) },
  { label: "A number", test: (value) => /\d/.test(value) },
  { label: "A symbol", test: (value) => /[^A-Za-z0-9]/.test(value) },
];

export function isStrongPassword(value: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(value));
}
