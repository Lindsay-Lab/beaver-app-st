import io

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
    handle_file_processing_error
)
from service.load_datasets import load_nhd_collections
from service.negative_sampling import prepare_hydro, sample_negative_points
from service.parser import extract_coordinates_df, upload_non_dam_points_to_ee, upload_points_to_ee
from service.session_state import SessionStateManager, check_prerequisites, show_prerequisite_error
from service.validation import (
    check_waterway_intersection,
    generate_validation_report,
    validate_dam_waterway_distance,
    visualize_validation_results,
)
from service.visualize_trends import (
    s2_export_for_visual,
    s2_export_for_visual_flowdir,
    add_landsat_lst_et,
    compute_all_metrics_lst_et,
    compute_all_metrics_up_downstream,
)


# Initialize Earth Engine and session state
initialize_earth_engine()
SessionStateManager.initialize()

def main():
    """Main application function"""
    # Show questionnaire if not shown
    if not SessionStateManager.get('questionnaire_shown', False):
        show_questionnaire()
        return

    # Main application
    st.title("Analyzing the Impact of Beaver Dams")
    st.warning(
        "Please note that the Evapotranspiration data is not available for the eastern half of the US "
        "or for certain years. Learn more on the OpenET website: [Link](https://etdata.org/)."
    )

    # Render each step in expandable sections
    with st.expander("Step 1: Upload Dam Locations", expanded=not SessionStateManager.is_step_complete(1)):
        render_step1()

    with st.expander(
            "Step 2: Select Waterway",
            expanded=SessionStateManager.is_step_complete(1) and not SessionStateManager.is_step_complete(2)
    ):
        render_step2()

    with st.expander(
            "Step 3: Validate Dam Locations",
            expanded=SessionStateManager.is_step_complete(2) and not SessionStateManager.is_step_complete(3)
    ):
        render_step3()

    with st.expander(
            "Step 4: Upload or Generate Non-Dam Locations",
            expanded=SessionStateManager.is_step_complete(3) and not SessionStateManager.is_step_complete(4)
    ):
        render_step4()

    with st.expander(
            "Step 5: Create Buffers",
            expanded=SessionStateManager.is_step_complete(4) and not SessionStateManager.is_step_complete(5)
    ):
        render_step5()

    with st.expander("Step 6: Visualize Trends", expanded=SessionStateManager.is_step_complete(5)):
        render_step6()

    # Footer
    st.info(
        "You can make the Beaver Impacts Tool better by filling out our "
        "[feedback form](https://docs.google.com/forms/d/e/1FAIpQLSeE1GP7OptA4-z8Melz2AHxNsddtL9ZgJVXdVVtxLsrljJ10Q/viewform?usp=sharing)."
    )

def show_questionnaire():
    """Display initial questionnaire section"""
    st.title("Beaver Impacts Feedback Survey")
    st.markdown(
        """
    Thank you for being a beta tester for the Beaver Impacts web tool! We really value your input and appreciate you taking the time to fill out this form.

    Please click [here](https://docs.google.com/forms/d/e/1FAIpQLSeE1GP7OptA4-z8Melz2AHxNsddtL9ZgJVXdVVtxLsrljJ10Q/viewform?usp=sharing) to start the survey. Continue on by clicking below:
    """
    )

    if st.button("I have opened the survey and will fill it out after trying the web tool.", type="primary"):
        SessionStateManager.set('questionnaire_shown', True)
        st.rerun()


@handle_processing_errors("file upload processing")
def process_dam_upload(uploaded_file):
    """Process uploaded dam location file"""
    feature_collection = upload_points_to_ee(uploaded_file, widget_prefix="Dam")
    if feature_collection:
        SessionStateManager.set_multiple({
            'Positive_collection': feature_collection,
            'Full_positive': feature_collection,
        })
        SessionStateManager.complete_step(1)
        return feature_collection
    return None


