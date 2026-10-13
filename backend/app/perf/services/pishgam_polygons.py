"""تقسیم پلیگان برای محدودیت ۲ کیلومتر و بسته‌بندی Create."""

from __future__ import annotations

import math

MAX_EDGE_KM = 2.0
MAX_POLYGONS_PER_CREATE = 3


def _mid_lat(ring: list[list[float]]) -> float:
    lats = [p[1] for p in ring]
    return (min(lats) + max(lats)) / 2 if lats else 35.0


def km_to_degrees(km: float, lat: float) -> tuple[float, float]:
    dlat = km / 111.32
    dlng = km / (111.32 * max(math.cos(math.radians(lat)), 0.2))
    return dlat, dlng


def ring_bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lngs), min(lats), max(lngs), max(lats)


def edge_lengths_km(ring: list[list[float]]) -> tuple[float, float]:
    min_lng, min_lat, max_lng, max_lat = ring_bbox(ring)
    mid = _mid_lat(ring)
    _, dlng = km_to_degrees(1.0, mid)
    dlat = 1.0 / 111.32
    width_km = (max_lng - min_lng) / dlng if dlng else 0.0
    height_km = (max_lat - min_lat) / dlat if dlat else 0.0
    return width_km, height_km


def close_ring(ring: list[list[float]]) -> list[list[float]]:
    if not ring:
        return ring
    first, last = ring[0], ring[-1]
    if first[0] == last[0] and first[1] == last[1]:
        return ring
    return [*ring, first]


def split_ring(ring: list[list[float]], max_km: float = MAX_EDGE_KM) -> list[list[list[float]]]:
    """حلقه را به مستطیل‌های بسته ≤ max_km تقسیم می‌کند. خروجی: لیست حلقه‌ها [lng, lat]."""
    ring = close_ring(ring)
    min_lng, min_lat, max_lng, max_lat = ring_bbox(ring)
    mid = _mid_lat(ring)
    dlat, dlng = km_to_degrees(max_km, mid)
    if dlat <= 0 or dlng <= 0:
        return [ring]
    cells: list[list[list[float]]] = []
    lat = min_lat
    while lat < max_lat:
        lat2 = min(lat + dlat, max_lat)
        lng = min_lng
        while lng < max_lng:
            lng2 = min(lng + dlng, max_lng)
            cells.append(close_ring([[lng, lat2], [lng2, lat2], [lng2, lat], [lng, lat]]))
            lng = lng2
        lat = lat2
    return cells or [ring]


def fragment_count(ring: list[list[float]]) -> int:
    return len(split_ring(ring))


def batch_rings(rings: list[list[list[float]]], size: int = MAX_POLYGONS_PER_CREATE) -> list[list[list[list[float]]]]:
    """هر بسته برای فیلد polygons در Create: number[][][]."""
    batches: list[list[list[list[float]]]] = []
    for index in range(0, len(rings), size):
        batches.append(rings[index : index + size])
    return batches
