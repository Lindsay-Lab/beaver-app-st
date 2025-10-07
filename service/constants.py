"""
Constants and default values for the app.
"""


# pylint: disable=too-few-public-methods
class AppConstants:
    """simple container for constants and default values"""

    # Buffer settings
    DEFAULT_BUFFER_RADIUS = 150
    MIN_BUFFER_RADIUS = 1
    BUFFER_STEP = 1

    # Validation settings
    DEFAULT_MAX_DISTANCE = 50
    MIN_MAX_DISTANCE = 0
    DISTANCE_STEP = 10

    # Negative sampling
    DEFAULT_INNER_RADIUS = 300
    DEFAULT_OUTER_RADIUS = 500
    SAMPLING_SCALE = 10
    RADIUS_STEP = 50

    # Processing settings
    BATCH_SIZE = 30
    MAX_RETRIES = 3

    # UI settings
    MAP_WIDTH = 800
    MAP_HEIGHT = 600
    LARGE_MAP_WIDTH = 1200
    LARGE_MAP_HEIGHT = 700

    # Date formatting
    DEFAULT_DATE_SUFFIX = "-07-01"
    DATE_FORMAT = "YYYY"
    FORMATTED_DATE_FORMAT = "YYYYMMdd"

    # Session state defaults
    SESSION_DEFAULTS = {
        # Questionnaire state
        "questionnaire_shown": False,
        "survey_clicked": False,
        # Data collections
        "Positive_collection": None,
        "Dam_data": None,
        "Full_positive": None,
        "selected_waterway": None,
        "Merged_collection": None,
        "validation_results": None,
        "df_lst": None,
        "fig": None,
        # Configuration
        "buffer_radius": DEFAULT_BUFFER_RADIUS,
        # Boolean flags
        "validation_complete": False,
        "use_all_dams": True,
        "show_non_dam_section": False,
        "buffer_complete": False,
        "dataset_loaded": False,
        "buffers_created": False,
        "visualization_complete": False,
        # Workflow state
        "validation_step": "initial",
    }

    STATE_CODES = {
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
