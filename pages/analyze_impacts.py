"""Primary page for analyzing dam impacts"""

import io
import math

import ee
import geemap.foliumap as geemap
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from service.constants import AppConstants
from service.earth_engine_auth import initialize_earth_engine
from service.error_handling import (
    handle_processing_errors,
    safe_processing,
    display_validation_error,
    display_success_message,
    display_warning_with_options,
    handle_file_processing_error, safe_expander,
)
from service.load_datasets import load_nhd_collections
from service.negative_sampling import prepare_hydro, sample_negative_points
from service.parser import extract_coordinates_df, upload_non_dam_points_to_ee, upload_points_to_ee, \
    upload_waterway_to_ee
from service.session_state import SessionStateManager, check_prerequisites, show_prerequisite_error
from service.validation import (
    check_waterway_intersection,
    generate_validation_report,
    resolve_validation_summary,
    validate_dam_waterway_distance,
    visualize_validation_results,
)

from service.visualize_trends import (
    s2_export_for_visual,
    add_landsat_lst_et,
    compute_all_metrics_lst_et,
    add_elevation_band,
)


# Initialize Earth Engine and session state
initialize_earth_engine()
SessionStateManager.initialize()


def main():
    """Main application function"""
    st.title("Analyzing the Impact of Beaver Dams")
    st.warning(
        "Please note that the Evapotranspiration data is not available for the eastern half of the US "
        "or for certain years. Learn more on the OpenET website: [Link](https://etdata.org/)."
    )

    # Render each step in expandable sections
    with safe_expander("Step 1: Upload Dam Locations", expanded=not SessionStateManager.is_step_complete(1)):
        render_step1()

    with safe_expander(
        "Step 2: Select Waterway",
        expanded=SessionStateManager.is_step_complete(1) and not SessionStateManager.is_step_complete(2),
    ):
        render_step2()

    with safe_expander(
        "Step 3: Validate Dam Locations",
        expanded=SessionStateManager.is_step_complete(2) and not SessionStateManager.is_step_complete(3),
    ):
        render_step3()

    with safe_expander(
        "Step 4: Upload or Generate Non-Dam Locations",
        expanded=SessionStateManager.is_step_complete(3) and not SessionStateManager.is_step_complete(4),
    ):
        render_step4()

    with safe_expander(
        "Step 5: Create Buffers",
        expanded=SessionStateManager.is_step_complete(4) and not SessionStateManager.is_step_complete(5),
    ):
        render_step5()

    with safe_expander("Step 6: Visualize Trends", expanded=SessionStateManager.is_step_complete(5)):
        render_step6()


@handle_processing_errors("file upload processing")
def process_dam_upload(uploaded_file):
    """Process uploaded dam location file"""
    feature_collection = upload_points_to_ee(uploaded_file, widget_prefix="Dam")
    if feature_collection:
        if feature_collection.size().getInfo() < 2:
            st.warning(
                "Please upload more than one dam location — the comparative analysis "
                "needs at least two."
            )
            return None
        SessionStateManager.set_multiple(
            {
                "Positive_collection": feature_collection,
                "Full_positive": feature_collection,
            }
        )
        SessionStateManager.complete_step(1)
        return feature_collection
    return None


def render_step1():
    """Step 1: Upload Dam Locations"""
    st.header("Step 1: Upload Dam Locations")

    uploaded_file = st.file_uploader("Choose a CSV or GeoJSON file", type=["csv", "geojson"], key="Dam_file_uploader")

    if uploaded_file:
        with safe_processing("Processing uploaded file", show_spinner=True):
            feature_collection = process_dam_upload(uploaded_file)

            if feature_collection:
                display_success_message("Dam locations uploaded successfully!")

                # Display data preview
                st.subheader("Data Preview")
                st.text("Points may take a few seconds to upload")

                preview_map = geemap.Map()
                preview_map.add_basemap("SATELLITE")
                preview_map.addLayer(feature_collection, {"color": "blue"}, "Dam Locations")
                preview_map.centerObject(feature_collection)
                preview_map.to_streamlit(width=AppConstants.MAP_WIDTH, height=AppConstants.MAP_HEIGHT)


