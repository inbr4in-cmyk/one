/** Kazakhstan phone helpers: the UI always shows +7 XXX XXX XX XX and sends +7XXXXXXXXXX. */

export const PHONE_DIGITS = 10

/**
 * National digits (without the country code) from the field's text.
 * `whole` = the text is a complete number from outside (paste, autofill, initial value), so a
 * leading 7/8 country or trunk prefix on an 11-digit number is dropped. While typing, extra digits
 * at the end are simply cut off.
 */
export function nationalDigits(input: string, whole = false): string {
  let s = input.trim()
  if (s.startsWith('+7')) s = s.slice(2).trim() // the field's own prefix
  if (s.startsWith('+7')) s = s.slice(2) // a full +7 number pasted after the prefix
  let d = s.replace(/\D/g, '')
  if (whole && d.length === PHONE_DIGITS + 1 && /^[78]/.test(d)) d = d.slice(1)
  // KZ national numbers start with 7; a leading 8 is the old trunk prefix.
  if (d.startsWith('8')) d = d.slice(1)
  return d.slice(0, PHONE_DIGITS)
}

/** "7011234567" -> "+7 701 123 45 67" (partial input is formatted as far as it goes). */
export function formatNational(d: string): string {
  if (!d) return ''
  const parts = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 8), d.slice(8, 10)].filter(Boolean)
  return `+7 ${parts.join(' ')}`
}

export function toE164(d: string): string {
  return d.length === PHONE_DIGITS ? `+7${d}` : ''
}

export function isCompletePhone(e164: string): boolean {
  return /^\+7\d{10}$/.test(e164)
}

/** Position in the formatted string right after the n-th digit. Used to keep the caret in place. */
export function caretAfterDigits(formatted: string, n: number): number {
  if (n <= 0) return formatted ? 3 : 0 // after "+7 "
  let seen = 0
  for (let i = 3; i < formatted.length; i++) {
    if (/\d/.test(formatted[i] ?? '')) seen++
    if (seen === n) return i + 1
  }
  return formatted.length
}