def render_step1():
    """Step 1: Upload Dam Locations"""
    st.header("Step 1: Upload Dam Locations")

    uploaded_file = st.file_uploader(
        "Choose a CSV or GeoJSON file",
        type=["csv", "geojson"],
        key="Dam_file_uploader"
    )

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
    full_positive = SessionStateManager.get('Full_positive')
    if not full_positive:
        return None

    # Get dam bounds and find states
    positive_dam_bounds = full_positive.geometry().bounds()
    states_dataset = ee.FeatureCollection("TIGER/2018/States")
    states_with_dams = states_dataset.filterBounds(positive_dam_bounds)

    SessionStateManager.set('Positive_dam_state', states_with_dams)
    state_names = states_with_dams.aggregate_array("NAME").getInfo()

    if not state_names:
        display_validation_error(
            "No states found within the dam data bounds.",
            ["Check that your dam coordinates are valid", "Ensure coordinates are in the correct format"]
        )
        return None

    st.write(f"States within dam data bounds: {state_names}")

    # Load NHD collections
    nhd_collections = load_nhd_collections(state_names)

    if nhd_collections:
        merged_nhd = ee.FeatureCollection(nhd_collections).flatten()
        SessionStateManager.set_multiple({
            'selected_waterway': merged_nhd,
            'Waterway': merged_nhd,
            'dataset_loaded': True
        })
        SessionStateManager.complete_step(2)
        return merged_nhd
    else:
        display_validation_error(
            "No NHD datasets found for the selected states.",
            ["Try using the alternative waterway dataset", "Check that your dam locations are in supported areas"]
        )
        return None


def render_alternative_waterway_options():
    """Render alternative waterway dataset options"""
    st.subheader("To use a different waterway map instead:")

    upload_own_checkbox = st.checkbox("Use Custom Waterway Map")
    choose_other_checkbox = st.checkbox("Use Alternative Waterway Map")

    if upload_own_checkbox:
        asset_id = st.text_input(
            "Enter GEE Asset Table ID (e.g., projects/ee-beaver-lab/assets/Hydro/MA_Hydro_arc):"
        )
        if st.button("Load Custom Dataset"):
            with safe_processing("Loading custom dataset"):
                waterway_own = ee.FeatureCollection(asset_id)
                SessionStateManager.set_multiple({
                    'selected_waterway': waterway_own,
                    'dataset_loaded': True
                })
                SessionStateManager.complete_step(2)
                display_success_message("Custom dataset successfully loaded.")

    if choose_other_checkbox:
        dataset_option = st.selectbox("Select alternative map:", ["WWF Free Flowing Rivers"])

        if st.button("Load Alternative Map"):
            with safe_processing("Loading alternative dataset"):
                if dataset_option == "WWF Free Flowing Rivers":
                    states_with_dams = SessionStateManager.get('Positive_dam_state')
                    wwf_dataset = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers")
                    clipped_wwf = wwf_dataset.filterBounds(states_with_dams)
                    SessionStateManager.set('selected_waterway', clipped_wwf)
                    SessionStateManager.complete_step(2)
                    display_success_message("WWF dataset successfully loaded.")


def render_step2():
    """Step 2: Select Waterway"""
    st.header("Step 2: Select Waterway")

    # Check prerequisites
    if not check_prerequisites([1]):
        show_prerequisite_error("Step 2", [1])
        return

    # Show loading message
    st.success(
        "Automatically loaded NHD dataset. If you want to use a different dataset, "
        "you can upload your own or use the alternative dataset."
    )

    with safe_processing("Loading waterway data"):
        waterway = load_waterway_data()

        if waterway:
            # Display map
            waterway_map = geemap.Map()
            waterway_map.add_basemap("SATELLITE")
            waterway_map.centerObject(SessionStateManager.get('Full_positive'))
            waterway_map.addLayer(waterway, {"color": "blue"}, "Selected Waterway")
            waterway_map.addLayer(SessionStateManager.get('Full_positive'), {"color": "red"}, "Dams")
            waterway_map.to_streamlit(
                width=AppConstants.LARGE_MAP_WIDTH,
                height=AppConstants.LARGE_MAP_HEIGHT
            )

            render_alternative_waterway_options()