@handle_processing_errors("waterway dataset loading")
def load_waterway_data():
    """Load waterway dataset based on dam locations"""
    full_positive = SessionStateManager.get("Full_positive")
    if not full_positive:
        return None

    # Get dam bounds and find states
    positive_dam_bounds = full_positive.geometry().bounds()
    states_dataset = ee.FeatureCollection("TIGER/2018/States")
    states_with_dams = states_dataset.filterBounds(positive_dam_bounds)

    SessionStateManager.set("Positive_dam_state", states_with_dams)
    state_names = states_with_dams.aggregate_array("NAME").getInfo()

    if not state_names:
        display_validation_error(
            "No states found within the dam data bounds.",
            ["Check that your dam coordinates are valid", "Ensure coordinates are in the correct format"],
        )
        return None

    st.write(f"States within dam data bounds: {state_names}")

    # Load NHD collections
    nhd_collections = load_nhd_collections(state_names)

    if nhd_collections:
        merged_nhd = ee.FeatureCollection(nhd_collections).flatten()
        SessionStateManager.set_multiple(
            {"selected_waterway": merged_nhd, "dataset_loaded": True}
        )
        st.success(
            "Automatically loaded NHD dataset. If you want to use a different dataset, "
            "you can upload your own or use the alternative dataset."
        )
        return merged_nhd

    display_validation_error(
        "No NHD datasets found for the selected states.",
        ["Try using the alternative waterway dataset", "Check that your dam locations are in supported areas"],
    )
    return None


def render_alternative_waterway_options():
    """Render alternative waterway dataset options"""
    st.subheader("To use a different waterway map instead:")

    upload_own_checkbox = st.checkbox("Upload Custom Waterway File in Geojson Format")
    preuploaded_checkbox = st.checkbox("Use Custom Waterway Map Uploaded to GEE")
    choose_other_checkbox = st.checkbox("Use Alternative Waterway Map")

    if upload_own_checkbox:
        uploaded_file = st.file_uploader("Choose a GeoJSON file", type=["geojson", "json"],
                                         key="waterway_file_uploader")
        # asset_id = st.text_input("Upload a waterway file in geojson format:")
        if st.button("Upload Custom Dataset"):
            with safe_processing("Loading custom dataset"):
                waterway_own = upload_waterway_to_ee(uploaded_file)
                SessionStateManager.set_multiple({"selected_waterway": waterway_own})
                SessionStateManager.complete_step(2)
                display_success_message("Dataset successfully uploaded.")

    if preuploaded_checkbox:
        asset_id = st.text_input("Enter GEE Asset Table ID (e.g., projects/your-project/assets/Hydro/MA_Hydro_arc):")
        if st.button("Load Custom Dataset"):
            with safe_processing("Loading custom dataset"):
                waterway_own = ee.FeatureCollection(asset_id)
                SessionStateManager.set_multiple({"selected_waterway": waterway_own})
                SessionStateManager.complete_step(2)
                display_success_message("Custom dataset successfully loaded.")

    if choose_other_checkbox:
        dataset_option = st.selectbox("Select alternative map:", ["WWF Free Flowing Rivers"])
        if st.button("Load Alternative Map"):
            with safe_processing("Loading alternative dataset"):
                if dataset_option == "WWF Free Flowing Rivers":
                    states_with_dams = SessionStateManager.get("Positive_dam_state")
                    wwf_dataset = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers")
                    clipped_wwf = wwf_dataset.filterBounds(states_with_dams)
                    SessionStateManager.set("selected_waterway", clipped_wwf)
                    SessionStateManager.complete_step(2)
                    display_success_message("WWF dataset successfully loaded.")


def render_step2():
    """Step 2: Select Waterway"""
    st.header("Step 2: Select Waterway")

    # Check prerequisites
    if not check_prerequisites([1]):
        show_prerequisite_error("Step 2", [1])
        return

    with safe_processing("Loading waterway data"):
        waterway = load_waterway_data()

    if waterway:
        # Display map
        waterway_map = geemap.Map()
        waterway_map.add_basemap("SATELLITE")
        waterway_map.centerObject(SessionStateManager.get("Full_positive"))
        waterway_map.addLayer(waterway, {"color": "blue"}, "Selected Waterway")
        waterway_map.addLayer(SessionStateManager.get("Full_positive"), {"color": "red"}, "Dams")
        waterway_map.to_streamlit(width=AppConstants.LARGE_MAP_WIDTH, height=AppConstants.LARGE_MAP_HEIGHT)
        st.subheader("Use the automatically loaded NHD default waterway map?")
        use_default_checkbox = st.checkbox("Yes. Use the automatically loaded NHD default waterway map.")
        if use_default_checkbox:
            SessionStateManager.complete_step(2)

    render_alternative_waterway_options()


@handle_processing_errors("dam location validation")
def perform_dam_validation(max_distance):
    """Perform dam location validation"""
    error_msg = SessionStateManager.validate_earth_engine_data(
        {"Full_positive": "Dam locations", "selected_waterway": "Waterway data"}
    )

    if error_msg:
        display_validation_error(error_msg)
        return None

    full_positive = SessionStateManager.get("Full_positive")
    waterway = SessionStateManager.get_waterway_data()

    # Perform distance validation
    distance_validation = validate_dam_waterway_distance(full_positive, waterway, max_distance)

    # Perform intersection validation
    _ = check_waterway_intersection(full_positive, waterway)

    # Combine validation results
    validation_results = {
        "valid_dams": distance_validation["valid_dams"],
        "invalid_dams": distance_validation["invalid_dams"],
        "invalid_dams_info": distance_validation["invalid_dams_info"],
        "total_dams": full_positive.size(),
        "valid_count": distance_validation["valid_count"],
        "invalid_count": distance_validation["invalid_count"],
    }

    return validation_results


