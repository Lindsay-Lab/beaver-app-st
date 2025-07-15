"""
Unit tests for constants.py.

Tests that constants are properly defined and have expected values
for scientific calculations and processing parameters.
"""

import pytest


class TestStateAbbreviations:
    """Test state abbreviation mappings."""

    @pytest.mark.unit
    def test_state_abbreviations_exist(self):
        """Test that state abbreviations dictionary exists."""
        from service.constants import STATE_ABBREVIATIONS

        assert isinstance(STATE_ABBREVIATIONS, dict)
        assert len(STATE_ABBREVIATIONS) > 0

    @pytest.mark.unit
    def test_common_states(self):
        """Test that common states are included."""
        from service.constants import STATE_ABBREVIATIONS

        # Test some common states
        expected_states = {
            "California": "CA",
            "Oregon": "OR",
            "Washington": "WA",
            "Colorado": "CO",
            "Montana": "MT",
            "Wyoming": "WY",
            "Idaho": "ID",
            "Utah": "UT",
            "Nevada": "NV",
            "Arizona": "AZ",
        }

        for state_name, expected_abbrev in expected_states.items():
            assert state_name in STATE_ABBREVIATIONS
            assert STATE_ABBREVIATIONS[state_name] == expected_abbrev

    @pytest.mark.unit
    def test_abbreviation_format(self):
        """Test that abbreviations are properly formatted."""
        from service.constants import STATE_ABBREVIATIONS

        for state_name, abbrev in STATE_ABBREVIATIONS.items():
            # All abbreviations should be exactly 2 characters
            assert len(abbrev) == 2, f"Invalid abbreviation length for {state_name}: {abbrev}"

            # All abbreviations should be uppercase
            assert abbrev.isupper(), f"Abbreviation not uppercase for {state_name}: {abbrev}"

            # State names should be properly capitalized
            assert state_name[0].isupper(), f"State name not capitalized: {state_name}"

    @pytest.mark.unit
    def test_no_duplicate_abbreviations(self):
        """Test that no two states have the same abbreviation."""
        from service.constants import STATE_ABBREVIATIONS

        abbreviations = list(STATE_ABBREVIATIONS.values())
        unique_abbreviations = set(abbreviations)

        assert len(abbreviations) == len(unique_abbreviations), "Duplicate abbreviations found"


class TestProcessingConstants:
    """Test processing-related constants."""

    @pytest.mark.unit
    def test_batch_sizes(self):
        """Test that batch sizes are reasonable."""
        from service.constants import DEFAULT_BATCH_SIZE, LARGE_BATCH_SIZE

        # Batch sizes should be positive integers
        assert isinstance(DEFAULT_BATCH_SIZE, int)
        assert isinstance(LARGE_BATCH_SIZE, int)
        assert DEFAULT_BATCH_SIZE > 0
        assert LARGE_BATCH_SIZE > 0

        # Large batch size should be larger than default
        assert LARGE_BATCH_SIZE > DEFAULT_BATCH_SIZE

        # Batch sizes should be reasonable (not too small or too large)
        assert 1 <= DEFAULT_BATCH_SIZE <= 50
        assert 1 <= LARGE_BATCH_SIZE <= 100

    @pytest.mark.unit
    def test_pixel_limits(self):
        """Test that pixel limits are reasonable."""
        from service.constants import MAX_PIXELS_LARGE, MAX_PIXELS_SMALL

        # Pixel limits should be positive integers
        assert isinstance(MAX_PIXELS_SMALL, int)
        assert isinstance(MAX_PIXELS_LARGE, int)
        assert MAX_PIXELS_SMALL > 0
        assert MAX_PIXELS_LARGE > 0

        # Large pixel limit should be larger than small
        assert MAX_PIXELS_LARGE > MAX_PIXELS_SMALL

        # Pixel limits should be reasonable for Earth Engine
        assert 1000000 <= MAX_PIXELS_SMALL <= 10000000000
        assert 1000000000 <= MAX_PIXELS_LARGE <= 100000000000000

    @pytest.mark.unit
    def test_scale_constants(self):
        """Test that scale constants are reasonable."""
        from service.constants import LANDSAT_SCALE, SENTINEL2_SCALE

        # Scale should be positive numbers
        assert isinstance(SENTINEL2_SCALE, (int, float))
        assert isinstance(LANDSAT_SCALE, (int, float))
        assert SENTINEL2_SCALE > 0
        assert LANDSAT_SCALE > 0

        # Scale should be reasonable for satellite imagery
        assert 1 <= SENTINEL2_SCALE <= 1000
        assert 1 <= LANDSAT_SCALE <= 1000

        # Sentinel-2 should have finer resolution than Landsat
        assert SENTINEL2_SCALE <= LANDSAT_SCALE


class TestVisualizationConstants:
    """Test visualization-related constants."""

    @pytest.mark.unit
    def test_plot_dimensions(self):
        """Test that plot dimensions are reasonable."""
        from service.constants import PLOT_FIGURE_HEIGHT_LARGE, PLOT_FIGURE_HEIGHT_SMALL, PLOT_FIGURE_WIDTH

        # Dimensions should be positive numbers
        assert isinstance(PLOT_FIGURE_WIDTH, (int, float))
        assert isinstance(PLOT_FIGURE_HEIGHT_SMALL, (int, float))
        assert isinstance(PLOT_FIGURE_HEIGHT_LARGE, (int, float))
        assert PLOT_FIGURE_WIDTH > 0
        assert PLOT_FIGURE_HEIGHT_SMALL > 0
        assert PLOT_FIGURE_HEIGHT_LARGE > 0

        # Large height should be larger than small
        assert PLOT_FIGURE_HEIGHT_LARGE > PLOT_FIGURE_HEIGHT_SMALL

        # Dimensions should be reasonable for plots
        assert 1 <= PLOT_FIGURE_WIDTH <= 30
        assert 1 <= PLOT_FIGURE_HEIGHT_SMALL <= 30
        assert 1 <= PLOT_FIGURE_HEIGHT_LARGE <= 30

    @pytest.mark.unit
    def test_map_dimensions(self):
        """Test that map dimensions are reasonable."""
        from service.constants import MAP_HEIGHT, MAP_WIDTH

        # Dimensions should be positive integers
        assert isinstance(MAP_WIDTH, int)
        assert isinstance(MAP_HEIGHT, int)
        assert MAP_WIDTH > 0
        assert MAP_HEIGHT > 0

        # Dimensions should be reasonable for web maps
        assert 100 <= MAP_WIDTH <= 2000
        assert 100 <= MAP_HEIGHT <= 2000