@handle_processing_errors("dam location validation")
def perform_dam_validation(max_distance):
    """Perform dam location validation"""
    error_msg = SessionStateManager.validate_earth_engine_data({
        "Full_positive": "Dam locations",
        "Waterway": "Waterway data"
    })

    if error_msg:
        display_validation_error(error_msg)
        return None

    full_positive = SessionStateManager.get('Full_positive')
    waterway = SessionStateManager.get('Waterway')

    # Perform distance validation
    distance_validation = validate_dam_waterway_distance(full_positive, waterway, max_distance)

    # Perform intersection validation
    intersection_validation = check_waterway_intersection(full_positive, waterway)

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


def handle_validation_results(validation_results):
    """Handle validation results and user decisions"""
    valid_count = validation_results["valid_count"].getInfo()
    invalid_count = validation_results["invalid_count"].getInfo()

    if valid_count == 0:
        display_validation_error(
            "No valid dam locations found. All dams failed validation.",
            ["Check your dam locations and waterway data", "Adjust the maximum distance parameter"]
        )
        return

    if invalid_count > 0:
        options = display_warning_with_options(
            "Some dam locations have been identified as potentially invalid. "
            "Please review the validation report and map above. "
            "You can continue with all dams or only use the valid dams.",
            {
                "Continue with all dams": "use_all_dams_btn",
                "Only use valid dams": "use_valid_dams_btn"
            }
        )

        if options.get("use_all_dams_btn"):
            SessionStateManager.set_multiple({
                'validation_complete': True,
                'use_all_dams': True,
                'Dam_data': SessionStateManager.get('Full_positive'),
                'show_non_dam_section': True,
                'validation_step': 'completed'
            })
            display_success_message("Selected to continue with all dams.")

        elif options.get("use_valid_dams_btn"):
            valid_dams = validation_results["valid_dams"]
            SessionStateManager.set_multiple({
                'Full_positive': valid_dams,
                'validation_step': 'completed',
                'validation_complete': True,
                'use_all_dams': False,
                'Dam_data': valid_dams,
                'show_non_dam_section': True
            })
            display_success_message(f"Successfully filtered to {valid_count} valid dams.")
    else:
        SessionStateManager.set_multiple({
            'validation_complete': True,
            'use_all_dams': True,
            'Dam_data': SessionStateManager.get('Full_positive'),
            'show_non_dam_section': True,
            'validation_step': 'completed'
        })
        display_success_message("All dams are valid.")

    SessionStateManager.complete_step(3)


def render_step3():
    """Step 3: Validate Dam Locations"""
    st.header("Step 3: Validate Dam Locations")

    # Check prerequisites
    if not check_prerequisites([2]):
        show_prerequisite_error("Step 3", [2])
        return

    # Only show validation section if validation is not complete
    if not SessionStateManager.get('validation_complete', False):
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
                    # Store validation results and display report
                    SessionStateManager.set_multiple({
                        'validation_results': validation_results,
                        'validation_step': 'show_options'
                    })

                    st.subheader("Validation Report")
                    st.text(generate_validation_report(validation_results))

                    # Display validation map
                    st.subheader("Validation Map")
                    validation_map = visualize_validation_results(
                        SessionStateManager.get('Full_positive'),
                        SessionStateManager.get('Waterway'),
                        validation_results
                    )
                    validation_map.to_streamlit(
                        width=AppConstants.LARGE_MAP_WIDTH,
                        height=AppConstants.LARGE_MAP_HEIGHT
                    )

    # Show options after validation is complete
    if SessionStateManager.get('validation_step') == 'show_options':
        validation_results = SessionStateManager.get('validation_results')
        if validation_results:
            handle_validation_results(validation_results)


