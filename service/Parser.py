import csv
import json

import dateutil
import ee
import pandas as pd
import streamlit as st

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def set_id_year_property(feature):
    try:
        # Ensure feature has an ID; default to "unknown" if not present
        feature_id = feature.id() if feature.id() else "unknown"

        # Convert Earth Engine String to Python string for processing
        feature_id = feature_id.getInfo() if isinstance(feature_id, ee.ComputedObject) else feature_id

        # Extract the last two characters safely
        short_id = feature_id[-2:] if isinstance(feature_id, str) and len(feature_id) >= 2 else "NA"

        # Safely get the year from the date property
        date = feature.get("date")
        year = ee.Date(date).get("year").getInfo() if date else None

        # Add the new properties
        return feature.set("id_property", feature_id).set("year", year).set("DamID", short_id)
    except Exception as e:
        st.error(f"An error occurred during standardization: {e}")
        return feature  # Return the original feature if an error occurs


# TODO: Add a function to easily upload points to Earth Engine
# The format is slightly different in Jupyter notebook because it doesn't deal with streamlit syntax


def clean_coordinate(value):
    """Cleans and converts a coordinate value into a valid float."""
    try:
        value = str(value).strip().replace("°", "").replace(",", ".")
        value = value.replace("N", "").replace("S", "").replace("E", "").replace("W", "")
        return float(value)
    except ValueError:
        return None  # Return None if the value cannot be converted


def parse_date(value, date_format):
    """Parses a date value into a standardized YYYY-MM-DD format."""
    try:
        if date_format == "Auto Detect":
            return dateutil.parser.parse(str(value)).strftime("%Y-%m-%d")
        elif date_format == "Unix Timestamp":
            return pd.to_datetime(int(value), unit="s").strftime("%Y-%m-%d")
        else:
            return pd.to_datetime(value, format=date_format).strftime("%Y-%m-%d")
    except Exception:
        return None  # Return None if the date cannot be parsed