class TestScientificConstants:
    """Test scientific/algorithm-related constants."""

    @pytest.mark.unit
    def test_elevation_thresholds(self):
        """Test elevation threshold constants."""
        from service.constants import ELEVATION_THRESHOLD_LOWER, ELEVATION_THRESHOLD_UPPER

        # Thresholds should be positive numbers
        assert isinstance(ELEVATION_THRESHOLD_UPPER, (int, float))
        assert isinstance(ELEVATION_THRESHOLD_LOWER, (int, float))
        assert ELEVATION_THRESHOLD_UPPER > 0
        assert ELEVATION_THRESHOLD_LOWER > 0

        # Thresholds should be reasonable for elevation masking
        assert 0.1 <= ELEVATION_THRESHOLD_UPPER <= 50
        assert 0.1 <= ELEVATION_THRESHOLD_LOWER <= 50

    @pytest.mark.unit
    def test_buffer_distances(self):
        """Test buffer distance constants."""
        from service.constants import ELEVATION_BUFFER_RADIUS, MIN_DISTANCE_FROM_DAMS

        # Distances should be positive numbers
        assert isinstance(ELEVATION_BUFFER_RADIUS, (int, float))
        assert isinstance(MIN_DISTANCE_FROM_DAMS, (int, float))
        assert ELEVATION_BUFFER_RADIUS > 0
        assert MIN_DISTANCE_FROM_DAMS > 0

        # Distances should be reasonable in meters
        assert 1 <= ELEVATION_BUFFER_RADIUS <= 10000
        assert 1 <= MIN_DISTANCE_FROM_DAMS <= 10000


class TestConstantConsistency:
    """Test consistency between related constants."""

    @pytest.mark.unit
    def test_batch_size_consistency(self):
        """Test that batch sizes are consistent with pixel limits."""
        from service.constants import DEFAULT_BATCH_SIZE, LARGE_BATCH_SIZE, MAX_PIXELS_LARGE, MAX_PIXELS_SMALL

        # Larger batch sizes should be used with larger pixel limits
        # This is a logical consistency check
        batch_ratio = LARGE_BATCH_SIZE / DEFAULT_BATCH_SIZE
        pixel_ratio = MAX_PIXELS_LARGE / MAX_PIXELS_SMALL

        # The ratios should be in the same order of magnitude
        # Note: batch_ratio is typically much smaller than pixel_ratio
        assert 0.0001 <= batch_ratio / pixel_ratio <= 10

    @pytest.mark.unit
    def test_plot_dimension_consistency(self):
        """Test that plot dimensions are consistent."""
        from service.constants import PLOT_FIGURE_HEIGHT_LARGE, PLOT_FIGURE_HEIGHT_SMALL, PLOT_FIGURE_WIDTH

        # Width should be reasonable relative to heights
        assert PLOT_FIGURE_WIDTH >= min(PLOT_FIGURE_HEIGHT_SMALL, PLOT_FIGURE_HEIGHT_LARGE)

        # Height difference should be reasonable
        height_ratio = PLOT_FIGURE_HEIGHT_LARGE / PLOT_FIGURE_HEIGHT_SMALL
        assert 1.0 <= height_ratio <= 5.0  # Large should be at most 5x small


class TestConstantTypes:
    """Test that constants have correct types."""

    @pytest.mark.unit
    def test_integer_constants(self):
        """Test constants that should be integers."""
        from service.constants import (
            DEFAULT_BATCH_SIZE,
            LARGE_BATCH_SIZE,
            MAP_HEIGHT,
            MAP_WIDTH,
            MAX_PIXELS_LARGE,
            MAX_PIXELS_SMALL,
        )

        integer_constants = [
            DEFAULT_BATCH_SIZE,
            LARGE_BATCH_SIZE,
            MAX_PIXELS_SMALL,
            MAX_PIXELS_LARGE,
            MAP_WIDTH,
            MAP_HEIGHT,
        ]

        for constant in integer_constants:
            assert isinstance(constant, int), f"Constant should be integer: {constant}"

    @pytest.mark.unit
    def test_numeric_constants(self):
        """Test constants that should be numeric (int or float)."""
        from service.constants import (
            ELEVATION_BUFFER_RADIUS,
            ELEVATION_THRESHOLD_LOWER,
            ELEVATION_THRESHOLD_UPPER,
            LANDSAT_SCALE,
            MIN_DISTANCE_FROM_DAMS,
            SENTINEL2_SCALE,
        )

        numeric_constants = [
            SENTINEL2_SCALE,
            LANDSAT_SCALE,
            ELEVATION_THRESHOLD_UPPER,
            ELEVATION_THRESHOLD_LOWER,
            ELEVATION_BUFFER_RADIUS,
            MIN_DISTANCE_FROM_DAMS,
        ]

        for constant in numeric_constants:
            assert isinstance(constant, (int, float)), f"Constant should be numeric: {constant}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
