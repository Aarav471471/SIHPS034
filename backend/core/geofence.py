"""GeoJSON jurisdiction validation -- spec core/geofence.py.

An officer's findings are only legally actionable inside their notified
territory.  Every inspection is therefore stamped WITHIN_BOUNDS or
OUT_OF_BOUNDS at capture time, which is both an evidentiary safeguard and the
thing that stops one officer's numbers polluting another zone's analytics.

Shapely does the point-in-polygon work when available; a ray-casting fallback
keeps the check functional if it is not installed.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

from models.enums import JurisdictionStatus

logger = logging.getLogger("metrix.geofence")

try:
    from shapely.geometry import Point, shape

    _SHAPELY = True
except ImportError:  # pragma: no cover - optional dependency
    _SHAPELY = False

EARTH_RADIUS_KM = 6371.0088


@dataclass
class GeofenceResult:
    status: str
    within: bool
    jurisdiction_name: str | None = None
    distance_km: float | None = None   # to the boundary when outside
    reason: str | None = None


# ---------------------------------------------------------------------------
# Point in polygon
# ---------------------------------------------------------------------------
def _ray_cast(lat: float, lng: float, ring: list[list[float]]) -> bool:
    """Even-odd ray casting over a single [lng, lat] ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_at_lat = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lng < x_at_lat:
                inside = not inside
        j = i
    return inside


def _fallback_contains(lat: float, lng: float, geojson: dict[str, Any]) -> bool:
    """Polygon / MultiPolygon containment honouring interior rings (holes)."""
    gtype = geojson.get("type")
    coords = geojson.get("coordinates") or []

    def _polygon(rings: list) -> bool:
        if not rings:
            return False
        if not _ray_cast(lat, lng, rings[0]):
            return False
        return not any(_ray_cast(lat, lng, hole) for hole in rings[1:])

    if gtype == "Polygon":
        return _polygon(coords)
    if gtype == "MultiPolygon":
        return any(_polygon(rings) for rings in coords)
    logger.warning("Unsupported jurisdiction geometry type: %s", gtype)
    return False


def point_in_jurisdiction(
    latitude: float | None,
    longitude: float | None,
    jurisdiction_geojson: dict[str, Any] | None,
    jurisdiction_name: str | None = None,
) -> GeofenceResult:
    """Classify a capture location against an officer's territory.

    An absent location or an unassigned jurisdiction yields UNKNOWN rather than
    OUT_OF_BOUNDS -- refusing to record an inspection because a GPS fix was slow
    would be worse than flagging it for review.
    """
    if latitude is None or longitude is None:
        return GeofenceResult(
            status=JurisdictionStatus.UNKNOWN,
            within=False,
            jurisdiction_name=jurisdiction_name,
            reason="No GPS coordinates captured with this inspection",
        )
    if not jurisdiction_geojson:
        return GeofenceResult(
            status=JurisdictionStatus.UNKNOWN,
            within=False,
            jurisdiction_name=jurisdiction_name,
            reason="No jurisdiction polygon assigned to this officer",
        )

    try:
        if _SHAPELY:
            poly = shape(jurisdiction_geojson)
            pt = Point(longitude, latitude)
            inside = poly.contains(pt) or poly.touches(pt)
            distance = None
            if not inside:
                # Degrees -> km is only valid locally; adequate for an advisory
                # "how far outside" figure, and cheap.
                deg = poly.exterior.distance(pt) if hasattr(poly, "exterior") else poly.distance(pt)
                distance = round(deg * 111.32 * math.cos(math.radians(latitude)), 3)
        else:
            inside = _fallback_contains(latitude, longitude, jurisdiction_geojson)
            distance = None
    except Exception as exc:
        logger.warning("Geofence evaluation failed: %s", exc)
        return GeofenceResult(
            status=JurisdictionStatus.UNKNOWN,
            within=False,
            jurisdiction_name=jurisdiction_name,
            reason=f"Jurisdiction geometry could not be evaluated: {exc}",
        )

    if inside:
        return GeofenceResult(
            status=JurisdictionStatus.WITHIN_BOUNDS,
            within=True,
            jurisdiction_name=jurisdiction_name,
            distance_km=0.0,
        )
    return GeofenceResult(
        status=JurisdictionStatus.OUT_OF_BOUNDS,
        within=False,
        jurisdiction_name=jurisdiction_name,
        distance_km=distance,
        reason=(
            f"Capture location falls outside {jurisdiction_name or 'the assigned jurisdiction'}"
            + (f" by approximately {distance} km" if distance else "")
        ),
    )


# ---------------------------------------------------------------------------
# Distance helpers (routing engine and radar clustering both use these)
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) for a cheap SQL pre-filter.

    Used to narrow candidates with an index before paying for haversine on each.
    """
    dlat = radius_km / 111.32
    dlng = radius_km / (111.32 * max(0.01, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def centroid(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
