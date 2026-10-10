/** متن بلند (بیشتر از maxLines خط یا maxChars نویسه) پیش‌فرض کوتاه نشان داده می‌شود و دکمهٔ «بیشتر» می‌گیرد. */
export function needsClamp(text: string | null | undefined, maxLines = 3, maxChars = 180): boolean {
  const value = (text ?? "").trim();
  if (!value) return false;
  return value.length > maxChars || value.split(/\r?\n/).length > maxLines;
}
