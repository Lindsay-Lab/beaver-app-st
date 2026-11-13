from pages.analyze_impacts import describe_missing_elevation, describe_sample_area


def test_no_note_when_every_location_has_elevation():
    assert describe_missing_elevation({"missing": [], "total": 4}) is None


def test_all_locations_missing_elevation():
    note = describe_missing_elevation({"missing": ["P1", "N1"], "total": 2})
    assert "no elevation data for these locations" in note
    assert "whole buffer" in note


def test_some_locations_missing_elevation_uses_whole_buffer_for_all():
    note = describe_missing_elevation({"missing": ["P3", "N3"], "total": 6})
    assert "2 of 6 locations (P3, N3)" in note
    assert "whole buffer is used for all of them" in note


def test_long_lists_are_truncated():
    missing = [f"P{i}" for i in range(1, 14)]
    note = describe_missing_elevation({"missing": missing, "total": 20}, max_listed=10)
    assert "P10 and 3 more" in note
    assert "P11" not in note


def test_sample_area_with_elevation_filter():
    note = describe_sample_area(3, missing_elevation=False)
    assert note == "Elevation filter: only land from 10 m below to 3 m above each location's elevation was analyzed."


def test_sample_area_whole_buffer_chosen_by_user():
    assert "selected in Step 5" in describe_sample_area(None, missing_elevation=False)


def test_sample_area_whole_buffer_because_elevation_is_missing():
    note = describe_sample_area(None, missing_elevation=True)
    assert "elevation data isn't available for every location" in note
    assert "selected in Step 5" not in note
