/** سازگاری با price.write تا مهاجرت کامل نقش‌ها. */

export function hasPriceApprove(has: (perm: string) => boolean): boolean {
  return has("price.approve") || has("price.write");
}

export function hasExpensePay(has: (perm: string) => boolean): boolean {
  return has("expense.pay") || has("price.write");
}

export function hasExpenseTeamApprove(has: (perm: string) => boolean): boolean {
  return (
    has("org.admin") ||
    has("expense.approve") ||
    has("request.triage") ||
    has("request.manage")
  );
}