def handle_validation_results(validation_results, summary=None):
    """Handle validation results and user decisions"""
    # Reuse the already-resolved summary when available. This runs on every rerun
    # while the options are displayed, and each .getInfo() would otherwise re-run the
    # whole dam-to-waterway distance computation.
    if summary is None:
        summary = SessionStateManager.get("validation_summary")
    if summary is None:
        summary = resolve_validation_summary(validation_results)

    valid_count = summary["valid_count"]
    invalid_count = summary["invalid_count"]

    if valid_count == 0:
        display_validation_error(
            "No valid dam locations found. All dams failed validation.",
            ["Check your dam locations and waterway data", "Adjust the maximum distance parameter"],
        )
        return

    if invalid_count > 0:
        options = display_warning_with_options(
            "Some dam locations have been identified as potentially invalid. "
            "Please review the validation report and map above. "
            "You can continue with all dams or only use the valid dams.",
            {"Continue with all dams": "use_all_dams_btn", "Only use valid dams": "use_valid_dams_btn"},
        )

        if options.get("use_all_dams_btn"):
            SessionStateManager.set_multiple(
                {
                    "validation_complete": True,
                    "use_all_dams": True,
                    "Dam_data": SessionStateManager.get("Full_positive"),
                    "show_non_dam_section": True,
                    "validation_step": "completed",
                }
            )
            display_success_message("Selected to continue with all dams.")

        elif options.get("use_valid_dams_btn"):
            valid_dams = validation_results["valid_dams"]
            SessionStateManager.set_multiple(
                {
                    "Full_positive": valid_dams,
                    "validation_step": "completed",
                    "validation_complete": True,
                    "use_all_dams": False,
                    "Dam_data": valid_dams,
                    "show_non_dam_section": True,
                }
            )
            display_success_message(f"Successfully filtered to {valid_count} valid dams.")
    else:
        SessionStateManager.set_multiple(
            {
                "validation_complete": True,
                "use_all_dams": True,
                "Dam_data": SessionStateManager.get("Full_positive"),
                "show_non_dam_section": True,
                "validation_step": "completed",
            }
        )
        display_success_message("All dams are valid.")

    SessionStateManager.complete_step(3)


def render_step3():
    """Step 3: Validate Dam Locations"""
    st.header("Step 3: Validate Dam Locations")

    # Check prerequisites; allow user to proceed so long as the NHD dataset is loaded
    if not check_prerequisites([2]) and not SessionStateManager.get("dataset_loaded"):
        show_prerequisite_error("Step 3", [2])
        return

    # Only show validation section if validation is not complete
    if not SessionStateManager.get("validation_complete", False):
        max_distance = st.number_input(
            "Maximum allowed distance from waterway (meters):",
            min_value=AppConstants.MIN_MAX_DISTANCE,
            value=AppConstants.DEFAULT_MAX_DISTANCE,
            step=AppConstants.DISTANCE_STEP,
            key="max_distance_input",
        )

        if st.button("Validate Dam Locations"):
            with safe_processing("Validating dam locations"):
                validation_results = perform_dam_validation(max_distance)

                if validation_results:
                    # Resolve the counts once here; the report, the options handler and
                    # every subsequent rerun all read from this cached summary.
                    summary = resolve_validation_summary(validation_results)

                    SessionStateManager.set_multiple(
                        {
                            "validation_results": validation_results,
                            "validation_summary": summary,
                            "validation_step": "show_options",
                        }
                    )

                    st.subheader("Validation Report")
                    st.text(generate_validation_report(validation_results, summary))

                    # Display validation map
                    st.subheader("Validation Map")
                    validation_map = visualize_validation_results(
                        dam_collection=SessionStateManager.get("Full_positive"),
                        waterway_fc=SessionStateManager.get_waterway_data(),
                        validation_results=validation_results,
                    )
                    validation_map.to_streamlit(
                        width=AppConstants.LARGE_MAP_WIDTH, height=AppConstants.LARGE_MAP_HEIGHT
                    )

    # Show options after validation is complete
    if SessionStateManager.get("validation_step") == "show_options":
        # If step 2 not completed, but NHD dataset is loaded, mark step 2 as completed.
        # This is possible in the case when the NHD dataset is loaded, the user does not choose an alternative, and
        #   proceeds without explicitly checking the "Yes. Use the automatically loaded NHD default..." checkbox.
        if not check_prerequisites([2]) and SessionStateManager.get("dataset_loaded"):
            SessionStateManager.complete_step(2)
        validation_results = SessionStateManager.get("validation_results")
        if validation_results:
            handle_validation_results(validation_results)


