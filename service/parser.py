"""
Utilities for parsing inputs into appropriate formats.
"""

import csv
import json
from io import StringIO

import ee
import pandas as pd
import streamlit as st

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def clean_coordinate(value):
    """Cleans and converts a coordinate value into a valid float."""
    try:
        value = str(value).strip().replace("°", "").replace(",", ".")
        value = value.replace("N", "").replace("S", "").replace("E", "").replace("W", "")
        return float(value)
    except ValueError:
        return None  # Return None if the value cannot be converted


def upload_points_to_ee(file: StringIO, widget_prefix:str="") -> ee.FeatureCollection | None:
    """
    Modified parser to include widget_prefix and autodetect header
    """
    if not file:
        return None

    try:
        if file.name.endswith(".csv"):
            file.seek(0)

            # Let the user select a delimiter
            delimiter_display = {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tab (\\t)"}
            delimiter_key = st.selectbox(
                "Select delimiter used in CSV:",
                list(delimiter_display.values()),
                index=0,
                key=f"{widget_prefix}_delimiter_selectbox",
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
                key=f"{widget_prefix}_longitude_selectbox",
            )
            latitude_col = st.selectbox(
                "Select the **Latitude** column:",
                options=df.columns,
                index=default_latitude,
                key=f"{widget_prefix}_latitude_selectbox",
            )

            # Year selection & default prompt
            selected_year = st.selectbox(
                "Select a year:", list(range(2017, 2025)), index=3, key=f"{widget_prefix}_year_selectbox"
            )
            selected_date = f"{selected_year}-07-01"

            if selected_year < 2020 or selected_year > 2025:
                st.warning("You may proceed to next steps, but ET data may not be available for the selected year.")

            if st.button("Confirm and Process Data", key=f"{widget_prefix}_process_data_button"):

                def standardize_feature(row):
                    longitude = clean_coordinate(row[longitude_col])
                    latitude = clean_coordinate(row[latitude_col])
                    if longitude is None or latitude is None:
                        return None
                    properties = {"date": selected_date}
                    return ee.Feature(ee.Geometry.Point([longitude, latitude]), properties)

                standardized_features = list(filter(None, df.apply(standardize_feature, axis=1).tolist()))
                feature_collection = ee.FeatureCollection(standardized_features)

                st.success("CSV successfully uploaded and standardized. Preview the data on the map below.")
                return feature_collection

        elif file.name.endswith(".geojson"):
            file.seek(0)
            try:
                geojson = json.load(file)
            except json.JSONDecodeError:
                st.error("Invalid GeoJSON file format.")
                return None

            if "features" not in geojson or not isinstance(geojson["features"], list):
                st.error("Invalid GeoJSON format: missing 'features' key.")
                return None

            # Year selection & default prompt for GeoJSON
            selected_year = st.selectbox(
                "Select a year:", list(range(2017, 2025)), index=3, key=f"{widget_prefix}_geojson_year_selectbox"
            )
            selected_date = f"{selected_year}-07-01"

            if selected_year < 2020 or selected_year > 2025:
                st.warning("You may proceed to next steps, but ET data may not be available for the selected year.")

            if st.button("Confirm and Process GeoJSON", key=f"{widget_prefix}_geojson_process_button"):
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
                st.success("GeoJSON successfully uploaded and converted.")
                return feature_collection

        else:
            st.error("Unsupported file format. Please upload a CSV or GeoJSON file.")
            return None

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
        return None


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
    if not file:
        return None

    # If dam_date is not provided, try to get it from session_state
    if dam_date is None:
        if "selected_date" in st.session_state:
            dam_date = st.session_state.selected_date
        elif "Dam_data" in st.session_state and st.session_state.Dam_data:
            # Try to get date from the first dam point
            try:
                first_feature = ee.Feature(st.session_state.Dam_data.first())
                dam_date = first_feature.get("date").getInfo()
                if not dam_date:
                    dam_date = "2020-07-01"  # Default date
            except:
                dam_date = "2020-07-01"  # Default date
        else:
            dam_date = "2020-07-01"  # Default date
            st.warning("No dam data date found, using default date: 2020-07-01")

    try:
        if file.name.endswith(".csv"):
            file.seek(0)

            # Let the user select a delimiter
            delimiter_display = {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tab (\\t)"}
            delimiter_key = st.selectbox(
                "Select delimiter used in CSV:",
                list(delimiter_display.values()),
                index=0,
                key=f"{widget_prefix}_nondam_delimiter_selectbox",
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
                key=f"{widget_prefix}_nondam_longitude_selectbox",
            )
            latitude_col = st.selectbox(
                "Select the **Latitude** column:",
                options=df.columns,
                index=default_latitude,
                key=f"{widget_prefix}_nondam_latitude_selectbox",
            )

            # Display the date that will be used

            if st.button("Confirm and Process Data", key=f"{widget_prefix}_nondam_process_data_button"):

                def standardize_feature(row):
                    longitude = clean_coordinate(row[longitude_col])
                    latitude = clean_coordinate(row[latitude_col])
                    if longitude is None or latitude is None:
                        return None
                    properties = {"date": dam_date}
                    return ee.Feature(ee.Geometry.Point([longitude, latitude]), properties)

                standardized_features = list(filter(None, df.apply(standardize_feature, axis=1).tolist()))
                feature_collection = ee.FeatureCollection(standardized_features)

                return feature_collection

        elif file.name.endswith(".geojson"):
            file.seek(0)
            try:
                geojson = json.load(file)
            except json.JSONDecodeError:
                st.error("Invalid GeoJSON file format.")
                return None

            if "features" not in geojson or not isinstance(geojson["features"], list):
                st.error("Invalid GeoJSON format: missing 'features' key.")
                return None

            # Display the date that will be used

            if st.button("Confirm and Process GeoJSON", key=f"{widget_prefix}_nondam_geojson_process_button"):
                features = []
                for i, feature_obj in enumerate(geojson["features"]):
                    try:
                        geom = feature_obj.get("geometry")
                        props = feature_obj.get("properties", {"id": i})
                        props["date"] = dam_date  # Use the dam date for all features
                        features.append(ee.Feature(ee.Geometry(geom), props))
                    except Exception as e:
                        st.warning(f"Skipped feature {i} due to an error: {e}")

                feature_collection = ee.FeatureCollection(features)
                st.success("Non-dam points GeoJSON successfully uploaded and converted.")
                return feature_collection

        else:
            st.error("Unsupported file format. Please upload a CSV or GeoJSON file.")
            return None

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
        return None
