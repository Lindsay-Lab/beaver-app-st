"""
Constants Module

Centralized constants and configuration values to eliminate magic numbers
and duplicate data throughout the application.
"""

# State name to abbreviation mapping for NHD dataset access
STATE_ABBREVIATIONS = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

# Buffer and distance constants (in meters)
DEFAULT_BUFFER_RADIUS = 150
ELEVATION_BUFFER_RADIUS = 100
DEDUPLICATION_BUFFER_RADIUS = 10

# Elevation thresholds (in meters)
ELEVATION_THRESHOLD_UPPER = 3
ELEVATION_THRESHOLD_LOWER = 5
ELEVATION_THRESHOLD_RANGE = 10

# Earth Engine processing constants
DEFAULT_BATCH_SIZE = 10
LARGE_BATCH_SIZE = 30
CLOUD_COVERAGE_SCALE = 10
SENTINEL2_SCALE = 10
LANDSAT_SCALE = 30

# Earth Engine maxPixels constants
MAX_PIXELS_SMALL = 1e9
MAX_PIXELS_LARGE = 1e13

# Cloud coverage thresholds
MAX_CLOUD_COVERAGE = 20  # Maximum cloud coverage percentage
MIN_INTERSECTION_RATIO = 0.95  # Minimum intersection ratio for image overlap

# Date and time constants
DEFAULT_YEAR = 2020
DEFAULT_MONTH = 7
DEFAULT_DAY = 1
ET_DATA_START_YEAR = 2020
ET_DATA_END_YEAR = 2025

# Negative sampling constants
MIN_DISTANCE_FROM_DAMS = 200  # Minimum distance from dams in meters
NEGATIVE_SAMPLE_BUFFER = 130  # Buffer for negative sampling

# Visualization constants
PLOT_FIGURE_WIDTH = 12
PLOT_FIGURE_HEIGHT_SMALL = 18
PLOT_FIGURE_HEIGHT_LARGE = 20
MAP_WIDTH = 1200
MAP_HEIGHT = 700
