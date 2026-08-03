"""Offline reverse geocoding: coordinates to a nearest-place name.

Entirely local — a k-d tree over ~150k GeoNames cities bundled with
`reverse_geocoder`. No web geocoding service is used, and none should be: the
coordinates of someone's photos are exactly the kind of thing a local-first app
must not send anywhere.

Two properties of this that shape the API:

- It returns the *nearest known place*, not the place you were in. A photo in
  the White Mountains resolves to a town ~13 km away because no town is nearer.
  `Place.distance_km` is therefore part of the result, so callers can say "near
  Gorham" rather than claiming the photo was taken there.
- Beyond `place_max_km` nothing is returned at all. Naming a city 400 km across
  an ocean is worse than admitting we don't know.

Memory: the tree costs ~100 MB resident and is built lazily on first use, so a
library with no GPS data never pays for it. It must only ever be built in the
parent process — building it inside each scan worker would multiply that by the
worker count.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Place:
    """The nearest known place to a coordinate."""

    city: str
    # GeoNames admin1: state in the US, province/region elsewhere. Absent for
    # city-states and some small territories.
    region: str | None
    # ISO 3166-1 alpha-2.
    country: str
    distance_km: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _search(coordinates: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Query the bundled dataset.

    Imported lazily so the 7.5 MB dataset and its tree are only paid for when
    something actually geocodes. mode=1 is required: the default forks a
    process pool, which must not happen inside a web worker or a scan job.
    """
    import reverse_geocoder

    return list(reverse_geocoder.search(coordinates, mode=1, verbose=False))


def _to_place(
    row: dict[str, Any], latitude: float, longitude: float, max_km: float
) -> Place | None:
    city = (row.get("name") or "").strip()
    if not city:
        return None
    try:
        distance = haversine_km(latitude, longitude, float(row["lat"]), float(row["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    if distance > max_km:
        return None
    region = (row.get("admin1") or "").strip() or None
    return Place(
        city=city,
        region=region,
        country=(row.get("cc") or "").strip().upper(),
        distance_km=round(distance, 1),
    )


def lookup_places(
    coordinates: list[tuple[float, float]], max_km: float | None = None
) -> list[Place | None]:
    """Reverse geocode a batch. Batching is much cheaper than one call each."""
    if not coordinates:
        return []
    limit = get_settings().place_max_km if max_km is None else max_km
    try:
        rows = _search(coordinates)
    except Exception:  # noqa: BLE001 - geocoding is enrichment; never fail a scan for it
        logger.exception("reverse geocoding failed for %d coordinate(s)", len(coordinates))
        return [None] * len(coordinates)
    if len(rows) != len(coordinates):  # pragma: no cover - defensive
        logger.error("reverse geocoder returned %d rows for %d inputs", len(rows), len(coordinates))
        return [None] * len(coordinates)
    return [
        _to_place(row, lat, lon, limit) for row, (lat, lon) in zip(rows, coordinates, strict=True)
    ]


def lookup_place(latitude: float | None, longitude: float | None) -> Place | None:
    """Reverse geocode one coordinate, or None if it has none."""
    if latitude is None or longitude is None:
        return None
    return lookup_places([(latitude, longitude)])[0]
