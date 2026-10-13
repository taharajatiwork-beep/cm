import { useBi } from "../i18n";

const VALUE_LABELS: Record<string, [string, string]> = {
  manual: ["Manual", "دستی"],
  automatic: ["Automatic", "اتوماتیک"],
  petrol: ["Petrol", "بنزین"],
  diesel: ["Diesel", "گازوئیل"],
  hybrid: ["Hybrid", "هیبرید"],
  electric: ["Electric", "برقی"],
  sedan: ["Sedan", "سدان"],
  suv: ["SUV", "شاسی‌بلند"],
  hatchback: ["Hatchback", "هاچ‌بک"],
  white: ["White", "سفید"],
  red: ["Red", "قرمز"],
  black: ["Black", "مشکی"],
  silver: ["Silver", "نقره‌ای"],
  gray: ["Gray", "خاکستری"],
  grey: ["Grey", "خاکستری"],
  blue: ["Blue", "آبی"],
};

export function useVehicleLabel() {
  const bi = useBi();
  return (value: string | null | undefined) => {
    if (!value) return "—";
    const key = value.trim().toLowerCase();
    const pair = VALUE_LABELS[key];
    return pair ? bi(pair[0], pair[1]) : value;
  };
}
