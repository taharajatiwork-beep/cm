import { faDigits, splitLatin } from "../fa";

/**
 * متن آمادهٔ سرور در رابط فارسی: رقم‌های جدا فارسی می‌شوند و هر تکهٔ لاتین
 * (کد کمپین، شناسه) داخل <bdi> می‌رود تا «S84: 2» در متن راست‌به‌چپ جابه‌جا نشود.
 */
export function FaText({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <>
      {splitLatin(text).map((part, index) =>
        part.latin ? <bdi key={index}>{part.text}</bdi> : <span key={index}>{faDigits(part.text)}</span>,
      )}
    </>
  );
}
