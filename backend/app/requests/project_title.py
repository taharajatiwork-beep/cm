"""عنوان پروژه بدون پسوند « — نام تیم» (قرارداد UI قدیمی)."""


def project_title_without_team_suffix(title: str, team_name: str | None) -> str:
    if not team_name or not title:
        return title
    suffix = f" — {team_name}"
    if title.endswith(suffix):
        stripped = title[: -len(suffix)].strip()
        if stripped:
            return stripped
    return title
