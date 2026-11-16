/*
 * One clock for everyone. A device clock may be minutes or hours off, so "now" is the server's time:
 * every API answer carries the server's Date, and the difference to the device clock is kept here.
 */
let skew = 0

/** Called with the Date header of an API response. */
export function syncClock(header: string | null): void {
  const server = header ? Date.parse(header) : NaN
  if (Number.isNaN(server)) return
  // The header has one-second precision and the answer took time to arrive: small differences are noise.
  const diff = server + 500 - Date.now()
  skew = Math.abs(diff) > 5000 ? diff : 0
}

/** Current instant (epoch ms) by the server clock. */
export const nowMs = (): number => Date.now() + skew
