"""تقسیم پلیگان برای محدودیت پیشگام."""

import json

from app.perf.services.pishgam_polygons import batch_rings, fragment_count, split_ring
from app.perf.services.pishgam_targeting import _areas_path, load_areas


def _ring(key: str) -> list[list[float]]:
    raw = json.loads(_areas_path().read_text(encoding="utf-8"))
    for feature in raw.get("features") or []:
        props = feature.get("properties") or {}
        if props.get("key") == key:
            return ((feature.get("geometry") or {}).get("coordinates") or [[]])[0]
    raise KeyError(key)


def test_zaferanieh_stays_one_fragment():
    ring = _ring("zaferanieh")
    assert fragment_count(ring) == 1
    assert len(split_ring(ring)) == 1


def test_lavasan_splits_into_multiple_fragments():
    ring = _ring("lavasan")
    cells = split_ring(ring)
    assert len(cells) > 1
    assert all(cell[0] == cell[-1] for cell in cells)


def test_batch_rings_max_three():
    rings = [split_ring(_ring("zaferanieh"))[0] for _ in range(4)]
    batches = batch_rings(rings)
    assert len(batches) == 2
    assert len(batches[0]) == 3
    assert len(batches[1]) == 1


def test_load_areas_includes_fragment_count():
    lavasan = next(row for row in load_areas() if row["key"] == "lavasan")
    assert lavasan["fragment_count"] > 1
