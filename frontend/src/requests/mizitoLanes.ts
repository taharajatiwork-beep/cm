export const MIZITO_LANE_LABEL: Record<string, string> = {
  finance_marketing: "مالی و مارکتینگ",
  content: "تولید محتوا",
  performance: "پرفورمنس مارکتینگ",
  campaigns: "کمپین‌ها",
  automation: "اتومیشن مارکتینگ",
  sales_circulars: "بخشنامه‌های فروش",
};

export function mizitoLaneLabel(slug: string | null | undefined): string {
  if (!slug) return "";
  return MIZITO_LANE_LABEL[slug] ?? slug;
}
