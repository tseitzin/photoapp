"""Reverse geocoding names the nearest known place — and admits when it can't.

These tests exercise the real bundled dataset rather than a mock: the value of
this feature is entirely in whether the names it produces are right, and a
mocked k-d tree would prove nothing.
"""

import pytest

from app.geo.places import Place, haversine_km, lookup_place, lookup_places


def test_a_city_coordinate_resolves_to_that_city() -> None:
    place = lookup_place(42.3601, -71.0589)  # Boston City Hall

    assert place is not None
    assert place.city == "Boston"
    assert place.region == "Massachusetts"
    assert place.country == "US"
    assert place.distance_km < 5


def test_a_place_outside_the_us_gets_its_own_region_naming() -> None:
    place = lookup_place(51.5074, -0.1278)  # Westminster

    assert place is not None
    assert place.country == "GB"
    assert place.region  # England — admin1 is a country within the UK


def test_wilderness_reports_the_distance_to_the_nearest_town() -> None:
    """Mount Washington: the nearest town is well away, and saying so is the
    difference between "near Gorham" and a false claim about where it was taken."""
    place = lookup_place(44.2705, -71.3033)

    assert place is not None
    assert place.region == "New Hampshire"
    assert place.distance_km > 5


def test_the_middle_of_an_ocean_gets_no_place_at_all() -> None:
    assert lookup_place(35.0, -40.0) is None


def test_a_photo_without_coordinates_is_not_geocoded() -> None:
    assert lookup_place(None, None) is None
    assert lookup_place(42.36, None) is None
    assert lookup_place(None, -71.05) is None


def test_the_distance_cap_is_configurable() -> None:
    coordinate = (44.2705, -71.3033)

    assert lookup_places([coordinate], max_km=1000)[0] is not None
    assert lookup_places([coordinate], max_km=0.5)[0] is None


def test_a_batch_answers_in_input_order() -> None:
    places = lookup_places([(42.3601, -71.0589), (35.0, -40.0), (51.5074, -0.1278)])

    assert len(places) == 3
    assert places[0] is not None and places[0].city == "Boston"
    assert places[1] is None
    assert places[2] is not None and places[2].country == "GB"


def test_an_empty_batch_does_not_build_the_lookup_tree() -> None:
    assert lookup_places([]) == []


def test_a_geocoder_failure_yields_no_places_rather_than_breaking_the_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Place names are enrichment; losing them must never fail an indexing run."""
    import app.geo.places as places

    def boom(_: object) -> list[dict[str, str]]:
        raise RuntimeError("dataset unreadable")

    monkeypatch.setattr(places, "_search", boom)

    assert lookup_places([(42.3601, -71.0589), (51.5074, -0.1278)]) == [None, None]


@pytest.mark.parametrize(
    ("a", "b", "expected_km"),
    [
        ((42.3601, -71.0589), (42.3601, -71.0589), 0.0),
        ((0.0, 0.0), (0.0, 1.0), 111.2),  # one degree of longitude at the equator
        ((42.3601, -71.0589), (51.5074, -0.1278), 5263.0),  # Boston to London
    ],
)
def test_haversine_matches_known_distances(
    a: tuple[float, float], b: tuple[float, float], expected_km: float
) -> None:
    assert haversine_km(a[0], a[1], b[0], b[1]) == pytest.approx(expected_km, rel=0.01, abs=0.1)


def test_place_is_immutable() -> None:
    """Rows are cached and shared; a mutable Place would be a footgun."""
    place = Place(city="Boston", region="Massachusetts", country="US", distance_km=0.2)

    with pytest.raises(AttributeError):
        place.city = "Cambridge"  # type: ignore[misc]
