import { useBi } from "../i18n";

const KNOWN: Record<string, [string, string]> = {
  "New task assigned": ["New task assigned", "کار جدید به شما سپرده شد"],
  "کار جدید به شما سپرده شد": ["New task assigned", "کار جدید به شما سپرده شد"],
};

const LEGACY_PATTERNS: Array<{ pattern: RegExp; fa: (m: RegExpMatchArray) => string }> = [
  {
    pattern: /^Case (\S+) assigned$/,
    fa: (m) => `پیگیری ${m[1]} به شما سپرده شد`,
  },
  {
    pattern: /^Case (\S+) escalated \(SLA\)$/,
    fa: (m) => `پیگیری ${m[1]} — مهلت SLA گذشت`,
  },
];

export function useNotificationTitle() {
  const bi = useBi();
  return (raw: string) => {
    const pair = KNOWN[raw];
    if (pair) return bi(pair[0], pair[1]);
    for (const rule of LEGACY_PATTERNS) {
      const match = raw.match(rule.pattern);
      if (match) return rule.fa(match);
    }
    return raw;
  };
}
