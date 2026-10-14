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
  White: ["White", "سفید"],
  red: ["Red", "قرمز"],
  black: ["Black", "مشکی"],
  silver: ["Silver", "نقره‌ای"],
  gray: ["Gray", "خاکستری"],
  grey: ["Grey", "خاکستری"],
  blue: ["Blue", "آبی"],
  toyota: ["Toyota", "تویوتا"],
  hyundai: ["Hyundai", "هیوندای"],
  kia: ["Kia", "کیا"],
  peugeot: ["Peugeot", "پژو"],
  renault: ["Renault", "رنو"],
  mercedes: ["Mercedes-Benz", "مرسدس بنز"],
  "mercedes-benz": ["Mercedes-Benz", "مرسدس بنز"],
  bmw: ["BMW", "بی‌ام‌و"],
  nissan: ["Nissan", "نیسان"],
  mazda: ["Mazda", "مزدا"],
  suzuki: ["Suzuki", "سوزوکی"],
  mg: ["MG", "ام‌جی"],
  chery: ["Chery", "چری"],
  geely: ["Geely", "جیلی"],
  haval: ["Haval", "هاوال"],
  jac: ["JAC", "جک"],
  mvm: ["MVM", "ام‌وی‌ام"],
  camry: ["Camry", "کمری"],
  tucson: ["Tucson", "توسان"],
  sportage: ["Sportage", "اسپورتیج"],
  cerato: ["Cerato", "سراتو"],
};

const HISTORY_NOTE_LABELS: Record<string, [string, string]> = {
  "Vehicle created": ["Vehicle created", "خودرو ثبت شد"],
};

export function useVehicleLabel() {
  const bi = useBi();
  return (value: string | null | undefined) => {
    if (!value) return "—";
    const raw = value.trim();
    const key = raw.toLowerCase();
    const pair = VALUE_LABELS[key];
    return pair ? bi(pair[0], pair[1]) : raw;
  };
}

export function useVehicleHistoryNote() {
  const bi = useBi();
  return (value: string | null | undefined) => {
    if (!value) return "";
    const pair = HISTORY_NOTE_LABELS[value.trim()];
    return pair ? bi(pair[0], pair[1]) : value;
  };
}
