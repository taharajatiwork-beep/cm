from app.requests.mizito_lanes import lane_for_mizito_project_title, wanted_marketing_mizito_project


def test_lane_titles_match_mizito_projects():
    assert wanted_marketing_mizito_project("پرفورمنس مارکتینگ")
    assert wanted_marketing_mizito_project("کمپین ها")
    lane = lane_for_mizito_project_title("مالی و مارکتینگ")
    assert lane is not None
    assert lane.slug == "finance_marketing"


def test_unknown_project_not_marketing_lane():
    assert not wanted_marketing_mizito_project("فروش خودرو")