@handle_processing_errors("non-dam data processing")
def process_non_dam_upload(uploaded_file):
    """Process uploaded non-dam data"""
    negative_feature_collection = upload_non_dam_points_to_ee(uploaded_file, widget_prefix="NonDam")

    if not negative_feature_collection:
        return None

    # Process negative sample data
    fc = negative_feature_collection
    features_list = fc.toList(fc.size())
    indices = ee.List.sequence(0, fc.size().subtract(1))

    def set_id_negatives2(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(features_list.get(idx))
        date = feature.get("date")
        if not date:
            first_pos = SessionStateManager.get("Positive_collection").first()
            date = first_pos.get("date")
        return (
            feature.set("id_property", ee.String("N").cat(idx.add(1).int().format()))
            .set("date", date)
            .set("Dam", "negative")
        )

    neg_points_id = ee.FeatureCollection(indices.map(set_id_negatives2))

    # Process positive samples
    pos_collection = (
        SessionStateManager.get("Dam_data")
        if not SessionStateManager.get("use_all_dams")
        else SessionStateManager.get("Positive_collection")
    )
    pos_collection = pos_collection.map(lambda feature: feature.set("Dam", "positive"))

    pos_features_list = pos_collection.toList(pos_collection.size())
    pos_indices = ee.List.sequence(0, pos_collection.size().subtract(1))

    def set_id_positives(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(pos_features_list.get(idx))
        date = feature.get("date")
        if not date:
            first_pos = SessionStateManager.get("Positive_collection").first()
            date = first_pos.get("date")
        return feature.set("id_property", ee.String("P").cat(idx.add(1).int().format())).set("date", date)

    positive_dam_id = ee.FeatureCollection(pos_indices.map(set_id_positives))
    merged_collection = positive_dam_id.merge(neg_points_id)

    SessionStateManager.set_multiple(
        {
            "Merged_collection": merged_collection,
            "Negative_upload_collection": negative_feature_collection,
            "Full_negative": negative_feature_collection,
            "buffer_complete": True,
        }
    )
    SessionStateManager.complete_step(4)

    return {
        "negative_points": neg_points_id,
        "positive_points": positive_dam_id,
        "merged_collection": merged_collection,
    }


@handle_processing_errors("negative point generation")
def generate_negative_points(inner_radius, outer_radius, sampling_scale):
    """Generate negative points using specified parameters"""
    # Validate required data
    error_msg = SessionStateManager.validate_earth_engine_data(
        {"Positive_collection": "Dam locations", "selected_waterway": "Waterway data"}
    )

    if error_msg:
        display_validation_error(error_msg)
        return None

    # Get positive dams
    positive_dams_fc = (
        SessionStateManager.get("Dam_data")
        if not SessionStateManager.get("use_all_dams")
        else SessionStateManager.get("Positive_collection")
    )

    if positive_dams_fc.size().getInfo() == 0:
        display_validation_error(
            "No valid dam data found.",
            ["Check your data and try again", "Ensure previous steps completed successfully"],
        )
        return None

    # Get bounds and clip waterway
    positive_bounds = positive_dams_fc.geometry().bounds()
    bounds_area = positive_bounds.area(1).getInfo()

    if bounds_area == 0:
        display_validation_error("No valid dam locations found.")
        return None

    waterway_fc = SessionStateManager.get("selected_waterway").filterBounds(positive_bounds)

    if waterway_fc.size().getInfo() == 0:
        display_validation_error(
            "No waterway data found within the dam locations area.",
            ["Check your waterway selection", "Verify dam locations are correct"],
        )
        return None

    # Prepare hydro raster and generate negative points
    hydro_raster = prepare_hydro(waterway_fc)
    negative_points = sample_negative_points(positive_dams_fc, hydro_raster, inner_radius, outer_radius, sampling_scale)

    # Resolve the sampling graph once. Left lazy, the paint -> focal_max ->
    # stratifiedSample chain is re-evaluated by every consumer, including each map
    # tile request, whose compute budget is far tighter than a plain getInfo. On
    # larger inputs that surfaces as "Computation timed out" when drawing the layer.
    sampled = negative_points.getInfo()

    if not sampled.get("features"):
        display_validation_error(
            "No negative points were generated.",
            ["Try adjusting the radius parameters", "Check that there's sufficient area for sampling"],
        )
        return None

    # Rebuild from raw coordinates: getInfo emits a 'geodesic' key that Earth
    # Engine's own Geometry constructor rejects, so the GeoJSON cannot be fed back
    # in as-is.
    negative_points = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point(feature["geometry"]["coordinates"]), feature.get("properties") or {})
            for feature in sampled["features"]
        ]
    )

    # Set date for negative points
    first_pos = positive_dams_fc.first()
    date = ee.Date(first_pos.get("date"))
    year_string = date.format("YYYY")
    full_date = ee.String(year_string).cat("-07-01")

    negative_points = negative_points.map(lambda feature: feature.set("Dam", "negative").set("date", full_date))

    # Process negative points with IDs
    fc = negative_points
    features_list = fc.toList(fc.size())
    indices = ee.List.sequence(0, fc.size().subtract(1))

    def set_id_negatives2(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(features_list.get(idx))
        return feature.set("id_property", ee.String("N").cat(idx.add(1).int().format()))

    neg_points_id = ee.FeatureCollection(indices.map(set_id_negatives2))

    # Process positive points with IDs
    pos_collection = positive_dams_fc.map(lambda feature: feature.set("Dam", "positive"))
    pos_features_list = pos_collection.toList(pos_collection.size())
    pos_indices = ee.List.sequence(0, pos_collection.size().subtract(1))

    def set_id_positives(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(pos_features_list.get(idx))
        return feature.set("id_property", ee.String("P").cat(idx.add(1).int().format()))

    positive_dam_id = ee.FeatureCollection(pos_indices.map(set_id_positives))
    merged_collection = positive_dam_id.merge(neg_points_id)

    SessionStateManager.set_multiple({"Merged_collection": merged_collection, "buffer_complete": True})
    SessionStateManager.complete_step(4)

    return {
        "negative_points": neg_points_id,
        "positive_points": positive_dam_id,
        "merged_collection": merged_collection,
    }


def render_step4():
    """Step 4: Upload or Generate Non-Dam Locations"""
    st.header("Step 4: Upload or Generate Non-Dam Locations")

    # Check prerequisites
    if not check_prerequisites([3]):
        show_prerequisite_error("Step 4", [3])
        return

    if not SessionStateManager.get("validation_complete", False):
        display_validation_error("Please complete the validation step first.")
        return

    if not SessionStateManager.get("show_non_dam_section", False):
        display_validation_error("Please complete the validation step first.")
        return

    # Display current dam usage status
    if SessionStateManager.get("use_all_dams"):
        st.info("Using all dam locations for analysis")
    else:
        st.info("Using only valid dam locations for analysis")

    upload_negatives_checkbox = st.checkbox("Upload Non-Dam Dataset (must be on a waterbody)")
    generate_negatives_checkbox = st.checkbox("Generate Non-Dam Locations")

    if upload_negatives_checkbox:
        uploaded_negatives = st.file_uploader(
            "Upload Non-Dam Dataset (CSV or GeoJSON)", type=["csv", "geojson"], key="negative_file_uploader"
        )

        if uploaded_negatives:
            with safe_processing("Processing uploaded non-dam data"):
                try:
                    result = process_non_dam_upload(uploaded_negatives)
                    if result:
                        display_success_message("Non-dam locations uploaded successfully!")

                        # Display data preview
                        st.subheader("Data Preview")
                        preview_map = geemap.Map()
                        preview_map.add_basemap("SATELLITE")
                        preview_map.addLayer(result["negative_points"], {"color": "red"}, "Non-dam locations")
                        preview_map.addLayer(result["positive_points"], {"color": "blue"}, "Dam locations")
                        preview_map.centerObject(result["merged_collection"])
                        preview_map.to_streamlit(width=AppConstants.MAP_WIDTH, height=AppConstants.MAP_HEIGHT)
                except Exception as e:
                    handle_file_processing_error(uploaded_negatives.name, e)

    if generate_negatives_checkbox:
        st.subheader("Specify the parameters for negative point generation:")
        st.image("assets/Negative_sampling_image.png")

        inner_radius = st.number_input(
            "Inner Radius (meters)",
            value=AppConstants.DEFAULT_INNER_RADIUS,
            min_value=0,
            step=AppConstants.RADIUS_STEP,
            key="inner_radius_input",
        )
        outer_radius = st.number_input(
            "Outer Radius (meters)",
            value=AppConstants.DEFAULT_OUTER_RADIUS,
            min_value=0,
            step=AppConstants.RADIUS_STEP,
            key="outer_radius_input",
        )
        sampling_scale = AppConstants.SAMPLING_SCALE

        if st.button("Generate Negative Points"):
            with safe_processing("Generating negative points"):
                result = generate_negative_points(inner_radius, outer_radius, sampling_scale)

                if result:
                    display_success_message("Negative points generated successfully!")

                    # Create and display the map
                    negative_points_map = geemap.Map()
                    negative_points_map.add_basemap("SATELLITE")
                    negative_points_map.addLayer(result["negative_points"], {"color": "red", "width": 2}, "Negative")
                    negative_points_map.addLayer(result["positive_points"], {"color": "blue"}, "Positive")
                    negative_points_map.centerObject(result["merged_collection"])
                    negative_points_map.to_streamlit(
                        width=AppConstants.LARGE_MAP_WIDTH, height=AppConstants.LARGE_MAP_HEIGHT
                    )


def buffer_merged_points(merged_collection, buffer_radius):
    """Buffer each point and standardize its date for the analysis pipeline"""

    def add_dam_buffer_and_standardize_date(feature):
        dam_status = feature.get("Dam")
        date = feature.get("date")

        if not date:
            date = feature.get("Survey_Date")
            if not date:
                first_pos = SessionStateManager.get("Positive_collection").first()
                date = first_pos.get("date")

        standardized_date = ee.Date(date)
        formatted_date = standardized_date.format("YYYYMMdd")

        # Create buffered geometry
        buffered_geometry = feature.geometry().buffer(buffer_radius)

        return ee.Feature(buffered_geometry).set(
            {
                "Dam": dam_status,
                "Survey_Date": standardized_date,
                "Damdate": ee.String("DamDate_").cat(formatted_date),
                "Point_geo": feature.geometry(),
                "id_property": feature.get("id_property"),
            }
        )

    buffered_collection = merged_collection.map(add_dam_buffer_and_standardize_date)
    return buffered_collection.select(["id_property", "Dam", "Survey_Date", "Damdate", "Point_geo"])


@handle_processing_errors("buffer creation")
def create_buffers(buffer_radius):
    """Create buffers around merged collection points"""
    merged_collection = SessionStateManager.get("Merged_collection")
    if not merged_collection:
        display_validation_error("No merged data found. Please complete Step 4 first.")
        return None

    dam_data = buffer_merged_points(merged_collection, buffer_radius)

    SessionStateManager.set_multiple({"Dam_data": dam_data, "buffers_created": True})

    return dam_data


def render_step5():
    """Step 5: Create Buffers"""
    st.header("Step 5: Create Buffers")

    # Check prerequisites
    if not check_prerequisites([4]):
        show_prerequisite_error("Step 5", [4])
        return

    if not SessionStateManager.get("step4_complete", False):
        display_validation_error("Please complete Step 4 first.")
        return

    if not SessionStateManager.has("Merged_collection"):
        display_validation_error("No merged data found. Please complete Step 4 first.")
        return

    # Display buffer settings
    st.subheader("Buffer Settings")
    elevation_dist = st.number_input(
        "Elevation distance (meters)",
        value=AppConstants.DEFAULT_ELEVATION_DISTANCE,
        min_value=1,
        step=AppConstants.ELEVATION_STEP,
        key="elevation_distance_input",
    )
    buffer_radius = st.number_input(
        "Enter buffer radius (meters). We will analyze locations within this buffer "
        f"that are no more than the selected elevation distance ({elevation_dist}m) "
        "away from the dam location.",
        min_value=AppConstants.MIN_BUFFER_RADIUS,
        step=AppConstants.BUFFER_STEP,
        value=SessionStateManager.get("buffer_radius"),
        key="buffer_radius_input",
    )

    if st.button("Create Buffers"):
        with safe_processing("Creating buffers"):
            dam_data = create_buffers(buffer_radius)

            if dam_data:
                # Split into positive and negative points for display
                negative = dam_data.filter(ee.Filter.eq("Dam", "negative"))
                positive = dam_data.filter(ee.Filter.eq("Dam", "positive"))

                # Display buffer preview
                st.subheader("Buffer Preview")
                buffer_map = geemap.Map()
                buffer_map.add_basemap("SATELLITE")
                buffer_map.addLayer(negative, {"color": "red"}, "Negative")
                buffer_map.addLayer(positive, {"color": "blue"}, "Positive")
                buffer_map.centerObject(dam_data)
                buffer_map.to_streamlit(width=800, height=600)

                SessionStateManager.complete_step(5)
                display_success_message(f"Buffers created successfully with radius {buffer_radius} meters!")


def compute_metrics_df(dam_data, elevation_dist):
    """Run the batched metric pipeline over buffered points and return a DataFrame"""
    dam_data = dam_data.filter(ee.Filter.notNull(["Survey_Date"]))
    total_count = dam_data.size().getInfo()

    if total_count == 0:
        display_validation_error(
            "No valid data with dates found.",
            ["Check your data for valid date fields", "Ensure date format is correct"],
        )
        return None

    # Process data in batches
    batch_size = AppConstants.BATCH_SIZE
    num_batches = (total_count + batch_size - 1) // batch_size
    df_list = []

    progress_bar = st.progress(0)
    st.write(f"Processing {total_count} dam points in {num_batches} batches")

    for i in range(num_batches):
        try:
            st.write(f"Processing batch {i + 1} of {num_batches}")

            # Get current batch
            dam_batch = dam_data.toList(batch_size, i * batch_size)
            dam_batch_fc = ee.FeatureCollection(dam_batch)

            # Process batch through pipeline
            s2_cloud_mask_batch = ee.ImageCollection(s2_export_for_visual(dam_batch_fc, add_elevation_band,
                                                                          elevation_dist))
            s2_image_collection_batch = ee.ImageCollection(s2_cloud_mask_batch)
            s2_with_lst_batch = s2_image_collection_batch.map(add_landsat_lst_et)
            results_fc_lst_batch = s2_with_lst_batch.map(compute_all_metrics_lst_et)
            results_fcc_lst_batch = ee.FeatureCollection(results_fc_lst_batch)

            # Convert to DataFrame
            df_batch = geemap.ee_to_df(results_fcc_lst_batch)
            df_list.append(df_batch)

            progress_bar.progress((i + 1) / num_batches)
        except Exception as e:
            st.warning(f"Error processing batch {i + 1}: {e}")
            continue

    if not df_list:
        display_validation_error("No data could be processed from any batch.")
        return None

    # Combine results
    df_lst = pd.concat(df_list, ignore_index=True)
    df_lst["Image_month"] = pd.to_numeric(df_lst["Image_month"])
    df_lst["Image_year"] = pd.to_numeric(df_lst["Image_year"])
    df_lst["Dam_status"] = df_lst["Dam_status"].replace({"positive": "Dam", "negative": "Non-dam"})
    return df_lst


@handle_processing_errors("combined effects analysis")
def analyze_combined_effects(elevation_dist):
    """Analyze combined effects of dams"""
    dam_data = SessionStateManager.get_dam_data()
    if not dam_data:
        display_validation_error("Dam data not found. Please complete previous steps.")
        return None

    # Validate dates in data
    def validate_date(feature):
        date = feature.get("Survey_Date")
        if not date:
            date = feature.get("date")
        return feature

    dam_data = dam_data.map(validate_date)

    df_lst = compute_metrics_df(dam_data, elevation_dist)
    if df_lst is None:
        return None

    # Create visualization
    fig, axes = plt.subplots(4, 1, figsize=(12, 18))
    metrics = ["NDVI", "NDWI_Green", "LST", "ET"]
    titles = ["NDVI", "NDWI Green", "LST (°C)", "ET (mm)"]

    for ax, metric, title in zip(axes, metrics, titles):
        try:
            sns.lineplot(
                data=df_lst,
                x="Image_month",
                y=metric,
                hue="Dam_status",
                style="Dam_status",
                markers=True,
                dashes=False,
                ax=ax,
            )
            ax.set_title(f"{title} by Month", fontsize=14)
            ax.set_xticks(range(1, 13))
        except ValueError:
            fig.delaxes(ax)
            st.warning(f"Unable to create map for {title}.")

    plt.tight_layout()

    SessionStateManager.set_multiple({"fig": fig, "df_lst": df_lst, "visualization_complete": True})

    return {"figure": fig, "dataframe": df_lst}


def _mean_over_months(sub_df, metric, months):
    """Average a metric over the selected months for one (year, status) subset.

    Cross-point monthly means are computed first, then averaged with equal weight
    per month; the 95% CI reflects month-to-month spread within the year.
    """
    if sub_df.empty or metric not in sub_df.columns:
        return float("nan"), 0.0

    monthly = sub_df[sub_df["Image_month"].isin(months)].groupby("Image_month")[metric].mean().dropna()
    if monthly.empty:
        return float("nan"), 0.0

    n = len(monthly)
    error = float(1.96 * monthly.std() / math.sqrt(n)) if n > 1 else 0.0
    return float(monthly.mean()), error


def plot_yearly_comparison(df_lst, years, months):
    """Plot per-year averages of each metric for dam vs non-dam locations"""
    fig, axes = plt.subplots(4, 1, figsize=(12, 18))
    metrics = ["NDVI", "NDWI_Green", "LST", "ET"]
    titles = ["NDVI", "NDWI Green", "LST (°C)", "ET (mm)"]
    bar_width = 0.35

    for ax, metric, title in zip(axes, metrics, titles):
        for offset, status in ((-bar_width / 2, "Dam"), (bar_width / 2, "Non-dam")):
            means, errors = [], []
            for year in years:
                sub_df = df_lst[(df_lst["Dam_status"] == status) & (df_lst["analysis_year"] == year)]
                mean, error = _mean_over_months(sub_df, metric, months)
                means.append(mean)
                errors.append(error)
            ax.bar(
                [i + offset for i in range(len(years))],
                means,
                width=bar_width,
                yerr=errors,
                capsize=4,
                label=status,
            )
        ax.set_title(f"{title} by Year", fontsize=14)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([str(year) for year in years])
        ax.legend()

    plt.tight_layout()
    return fig


@handle_processing_errors("multi-year analysis")
def analyze_multiple_years(elevation_dist, years, months):
    """Run the combined analysis once per year and compare yearly averages"""
    merged_collection = SessionStateManager.get("Merged_collection")
    if not merged_collection:
        display_validation_error("No merged data found. Please complete Step 4 first.")
        return None

    buffer_radius = SessionStateManager.get("buffer_radius_input", SessionStateManager.get("buffer_radius"))

    year_dfs = []
    for year in years:
        st.write(f"Analyzing year {year}")

        # Re-date every point to July 1 of the target year so the pipeline pulls
        # that year's imagery, then re-buffer and run the metric pipeline.
        full_date = f"{year}-07-01"
        dated_collection = merged_collection.map(lambda feature, date=full_date: feature.set("date", date))
        dam_data = buffer_merged_points(dated_collection, buffer_radius)

        df_year = compute_metrics_df(dam_data, elevation_dist)
        if df_year is None or df_year.empty:
            st.warning(f"No data could be processed for {year}.")
            continue
        df_year["analysis_year"] = year
        year_dfs.append(df_year)

    if not year_dfs:
        display_validation_error("No data could be processed for any selected year.")
        return None

    df_lst = pd.concat(year_dfs, ignore_index=True)
    fig = plot_yearly_comparison(df_lst, years, months)

    SessionStateManager.set_multiple({"fig": fig, "df_lst": df_lst, "visualization_complete": True})

    return {"figure": fig, "dataframe": df_lst}


def create_export_dataframe(df, include_coordinates=True):
    """Create export DataFrame with coordinates"""

    if not include_coordinates:
        return df

    export_df = df.copy()

    export_df["longitude"] = 0
    export_df["latitude"] = 0

    if SessionStateManager.has("Dam_data"):
        coords_df = extract_coordinates_df(SessionStateManager.get("Dam_data"))

        if not coords_df.empty:
            # determine why id_property is being lost in df conversion from `results_fcc_lst_batch` to `df_batch`
            if "id_property" in export_df.columns:
                export_df = export_df.merge(coords_df, on="id_property", how="left")
                export_df["longitude"] = export_df["longitude"].fillna(0)
                export_df["latitude"] = export_df["latitude"].fillna(0)
            else:
                if len(export_df) > len(coords_df):
                    months_per_point = len(export_df) // len(coords_df)
                    longitudes, latitudes = [], []

                    for i in range(len(coords_df)):
                        coords = coords_df.iloc[i]
                        longitudes.extend([coords["longitude"]]*months_per_point)
                        latitudes.extend([coords["latitude"]]*months_per_point)

                    export_df["longitude"] = longitudes
                    export_df["latitude"] = latitudes

    return export_df


def render_step6():
    """Step 6: Visualize Trends"""
    st.header("Step 6: Visualize Trends")

    elevation_dist = SessionStateManager.get(
        "elevation_distance_input", AppConstants.DEFAULT_ELEVATION_DISTANCE
    )

    # Check prerequisites
    if not check_prerequisites([5]):
        show_prerequisite_error("Step 6", [5])
        return

    multi_year = st.checkbox(
        "Compare multiple years",
        key="multi_year_checkbox",
        help="Re-run the analysis for each selected year (using imagery within ±6 months "
        "of July 1) and compare yearly averages for dam vs non-dam locations.",
    )

    if multi_year:
        years = st.multiselect("Years to analyze:", list(range(2017, 2025)), key="multi_year_years")
        months = st.multiselect(
            "Months to include in each yearly average:",
            list(range(1, 13)),
            default=list(range(1, 13)),
            key="multi_year_months",
        )

        if any(year < 2020 for year in years):
            st.warning("You may proceed, but ET data may not be available for some selected years.")

        if st.button("Analyze Across Years"):
            if len(years) < 2:
                st.warning("Please select at least two years to compare.")
            elif not months:
                st.warning("Please select at least one month.")
            else:
                with safe_processing("Analyzing across years"):
                    result = analyze_multiple_years(elevation_dist, sorted(years), sorted(months))
                    if result:
                        display_success_message("Multi-year analysis complete!")

    elif not SessionStateManager.get("visualization_complete", False):
        if st.button("Analyze Combined Effects"):
            with safe_processing("Analyzing combined effects"):
                result = analyze_combined_effects(elevation_dist)
                if result:
                    display_success_message("Visualization complete!")

    if SessionStateManager.get("visualization_complete", False):
        fig = SessionStateManager.get("fig")
        df_lst = SessionStateManager.get("df_lst")

        if fig:
            st.pyplot(fig)

            col1, col2 = st.columns(2)

            with col1:
                buf = io.BytesIO()
                fig.savefig(buf, format="png")
                buf.seek(0)
                st.download_button("Download Combined Figures", buf, "combined_trends.png", "image/png")

            with col2:
                if df_lst is not None:
                    export_df = create_export_dataframe(df_lst)
                    csv = export_df.to_csv(index=False).encode("utf-8")
                    st.download_button("Download Combined Data (CSV)", csv, "combined_data.csv", "text/csv")


main()
