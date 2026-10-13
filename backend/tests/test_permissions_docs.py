"""مستندات نقش‌ها با permissions.py یکی بماند."""

import re
from pathlib import Path

from app.core.permissions import ROLE_TEMPLATES


def test_role_templates_documented_in_roles_plan():
    doc = Path(__file__).resolve().parents[2] / "docs" / "roles-plan.md"
    text = doc.read_text(encoding="utf-8")
    for code in ROLE_TEMPLATES:
        assert f"`{code}`" in text, f"نقش {code} در roles-plan.md نیست"


def test_permission_codes_listed_in_roles_plan():
    doc = Path(__file__).resolve().parents[2] / "docs" / "roles-plan.md"
    text = doc.read_text(encoding="utf-8")
    for code in ("price.approve", "expense.pay", "report.read"):
        assert code in text, f"مجوز {code} در roles-plan.md نیست"