def _process_csv_file(file, widget_prefix, point_type):
    """Extract CSV processing logic into shared function."""
    file.seek(0)

    # Let the user select a delimiter
    delimiter_display = {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tab (\\t)"}
    delimiter_key = st.selectbox(
        "Select delimiter used in CSV:",
        list(delimiter_display.values()),
        index=0,
        key=f"{widget_prefix}_{point_type}_delimiter_selectbox",
    )
    delimiter = [k for k, v in delimiter_display.items() if v == delimiter_key][0]

    # Read a sample for header detection using csv.Sniffer
    sample = file.read(1024)
    try:
        sample_str = sample.decode("utf-8")
    except AttributeError:
        sample_str = sample  # already a string
    sniffer = csv.Sniffer()
    has_header = sniffer.has_header(sample_str)
    file.seek(0)  # Reset pointer

    # Read the CSV with or without headers
    if has_header:
        df = pd.read_csv(file, delimiter=delimiter, header=0, encoding="utf-8")
    else:
        df = pd.read_csv(file, delimiter=delimiter, header=None, encoding="utf-8")
        df.columns = [f"column{i}" for i in range(len(df.columns))]

    st.write("**Preview of the uploaded file:**")
    st.dataframe(df.head(5))

    return df


def _get_coordinate_columns(df, widget_prefix, point_type):
    """Extract coordinate column selection logic."""
    # Auto-select Latitude and Longitude columns (case-insensitive)
    columns_lower = [col.lower() for col in df.columns]
    if "longitude" in columns_lower:
        default_longitude = list(df.columns).index(df.columns[columns_lower.index("longitude")])
    else:
        default_longitude = 0

    if "latitude" in columns_lower:
        default_latitude = list(df.columns).index(df.columns[columns_lower.index("latitude")])
    else:
        default_latitude = 1 if len(df.columns) > 1 else 0

    longitude_col = st.selectbox(
        "Select the **Longitude** column:",
        options=df.columns,
        index=default_longitude,
        key=f"{widget_prefix}_{point_type}_longitude_selectbox",
    )
    latitude_col = st.selectbox(
        "Select the **Latitude** column:",
        options=df.columns,
        index=default_latitude,
        key=f"{widget_prefix}_{point_type}_latitude_selectbox",
    )

    return longitude_col, latitude_col


def _get_date_for_processing(date_source, inherited_date, widget_prefix, point_type, show_et_warning):
    """Handle date selection/inheritance logic."""
    if date_source == "user_selection":
        # Year selection & default prompt
        selected_year = st.selectbox(
            "Select a year:", list(range(2017, 2025)), index=3, key=f"{widget_prefix}_{point_type}_year_selectbox"
        )
        selected_date = f"{selected_year}-07-01"

        if show_et_warning and (selected_year < 2020 or selected_year > 2025):
            st.warning("You may proceed to next steps, but ET data may not be available for the selected year.")

        return selected_date
    else:
        # Use inherited date from dam data
        if inherited_date is None:
            if "selected_date" in st.session_state:
                inherited_date = st.session_state.selected_date
            elif "Dam_data" in st.session_state and st.session_state.Dam_data:
                # Try to get date from the first dam point
                try:
                    first_feature = ee.Feature(st.session_state.Dam_data.first())
                    inherited_date = first_feature.get("date").getInfo()
                    if not inherited_date:
                        inherited_date = "2020-07-01"  # Default date
                except Exception:
                    inherited_date = "2020-07-01"  # Default date
            else:
                inherited_date = "2020-07-01"  # Default date
                st.warning("No dam data date found, using default date: 2020-07-01")

        return inherited_date


def _create_feature_collection_from_df(df, longitude_col, latitude_col, selected_date):
    """Create feature collection from DataFrame."""

    def standardize_feature(row):
        longitude = clean_coordinate(row[longitude_col])
        latitude = clean_coordinate(row[latitude_col])
        if longitude is None or latitude is None:
            return None
        properties = {"date": selected_date}
        return ee.Feature(ee.Geometry.Point([longitude, latitude]), properties)

    standardized_features = list(filter(None, df.apply(standardize_feature, axis=1).tolist()))
    feature_collection = ee.FeatureCollection(standardized_features)

    return feature_collection


def _process_geojson_file(file):
    """Extract GeoJSON processing logic."""
    file.seek(0)
    try:
        geojson = json.load(file)
    except json.JSONDecodeError:
        st.error("Invalid GeoJSON file format.")
        return None

    if "features" not in geojson or not isinstance(geojson["features"], list):
        st.error("Invalid GeoJSON format: missing 'features' key.")
        return None

    return geojson


def _create_feature_collection_from_geojson(geojson, selected_date, point_type):
    """Create feature collection from GeoJSON."""
    features = []
    for i, feature_obj in enumerate(geojson["features"]):
        try:
            geom = feature_obj.get("geometry")
            props = feature_obj.get("properties", {"id": i})
            props["date"] = selected_date  # Add the selected date to the properties
            features.append(ee.Feature(ee.Geometry(geom), props))
        except Exception as e:
            st.warning(f"Skipped feature {i} due to an error: {e}")

    feature_collection = ee.FeatureCollection(features)
    return feature_collection


def _handle_processing_error(e):
    """Extract error handling logic."""
    st.error("**File Processing Failed**")
    st.error(f"**Issue:** {str(e)}")
    st.info("**Common Solutions:**")
    st.info("• Ensure file is valid CSV or GeoJSON format")
    st.info("• Check file encoding (should be UTF-8)")
    st.info("• Verify file size is reasonable (<10MB)")
    st.info("• Remove any special characters or formatting")


def process_uploaded_points(
    file, widget_prefix="", date_source="user_selection", inherited_date=None, point_type="dam", show_et_warning=True
):
    """
    Common function to process uploaded CSV or GeoJSON files into Earth Engine FeatureCollection.

    Args:
        file: The uploaded file object
        widget_prefix: Prefix for Streamlit widgets to avoid conflicts
        date_source: "user_selection" or "inherited"
        inherited_date: Date to use when date_source is "inherited"
        point_type: "dam" or "non_dam" for appropriate messaging
        show_et_warning: Whether to show ET data availability warning

    Returns:
        ee.FeatureCollection or None if processing fails
    """
    if not file:
        return None

    try:
        if file.name.endswith(".csv"):
            df = _process_csv_file(file, widget_prefix, point_type)
            if df is None:
                return None

            longitude_col, latitude_col = _get_coordinate_columns(df, widget_prefix, point_type)
            selected_date = _get_date_for_processing(date_source, inherited_date, widget_prefix, point_type, show_et_warning)

            if st.button(
                f"Confirm and Process {point_type.title()} Data", key=f"{widget_prefix}_{point_type}_process_data_button"
            ):
                feature_collection = _create_feature_collection_from_df(df, longitude_col, latitude_col, selected_date)
                success_msg = (
                    "CSV successfully uploaded and standardized. Preview the data on the map below."
                    if point_type == "dam"
                    else f"{point_type.title()} points CSV successfully uploaded and converted."
                )
                st.success(success_msg)
                return feature_collection

        elif file.name.endswith(".geojson"):
            geojson = _process_geojson_file(file)
            if geojson is None:
                return None

            selected_date = _get_date_for_processing(date_source, inherited_date, widget_prefix, point_type, show_et_warning)

            if st.button(
                f"Confirm and Process {point_type.title()} GeoJSON",
                key=f"{widget_prefix}_{point_type}_geojson_process_button",
            ):
                feature_collection = _create_feature_collection_from_geojson(geojson, selected_date, point_type)
                success_msg = (
                    "GeoJSON successfully uploaded and converted."
                    if point_type == "dam"
                    else f"{point_type.title()} points GeoJSON successfully uploaded and converted."
                )
                st.success(success_msg)
                return feature_collection

        else:
            st.error("Unsupported file format. Please upload a CSV or GeoJSON file.")
            return None

    except Exception as e:
        _handle_processing_error(e)
        return None


# Refactored original functions for backward compatibility
def upload_points_to_ee(file, widget_prefix=""):
    """Upload dam points to Earth Engine with user date selection."""
    return process_uploaded_points(
        file=file, widget_prefix=widget_prefix, date_source="user_selection", point_type="dam", show_et_warning=True
    )


def upload_non_dam_points_to_ee(file, dam_date=None, widget_prefix=""):
    """
    Handles CSV and GeoJSON uploads for non-dam points, using the date from dam data.
    Args:
        file: The uploaded file (CSV or GeoJSON)
        dam_date: The date from dam data to be used for non-dam points
        widget_prefix: Prefix for streamlit widgets to avoid conflicts
    Returns:
        ee.FeatureCollection or None if processing fails
    """
    return process_uploaded_points(
        file=file,
        widget_prefix=widget_prefix,
        date_source="inherited",
        inherited_date=dam_date,
        point_type="non_dam",
        show_et_warning=False,
    )
