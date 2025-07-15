"""
Unit tests for Parser.py functions.

Tests coordinate cleaning, date parsing, and other utility functions
without requiring Earth Engine authentication.
"""

import pytest

from service.Parser import clean_coordinate, parse_date


class TestCoordinateCleaning:
    """Test coordinate cleaning functionality."""

    @pytest.mark.unit
    def test_clean_coordinate_valid_inputs(self, sample_coordinate_data):
        """Test coordinate cleaning with valid inputs."""
        for input_value, expected_output in sample_coordinate_data:
            result = clean_coordinate(input_value)
            if expected_output is None:
                assert result is None
            else:
                assert abs(result - expected_output) < 0.001

    @pytest.mark.unit
    def test_clean_coordinate_edge_cases(self):
        """Test coordinate cleaning with edge cases."""
        # Test very small numbers
        assert abs(clean_coordinate("0.001") - 0.001) < 0.0001

        # Test very large numbers
        assert abs(clean_coordinate("180.0") - 180.0) < 0.001

        # Test negative numbers
        assert abs(clean_coordinate("-90.0") - (-90.0)) < 0.001

        # Test numbers with multiple decimal points
        assert clean_coordinate("45.123.456") is None

        # Test numbers with letters
        assert clean_coordinate("45abc") is None

    @pytest.mark.unit
    def test_clean_coordinate_boundary_values(self):
        """Test coordinate cleaning with boundary values."""
        # Valid latitude/longitude boundaries
        assert abs(clean_coordinate("90.0") - 90.0) < 0.001
        assert abs(clean_coordinate("-90.0") - (-90.0)) < 0.001
        assert abs(clean_coordinate("180.0") - 180.0) < 0.001
        assert abs(clean_coordinate("-180.0") - (-180.0)) < 0.001


class TestDateParsing:
    """Test date parsing functionality."""

    @pytest.mark.unit
    def test_parse_date_auto_detect(self, sample_date_data):
        """Test date parsing with auto-detection."""
        for input_value, expected_output in sample_date_data:
            result = parse_date(input_value, "Auto Detect")
            assert result == expected_output

    @pytest.mark.unit
    def test_parse_date_specific_formats(self):
        """Test date parsing with specific formats."""
        # Test specific format parsing
        assert parse_date("2020-07-15", "%Y-%m-%d") == "2020-07-15"
        assert parse_date("07/15/2020", "%m/%d/%Y") == "2020-07-15"
        assert parse_date("15-07-2020", "%d-%m-%Y") == "2020-07-15"

        # Test invalid format
        assert parse_date("2020-07-15", "%m/%d/%Y") is None

    @pytest.mark.unit
    def test_parse_date_unix_timestamp(self):
        """Test date parsing with Unix timestamps."""
        # Test Unix timestamp (July 1, 2020)
        timestamp = 1593561600
        result = parse_date(timestamp, "Unix Timestamp")
        assert result == "2020-07-01"

        # Test invalid timestamp
        assert parse_date("invalid", "Unix Timestamp") is None

    @pytest.mark.unit
    def test_parse_date_edge_cases(self):
        """Test date parsing with edge cases."""
        # Test leap year
        assert parse_date("2020-02-29", "Auto Detect") == "2020-02-29"

        # Test end of year
        assert parse_date("2020-12-31", "Auto Detect") == "2020-12-31"

        # Test invalid date
        assert parse_date("2020-13-01", "Auto Detect") is None
        assert parse_date("2020-02-30", "Auto Detect") is None


class TestDataProcessing:
    """Test data processing utilities."""

    @pytest.mark.unit
    def test_coordinate_validation_range(self):
        """Test that coordinates are within valid ranges."""
        # Valid coordinates
        assert clean_coordinate("45.0") == 45.0  # Valid latitude
        assert clean_coordinate("-122.0") == -122.0  # Valid longitude

        # Note: The current implementation doesn't validate ranges,
        # but this test documents the expected behavior
        # In a real implementation, you might want to add range validation

    @pytest.mark.unit
    def test_date_validation_range(self):
        """Test that dates are within reasonable ranges."""
        # Valid dates for satellite imagery
        assert parse_date("2020-07-15", "Auto Detect") == "2020-07-15"
        assert parse_date("2015-01-01", "Auto Detect") == "2015-01-01"

        # Very old dates (might be invalid for satellite data)
        assert parse_date("1900-01-01", "Auto Detect") == "1900-01-01"

        # Future dates
        assert parse_date("2030-01-01", "Auto Detect") == "2030-01-01"


class TestErrorHandling:
    """Test error handling in parsing functions."""

    @pytest.mark.unit
    def test_coordinate_error_handling(self):
        """Test error handling in coordinate cleaning."""
        # Should not raise exceptions, should return None
        assert clean_coordinate(None) is None
        assert clean_coordinate("") is None
        assert clean_coordinate("not_a_number") is None
        assert clean_coordinate("45.123.456") is None

    @pytest.mark.unit
    def test_date_error_handling(self):
        """Test error handling in date parsing."""
        # Should not raise exceptions, should return None
        assert parse_date(None, "Auto Detect") is None
        assert parse_date("", "Auto Detect") is None
        assert parse_date("not_a_date", "Auto Detect") is None
        assert parse_date("2020-13-01", "Auto Detect") is None


class TestDataIntegrity:
    """Test data integrity and consistency."""

    @pytest.mark.unit
    def test_coordinate_precision(self):
        """Test that coordinate precision is maintained."""
        # Test high precision coordinates
        result = clean_coordinate("45.123456789")
        assert abs(result - 45.123456789) < 0.0000001

        # Test that precision is not artificially limited
        result = clean_coordinate("-122.987654321")
        assert abs(result - (-122.987654321)) < 0.0000001

    @pytest.mark.unit
    def test_date_consistency(self):
        """Test that date parsing is consistent."""
        # Same date in different formats should produce same result
        formats = [
            ("2020-07-15", "Auto Detect"),
            ("2020/07/15", "Auto Detect"),
            ("07/15/2020", "Auto Detect"),
        ]

        expected = "2020-07-15"
        for date_str, format_str in formats:
            result = parse_date(date_str, format_str)
            assert result == expected, f"Failed for {date_str} with format {format_str}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
