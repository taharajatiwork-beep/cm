import { useBi } from "../i18n";

const KNOWN: Record<string, [string, string]> = {
  "New task assigned": ["New task assigned", "کار جدید به شما سپرده شد"],
  "کار جدید به شما سپرده شد": ["New task assigned", "کار جدید به شما سپرده شد"],
};

export function useNotificationTitle() {
  const bi = useBi();
  return (raw: string) => {
    const pair = KNOWN[raw];
    return pair ? bi(pair[0], pair[1]) : raw;
  };
}
