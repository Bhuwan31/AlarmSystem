/** Two-step confirmation before anything reaches people's phones: first the summary, then a final "are you sure".
 *  Replaces the two-factor / second-person requirement — one operator can send, but never with a single stray click. */
export function confirmTwice(summary: string, level?: string): boolean {
  if (!confirm(summary)) return false;
  const urgent = level === "CRITICAL" ? "\n\nCRITICAL: phones will get the most urgent alert and sirens may sound." : "";
  return confirm(`FINAL CHECK — this alerts real people's phones now and cannot be unsent.${urgent}\n\nPress OK to send.`);
}
