"""مجوزهای مالی: price.approve / expense.pay با سازگاری price.write."""

from app.core.permissions import PermissionCode


def has_price_approve(perms: set[str]) -> bool:
    if PermissionCode.ORG_ADMIN in perms:
        return True
    return PermissionCode.PRICE_APPROVE in perms or PermissionCode.PRICE_WRITE in perms


def has_expense_pay(perms: set[str]) -> bool:
    if PermissionCode.ORG_ADMIN in perms:
        return True
    return PermissionCode.EXPENSE_PAY in perms or PermissionCode.PRICE_WRITE in perms


def can_team_expense_approve(perms: set[str]) -> bool:
    """تأیید سرپرست تیم روی هزینه — جدا از پرداخت مالی."""
    if PermissionCode.ORG_ADMIN in perms:
        return True
    return PermissionCode.EXPENSE_APPROVE in perms or PermissionCode.REQUEST_TRIAGE in perms
