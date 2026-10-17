from app.perf.services.mizito import read_cards


def test_read_cards_exports_lane_boards():
    projects = {
        "projects": [
            {
                "_id": "p1",
                "title": "مالی و مارکتینگ",
                "kanban_boards": [
                    {"_id": "b1", "title": "ثبت نشده در Cost Tracking"},
                    {"_id": "b2", "title": "پرداخت شده"},
                ],
            }
        ]
    }
    tasks = [
        {
            "_id": "t1",
            "title": "S12 test",
            "project": "p1",
            "kanban_board": "b1",
            "checklist": [],
        }
    ]
    data = read_cards(projects, tasks)
    assert len(data["lane_boards"]) == 2
    assert data["lane_boards"][0]["lane_slug"] == "finance_marketing"
    assert data["cards"][0]["board"] == "ثبت نشده در Cost Tracking"
