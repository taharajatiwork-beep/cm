from app.requests.project_title import project_title_without_team_suffix


def test_strips_team_suffix():
    assert project_title_without_team_suffix("طراحی بنر — پرفورمنس", "پرفورمنس") == "طراحی بنر"


def test_keeps_title_when_suffix_mismatch():
    assert project_title_without_team_suffix("طراحی — پرفورمنس", "سوشال") == "طراحی — پرفورمنس"


def test_keeps_title_when_no_team():
    assert project_title_without_team_suffix("عنوان", None) == "عنوان"
