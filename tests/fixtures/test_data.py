"""
Test data fixtures for beaver dam analysis tests.

Contains sample data for testing coordinate parsing, date handling,
and other utility functions without requiring Earth Engine access.
"""

import pandas as pd
import pytest


@pytest.fixture
def sample_coordinate_data():
    """Sample coordinate data for testing coordinate cleaning."""
    return [
        ("45.123", 45.123),
        ("45.123°N", 45.123),
        ("45.123°", 45.123),
        ("45,123", 45.123),  # European decimal separator
        ("-122.456", -122.456),
        ("-122.456°W", -122.456),
        ("invalid", None),
        ("", None),
        (None, None),
    ]


@pytest.fixture
def sample_date_data():
    """Sample date data for testing date parsing."""
    return [
        ("2020-07-15", "2020-07-15"),
        ("2020/07/15", "2020-07-15"),
        ("07/15/2020", "2020-07-15"),
        ("15-07-2020", "2020-07-15"),
        ("2020-7-15", "2020-07-15"),
        ("invalid", None),
        ("", None),
        (None, None),
    ]


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing file parsing."""
    return pd.DataFrame(
        {
            "latitude": [45.123, 45.456, 45.789],
            "longitude": [-122.123, -122.456, -122.789],
            "date": ["2020-07-01", "2020-07-02", "2020-07-03"],
            "name": ["Dam1", "Dam2", "Dam3"],
        }
    )


@pytest.fixture
def sample_geojson_data():
    """Sample GeoJSON data for testing file parsing."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-122.123, 45.123]},
                "properties": {"name": "Dam1", "date": "2020-07-01"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-122.456, 45.456]},
                "properties": {"name": "Dam2", "date": "2020-07-02"},
            },
        ],
    }


@pytest.fixture
def sample_ndvi_data():
    """Sample data for testing NDVI calculations."""
    return {
        "nir_values": [0.8, 0.7, 0.6, 0.5],
        "red_values": [0.1, 0.2, 0.3, 0.4],
        "expected_ndvi": [0.777, 0.555, 0.333, 0.111],  # Approximate values
    }


@pytest.fixture
def sample_elevation_data():
    """Sample elevation data for testing elevation masking."""
    return {
        "center_elevation": 100.0,
        "test_elevations": [97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0],
        "upper_threshold": 3.0,
        "lower_threshold": 5.0,
        "expected_mask": [True, True, True, True, True, True, True, False],  # Within thresholds
    }


@pytest.fixture
def sample_batch_data():
    """Sample data for testing batch processing."""
    return {
        "total_items": 25,
        "batch_sizes": [5, 10, 15],
        "expected_batches": {
            5: 5,  # 25 items / 5 per batch = 5 batches
            10: 3,  # 25 items / 10 per batch = 3 batches
            15: 2,  # 25 items / 15 per batch = 2 batches
        },
    }


@pytest.fixture
def sample_state_data():
    """Sample state data for testing state abbreviations."""
    return {
        "full_names": ["California", "Oregon", "Washington", "Invalid State"],
        "abbreviations": ["CA", "OR", "WA", None],
    }


@pytest.fixture
def sample_scientific_data():
    """Sample scientific data for testing calculations."""
    return {
        "lst_celsius": [15.5, 20.2, 25.8, 30.1],
        "lst_kelvin": [288.65, 293.35, 298.95, 303.25],
        "ndwi_values": [0.2, 0.4, 0.6, 0.8],
        "cloud_coverage": [5.0, 15.0, 25.0, 35.0],
        "valid_images": [True, True, True, False],  # <20% cloud coverage
    }