@handle_processing_errors("non-dam data processing")
def process_non_dam_upload(uploaded_file):
    """Process uploaded non-dam data"""
    negative_feature_collection = upload_non_dam_points_to_ee(
        uploaded_file, widget_prefix="NonDam"
    )

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
            first_pos = SessionStateManager.get('Positive_collection').first()
            date = first_pos.get("date")
        return (
            feature.set("id_property", ee.String("N").cat(idx.add(1).int().format()))
            .set("date", date)
            .set("Dam", "negative")
        )

    neg_points_id = ee.FeatureCollection(indices.map(set_id_negatives2))

    # Process positive samples
    pos_collection = (SessionStateManager.get('Dam_data') if not SessionStateManager.get('use_all_dams')
                      else SessionStateManager.get('Positive_collection'))
    pos_collection = pos_collection.map(lambda feature: feature.set("Dam", "positive"))

    pos_features_list = pos_collection.toList(pos_collection.size())
    pos_indices = ee.List.sequence(0, pos_collection.size().subtract(1))

    def set_id_positives(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(pos_features_list.get(idx))
        date = feature.get("date")
        if not date:
            first_pos = SessionStateManager.get('Positive_collection').first()
            date = first_pos.get("date")
        return feature.set("id_property", ee.String("P").cat(idx.add(1).int().format())).set("date", date)

    positive_dam_id = ee.FeatureCollection(pos_indices.map(set_id_positives))
    merged_collection = positive_dam_id.merge(neg_points_id)

    SessionStateManager.set_multiple({
        'Merged_collection': merged_collection,
        'Negative_upload_collection': negative_feature_collection,
        'Full_negative': negative_feature_collection,
        'buffer_complete': True
    })
    SessionStateManager.complete_step(4)

    return {
        'negative_points': neg_points_id,
        'positive_points': positive_dam_id,
        'merged_collection': merged_collection
    }


@handle_processing_errors("negative point generation")
def generate_negative_points(inner_radius, outer_radius, sampling_scale):
    """Generate negative points using specified parameters"""
    # Validate required data
    error_msg = SessionStateManager.validate_earth_engine_data({
        "Positive_collection": "Dam locations",
        "selected_waterway": "Waterway data"
    })

    if error_msg:
        display_validation_error(error_msg)
        return None

    # Get positive dams
    positive_dams_fc = (SessionStateManager.get('Dam_data') if not SessionStateManager.get('use_all_dams')
                        else SessionStateManager.get('Positive_collection'))

    if positive_dams_fc.size().getInfo() == 0:
        display_validation_error(
            "No valid dam data found.",
            ["Check your data and try again", "Ensure previous steps completed successfully"]
        )
        return None

    # Get bounds and clip waterway
    positive_bounds = positive_dams_fc.geometry().bounds()
    bounds_area = positive_bounds.area(1).getInfo()

    if bounds_area == 0:
        display_validation_error("No valid dam locations found.")
        return None

    waterway_fc = SessionStateManager.get('selected_waterway').filterBounds(positive_bounds)

    if waterway_fc.size().getInfo() == 0:
        display_validation_error(
            "No waterway data found within the dam locations area.",
            ["Check your waterway selection", "Verify dam locations are correct"]
        )
        return None

    # Prepare hydro raster and generate negative points
    hydroRaster = prepare_hydro(waterway_fc)
    negativePoints = sample_negative_points(
        positive_dams_fc, hydroRaster, inner_radius, outer_radius, sampling_scale
    )

    if negativePoints.size().getInfo() == 0:
        display_validation_error(
            "No negative points were generated.",
            ["Try adjusting the radius parameters", "Check that there's sufficient area for sampling"]
        )
        return None

    # Set date for negative points
    first_pos = positive_dams_fc.first()
    date = ee.Date(first_pos.get("date"))
    year_string = date.format("YYYY")
    full_date = ee.String(year_string).cat("-07-01")

    negativePoints = negativePoints.map(
        lambda feature: feature.set("Dam", "negative").set("date", full_date)
    )

    # Process negative points with IDs
    fc = negativePoints
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

    SessionStateManager.set_multiple({
        'Merged_collection': merged_collection,
        'buffer_complete': True
    })
    SessionStateManager.complete_step(4)

    return {
        'negative_points': neg_points_id,
        'positive_points': positive_dam_id,
        'merged_collection': merged_collection
    }


def render_step4():
    """Step 4: Upload or Generate Non-Dam Locations"""
    st.header("Step 4: Upload or Generate Non-Dam Locations")

    # Check prerequisites
    if not check_prerequisites([3]):
        show_prerequisite_error("Step 4", [3])
        return

    if not SessionStateManager.get('validation_complete', False):
        display_validation_error("Please complete the validation step first.")
        return

    if not SessionStateManager.get('show_non_dam_section', False):
        display_validation_error("Please complete the validation step first.")
        return

    # Display current dam usage status
    if SessionStateManager.get('use_all_dams'):
        st.info("Using all dam locations for analysis")
    else:
        st.info("Using only valid dam locations for analysis")

    upload_negatives_checkbox = st.checkbox("Upload Non-Dam Dataset (must be on a waterbody)")
    generate_negatives_checkbox = st.checkbox("Generate Non-Dam Locations")

    if upload_negatives_checkbox:
        uploaded_negatives = st.file_uploader(
            "Upload Non-Dam Dataset (CSV or GeoJSON)",
            type=["csv", "geojson"],
            key="negative_file_uploader"
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
                        preview_map.addLayer(result['negative_points'], {"color": "red"}, "Non-dam locations")
                        preview_map.addLayer(result['positive_points'], {"color": "blue"}, "Dam locations")
                        preview_map.centerObject(result['merged_collection'])
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
            key="inner_radius_input"
        )
        outer_radius = st.number_input(
            "Outer Radius (meters)",
            value=AppConstants.DEFAULT_OUTER_RADIUS,
            min_value=0,
            step=AppConstants.RADIUS_STEP,
            key="outer_radius_input"
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
                    negative_points_map.addLayer(result['negative_points'], {"color": "red", "width": 2}, "Negative")
                    negative_points_map.addLayer(result['positive_points'], {"color": "blue"}, "Positive")
                    negative_points_map.centerObject(result['merged_collection'])
                    negative_points_map.to_streamlit(
                        width=AppConstants.LARGE_MAP_WIDTH,
                        height=AppConstants.LARGE_MAP_HEIGHT
                    )


@handle_processing_errors("buffer creation")
def create_buffers(buffer_radius):
    """Create buffers around merged collection points"""
    merged_collection = SessionStateManager.get('Merged_collection')
    if not merged_collection:
        display_validation_error("No merged data found. Please complete Step 4 first.")
        return None

    # Get date from first positive dam
    first_pos = SessionStateManager.get('Positive_collection').first()
    date = ee.Date(first_pos.get("date"))
    year_string = date.format("YYYY")
    full_date = ee.String(year_string).cat("-07-01")

    def add_dam_buffer_and_standardize_date(feature):
        dam_status = feature.get("Dam")
        date = feature.get("date")

        if not date:
            date = feature.get("Survey_Date")
            if not date:
                first_pos = SessionStateManager.get('Positive_collection').first()
                date = first_pos.get("date")

        standardized_date = ee.Date(date)
        formatted_date = standardized_date.format("YYYYMMdd")

        # Create buffered geometry
        buffered_geometry = feature.geometry().buffer(buffer_radius)

        return ee.Feature(buffered_geometry).set({
            "Dam": dam_status,
            "Survey_Date": standardized_date,
            "Damdate": ee.String("DamDate_").cat(formatted_date),
            "Point_geo": feature.geometry(),
            "id_property": feature.get("id_property"),
        })

    buffered_collection = merged_collection.map(add_dam_buffer_and_standardize_date)
    dam_data = buffered_collection.select(["id_property", "Dam", "Survey_Date", "Damdate", "Point_geo"])

    SessionStateManager.set_multiple({
        'Dam_data': dam_data,
        'buffers_created': True
    })

    return dam_data


def render_step5():
    """Step 5: Create Buffers"""
    st.header("Step 5: Create Buffers")

    # Check prerequisites
    if not check_prerequisites([4]):
        show_prerequisite_error("Step 5", [4])
        return

    if not SessionStateManager.get('step4_complete', False):
        display_validation_error("Please complete Step 4 first.")
        return

    if not SessionStateManager.has('Merged_collection'):
        display_validation_error("No merged data found. Please complete Step 4 first.")
        return

    # Display buffer settings
    st.subheader("Buffer Settings")
    buffer_radius = st.number_input(
        "Enter buffer radius (meters). We will analyze locations within this buffer "
        "that are no more than 3m in elevation away from the dam location.",
        min_value=AppConstants.MIN_BUFFER_RADIUS,
        step=AppConstants.BUFFER_STEP,
        value=SessionStateManager.get('buffer_radius'),
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


@handle_processing_errors("combined effects analysis")
def analyze_combined_effects():
    """Analyze combined effects of dams"""
    dam_data = SessionStateManager.get('Dam_data')
    if not dam_data:
        display_validation_error("Dam data not found. Please complete previous steps.")
        return None

    # Validate dates in data
    def validate_date(feature):
        date = feature.get("Survey_Date")
        if not date:
            date = feature.get("date")
        return feature

    dam_data = dam_data.map(validate_date).filter(ee.Filter.notNull(["Survey_Date"]))

    if dam_data.size().getInfo() == 0:
        display_validation_error(
            "No valid data with dates found.",
            ["Check your data for valid date fields", "Ensure date format is correct"]
        )
        return None

    # Process data in batches
    total_count = dam_data.size().getInfo()
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
            s2_cloud_mask_batch = ee.ImageCollection(s2_export_for_visual(dam_batch_fc))
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

    # Create visualization
    fig, axes = plt.subplots(4, 1, figsize=(12, 18))
    metrics = ["NDVI", "NDWI_Green", "LST", "ET"]
    titles = ["NDVI", "NDWI Green", "LST (°C)", "ET"]

    for ax, metric, title in zip(axes, metrics, titles):
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

    plt.tight_layout()

    SessionStateManager.set_multiple({
        'fig': fig,
        'df_lst': df_lst,
        'visualization_complete': True
    })

    return {'figure': fig, 'dataframe': df_lst}


@handle_processing_errors("upstream downstream analysis")
def analyze_upstream_downstream():
    """Analyze upstream and downstream effects"""
    error_msg = SessionStateManager.validate_required_data({
        "Dam_data": "Dam locations",
        "Waterway": "Waterway data"
    })

    if error_msg:
        display_validation_error(error_msg)
        return None

    dam_data = SessionStateManager.get('Dam_data')
    waterway_fc = SessionStateManager.get('Waterway')

    # Process in batches
    total_count = dam_data.size().getInfo()
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

            # Process through pipeline
            s2_ic_batch = s2_export_for_visual_flowdir(dam_batch_fc, waterway_fc)
            s2_with_lst_et = s2_ic_batch.map(add_landsat_lst_et)
            results_batch = s2_with_lst_et.map(compute_all_metrics_up_downstream)

            # Convert to DataFrame
            df_batch = geemap.ee_to_df(ee.FeatureCollection(results_batch))
            df_list.append(df_batch)
            progress_bar.progress((i + 1) / num_batches)
        except Exception as e:
            st.warning(f"Error processing batch {i + 1}: {e}")
            continue

    if not df_list:
        display_validation_error("All batches failed processing. Please check your data.")
        return None

    # Combine results
    final_df = pd.concat(df_list, ignore_index=True)
    final_df["Dam_status"] = final_df["Dam_status"].replace({"positive": "Dam", "negative": "Non-dam"})

    # Create visualization
    fig2, axes2 = plt.subplots(4, 1, figsize=(12, 20))

    def melt_and_plot(df, metric, ax):
        melted = df.melt(
            ["Image_year", "Image_month", "Dam_status"],
            [f"{metric}_up", f"{metric}_down"],
            "Flow",
            metric,
        )
        melted["Flow"] = melted["Flow"].replace({f"{metric}_up": "Upstream", f"{metric}_down": "Downstream"})
        sns.lineplot(
            data=melted,
            x="Image_month",
            y=metric,
            hue="Dam_status",
            style="Flow",
            markers=True,
            ax=ax,
        )
        ax.set_title(f"{metric.upper()} by Month (Upstream vs Downstream)")
        ax.set_xticks(range(1, 13))

    for ax, met in zip(axes2, ["NDVI", "NDWI", "LST", "ET"]):
        melt_and_plot(final_df, met, ax)

    plt.tight_layout()

    SessionStateManager.set_multiple({
        'fig2': fig2,
        'final_df': final_df,
        'upstream_analysis_complete': True
    })

    return {'figure': fig2, 'dataframe': final_df}


def create_export_dataframe(df, include_coordinates=True):
    """Create export DataFrame with coordinates"""
    export_df = df.copy()

    if include_coordinates and SessionStateManager.has('Dam_data'):
        coords_df = extract_coordinates_df(SessionStateManager.get('Dam_data'))

        if not coords_df.empty and "id_property" in export_df.columns:
            # For upstream/downstream data, we need to handle multiple rows per point
            if len(export_df) > len(coords_df):
                months_per_point = len(export_df) // len(coords_df)
                longitudes, latitudes = [], []

                for i in range(len(coords_df)):
                    coords = coords_df.iloc[i]
                    for _ in range(months_per_point):
                        longitudes.append(coords["longitude"])
                        latitudes.append(coords["latitude"])

                export_df["longitude"] = longitudes
                export_df["latitude"] = latitudes
            else:
                # Regular merge for combined analysis
                export_df = export_df.merge(coords_df, on="id_property", how="left")
                export_df["longitude"] = export_df["longitude"].fillna(0)
                export_df["latitude"] = export_df["latitude"].fillna(0)
        else:
            export_df["longitude"] = 0
            export_df["latitude"] = 0
    else:
        export_df["longitude"] = 0
        export_df["latitude"] = 0

    return export_df


def render_step6():
    """Step 6: Visualize Trends"""
    st.header("Step 6: Visualize Trends")

    # Check prerequisites
    if not check_prerequisites([5]):
        show_prerequisite_error("Step 6", [5])
        return

    tab1, tab2 = st.tabs(["Combined Analysis", "Upstream & Downstream Analysis"])

    with tab1:
        if not SessionStateManager.get('visualization_complete', False):
            if st.button("Analyze Combined Effects"):
                with safe_processing("Analyzing combined effects"):
                    result = analyze_combined_effects()
                    if result:
                        display_success_message("Visualization complete!")

        if SessionStateManager.get('visualization_complete', False):
            fig = SessionStateManager.get('fig')
            df_lst = SessionStateManager.get('df_lst')

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

    with tab2:
        if not SessionStateManager.get('upstream_analysis_complete', False):
            if st.button("Analyze Upstream & Downstream Effects"):
                with safe_processing("Analyzing Upstream & Downstream"):
                    result = analyze_upstream_downstream()
                    if result:
                        st.pyplot(result['figure'])
                        display_success_message("Upstream & downstream analysis completed successfully!")

        if SessionStateManager.get('upstream_analysis_complete', False):
            fig2 = SessionStateManager.get('fig2')
            final_df = SessionStateManager.get('final_df')

            if fig2:
                st.pyplot(fig2)

                col3, col4 = st.columns(2)

                with col3:
                    buf2 = io.BytesIO()
                    fig2.savefig(buf2, format="png")
                    buf2.seek(0)
                    st.download_button(
                        "Download Up/Downstream Figures",
                        buf2,
                        "upstream_downstream_trends.png",
                        "image/png",
                        key="download_updown_fig"
                    )

                with col4:
                    if final_df is not None:
                        export_df = create_export_dataframe(final_df)
                        csv2 = export_df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Download Up/Downstream Data (CSV)",
                            csv2,
                            "upstream_downstream_data.csv",
                            "text/csv",
                            key="download_updown_csv"
                        )


main()
