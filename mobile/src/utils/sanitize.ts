/**
 * Shared sanitization utilities.
 *
 * COSAT MongoDB documents sometimes embed email addresses inside venue/location
 * fields (e.g. "Buenos Aires, contacto@club.com"). These helpers strip or
 * detect such values before displaying them to the user.
 */

const EMAIL_RE = /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/;

/**
 * Returns true when the string contains something that looks like an email
 * address. Use to skip displaying a venue field that has been contaminated.
 */
export function hasEmailLike(text: string | null | undefined): boolean {
  if (!text) return false;
  return EMAIL_RE.test(text);
}

/**
 * Returns the original text with any email-like substrings removed and
 * surrounding whitespace trimmed. Use for fields that may contain partial
 * email contamination alongside valid content.
 */
export function stripEmailLike(text: string): string {
  return text.replace(EMAIL_RE, '').trim();
}
