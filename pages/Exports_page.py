import io
import traceback

import ee
import geemap.foliumap as geemap
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from service.batch_processing import process_to_dataframe
from service.constants import (
    LARGE_BATCH_SIZE,
    MAP_HEIGHT,
    MAP_WIDTH,
    PLOT_FIGURE_HEIGHT_LARGE,
    PLOT_FIGURE_HEIGHT_SMALL,
    PLOT_FIGURE_WIDTH,
    STATE_ABBREVIATIONS,
)
from service.Data_management import add_dam_buffer_and_standardize_date
from service.earth_engine_auth import initialize_earth_engine
from service.Negative_sample_functions import prepareHydro, sampleNegativePoints
from service.Parser import upload_non_dam_points_to_ee, upload_points_to_ee
from service.Validation_service import (
    check_waterway_intersection,
    generate_validation_report,
    validate_dam_waterway_distance,
    visualize_validation_results,
)
from service.Visualize_trends import (
    S2_Export_for_visual,
    S2_Export_for_visual_flowdir,
    add_landsat_lst_et,
    compute_all_metrics_LST_ET,
    compute_all_metrics_up_downstream,
)

initialize_earth_engine()


def extract_coordinates_df(dam_data):
    """
    Extract coordinates from Dam_data and create a DataFrame with id_property and coordinates

    Args:
        dam_data: Earth Engine Feature Collection containing dam data

    Returns:
        DataFrame with id_property, longitude, and latitude columns
    """
    try:
        # Get features from Dam_data
        dam_features = dam_data.getInfo()["features"]

        coords_data = []
        for i, feature in enumerate(dam_features):
            try:
                props = feature["properties"]
                id_prop = props.get("id_property")

                if not id_prop:
                    st.warning(f"Feature {i} missing id_property")
                    continue

                # Extract coordinates from Point_geo
                if "Point_geo" in props:
                    point_geo = props["Point_geo"]

                    if isinstance(point_geo, dict) and "coordinates" in point_geo:
                        coords = point_geo["coordinates"]
                        if isinstance(coords, list) and len(coords) >= 2:
                            coords_data.append({"id_property": id_prop, "longitude": coords[0], "latitude": coords[1]})
                        else:
                            st.warning(f"Invalid coordinates format for feature {i}: {coords}")
                    else:
                        st.warning(f"Point_geo missing coordinates for feature {i}")
                else:
                    st.warning(f"No Point_geo found for feature {i}")

            except Exception as e:
                st.warning(f"Error processing feature {i}: {str(e)}")
                continue

        # Create DataFrame from coordinates data
        coords_df = pd.DataFrame(coords_data)

        return coords_df
    except Exception as e:
        st.warning(f"Could not extract coordinates: {str(e)}")
        return pd.DataFrame(columns=["id_property", "longitude", "latitude"])


# Initialize session state for questionnaire
if "questionnaire_shown" not in st.session_state:
    st.session_state.questionnaire_shown = False
if "survey_clicked" not in st.session_state:
    st.session_state.survey_clicked = False

# Initialize session state variables
if "Positive_collection" not in st.session_state:
    st.session_state.Positive_collection = None
if "buffer_radius" not in st.session_state:
    st.session_state.buffer_radius = 150  # Default buffer radius
if "validation_complete" not in st.session_state:
    st.session_state.validation_complete = False
if "use_all_dams" not in st.session_state:
    st.session_state.use_all_dams = True
if "validation_step" not in st.session_state:
    st.session_state.validation_step = "initial"
if "show_non_dam_section" not in st.session_state:
    st.session_state.show_non_dam_section = False
if "buffer_complete" not in st.session_state:
    st.session_state.buffer_complete = False
if "Dam_data" not in st.session_state:
    st.session_state.Dam_data = None
if "Full_positive" not in st.session_state:
    st.session_state.Full_positive = None
if "selected_waterway" not in st.session_state:
    st.session_state.selected_waterway = None
if "dataset_loaded" not in st.session_state:
    st.session_state.dataset_loaded = False
if "validation_results" not in st.session_state:
    st.session_state.validation_results = None
if "buffers_created" not in st.session_state:
    st.session_state.buffers_created = False
if "Merged_collection" not in st.session_state:
    st.session_state.Merged_collection = None
if "visualization_complete" not in st.session_state:
    st.session_state.visualization_complete = False
if "df_lst" not in st.session_state:
    st.session_state.df_lst = None
if "fig" not in st.session_state:
    st.session_state.fig = None
for i in range(1, 7):
    if f"step{i}_complete" not in st.session_state:
        st.session_state[f"step{i}_complete"] = False

if not st.session_state.questionnaire_shown:
    st.title("Beaver Impacts Feedback Survey")
    st.markdown(
        """
    Thank you for being a beta tester for the Beaver Impacts web tool! We really value your input and appreciate you taking the time to fill out this form.
    
    Please click [here](https://docs.google.com/forms/d/e/1FAIpQLSeE1GP7OptA4-z8Melz2AHxNsddtL9ZgJVXdVVtxLsrljJ10Q/viewform?usp=sharing) to start the survey. Continue on by clicking below:
    """
    )

    if st.button("I have opened the survey and will fill it out after trying the web tool.", type="primary"):
        st.session_state.questionnaire_shown = True
        st.rerun()

# Continue with the rest of the application if questionnaire is shown
if st.session_state.questionnaire_shown:
    st.title("Analyzing the Impact of Beaver Dams")
    st.warning(
        "Please note that the Evapotranspiration data is not available for the eastern half of the US or for certain years. Learn more on the OpenET website: [Link](https://etdata.org/)."
    )

    # Create expandable sections for each step
    with st.expander("Step 1: Upload Dam Locations", expanded=not st.session_state.step1_complete):
        st.header("Step 1: Upload Dam Locations")
        uploaded_file = st.file_uploader("Choose a CSV or GeoJSON file", type=["csv", "geojson"], key="Dam_file_uploader")
        if uploaded_file:
            with st.spinner("Processing uploaded file..."):
                try:
                    feature_collection = upload_points_to_ee(uploaded_file, widget_prefix="Dam")
                    if feature_collection:
                        st.session_state.Positive_collection = feature_collection
                        st.session_state.Full_positive = feature_collection
                        st.session_state.step1_complete = True

                        # Display data preview
                        st.subheader("Data Preview")
                        st.text("Points may take a few seconds to upload")
                        preview_map = geemap.Map()
                        preview_map.add_basemap("SATELLITE")
                        preview_map.addLayer(feature_collection, {"color": "blue"}, "Dam Locations")
                        preview_map.centerObject(feature_collection)
                        preview_map.to_streamlit(width=800, height=600)
                except Exception as e:
                    st.error(f"Error processing file: {str(e)}")

    with st.expander(
        "Step 2: Select Waterway", expanded=st.session_state.step1_complete and not st.session_state.step2_complete
    ):
        st.header("Step 2: Select Waterway")
        if "Full_positive" in st.session_state:
            # Show loading message
            st.success(
                "Automatically loaded NHD dataset. If you want to use a different dataset, you can upload your own or use the alternative dataset."
            )

            try:
                # Get dam bounds
                positive_dam_bounds = st.session_state["Full_positive"].geometry().bounds()
                states_dataset = ee.FeatureCollection("TIGER/2018/States")
                states_with_dams = states_dataset.filterBounds(positive_dam_bounds)
                st.session_state["Positive_dam_state"] = states_with_dams
                states_geo = st.session_state["Positive_dam_state"]
                state_names = states_geo.aggregate_array("NAME").getInfo()

                if not state_names:
                    st.error("No states found within the dam data bounds.")
                else:
                    st.write(f"States within dam data bounds: {state_names}")

                    # Automatically load NHD dataset

                    nhd_collections = []
                    for state in state_names:
                        state_initial = STATE_ABBREVIATIONS.get(state)
                        if state_initial:
                            nhd_dataset = ee.FeatureCollection(
                                f"projects/sat-io/open-datasets/NHD/NHD_{state_initial}/NHDFlowline"
                            )
                            nhd_collections.append(nhd_dataset)

                    if nhd_collections:
                        merged_nhd = ee.FeatureCollection(nhd_collections).flatten()
                        st.session_state.selected_waterway = merged_nhd
                        st.session_state["Waterway"] = st.session_state.selected_waterway
                        st.session_state.dataset_loaded = True
                        st.session_state.step2_complete = True

                        # Display map
                        Waterway_map = geemap.Map()
                        Waterway_map.add_basemap("SATELLITE")
                        Waterway_map.centerObject(st.session_state["Full_positive"])
                        # Add waterway layer first
                        Waterway_map.addLayer(st.session_state.selected_waterway, {"color": "blue"}, "Selected Waterway")
                        # Then add dam points layer
                        Waterway_map.addLayer(st.session_state["Full_positive"], {"color": "red"}, "Dams")
                        Waterway_map.to_streamlit(width=MAP_WIDTH, height=MAP_HEIGHT)

                        # Provide additional options
                        st.subheader("To use a different waterway map instead:")
                        upload_own_checkbox = st.checkbox("Use Custom Waterway Map")
                        choose_other_checkbox = st.checkbox("Use Alternative Waterway Map")

                        if upload_own_checkbox:
                            asset_id = st.text_input(
                                "Enter GEE Asset Table ID (e.g., projects/ee-beaver-lab/assets/Hydro/MA_Hydro_arc):"
                            )
                            if st.button("Load Custom Dataset"):
                                try:
                                    waterway_own = ee.FeatureCollection(asset_id)
                                    st.session_state.step2_complete = True
                                    st.session_state.selected_waterway = waterway_own
                                    st.session_state.dataset_loaded = True
                                    st.success("Custom dataset successfully loaded.")
                                except Exception as e:
                                    st.error(f"Failed to load dataset: {e}")

                        if choose_other_checkbox:
                            dataset_option = st.selectbox("Select alternative map:", ["WWF Free Flowing Rivers"])

                            if st.button("Load Alternative Map"):
                                try:
                                    if dataset_option == "WWF Free Flowing Rivers":
                                        wwf_dataset = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers")
                                        clipped_wwf = wwf_dataset.filterBounds(states_with_dams)
                                        st.session_state.selected_waterway = clipped_wwf
                                        st.session_state.step2_complete = True
                                        st.success("WWF dataset successfully loaded.")
                                except Exception as e:
                                    st.error(f"Failed to load dataset: {e}")

                        if st.session_state.step2_complete:
                            st.success("Waterway map loaded successfully.")
                    else:
                        st.error("No NHD datasets found for the selected states.")
            except Exception as e:
                st.error(f"Error loading dataset: {e}")
        else:
            st.error("Please complete Step 1 first.")

    with st.expander(
        "Step 3: Validate Dam Locations", expanded=st.session_state.step2_complete and not st.session_state.step3_complete
    ):
        st.header("Step 3: Validate Dam Locations")

        # Only show validation section if validation is not complete
        if not st.session_state.validation_complete:
            # Add validation parameters
            max_distance = st.number_input(
                "Maximum allowed distance from waterway (meters):", min_value=0, value=50, step=10, key="max_distance_input"
            )

            # Validate positive dams
            if "Full_positive" in st.session_state and "Waterway" in st.session_state:
                if st.button("Validate Dam Locations"):
                    with st.spinner("Validating dam locations..."):
                        try:
                            # Check if inputs are valid
                            if not st.session_state["Full_positive"] or not st.session_state["Waterway"]:
                                st.error("Invalid input data: feature collection or waterway data is missing")
                            else:
                                # Perform distance validation
                                distance_validation = validate_dam_waterway_distance(
                                    st.session_state["Full_positive"], st.session_state["Waterway"], max_distance
                                )

                                # Perform intersection validation
                                intersection_validation = check_waterway_intersection(
                                    st.session_state["Full_positive"], st.session_state["Waterway"]
                                )

                                # Combine validation results
                                validation_results = {
                                    "valid_dams": distance_validation["valid_dams"],
                                    "invalid_dams": distance_validation["invalid_dams"],
                                    "invalid_dams_info": distance_validation["invalid_dams_info"],
                                    "total_dams": st.session_state["Full_positive"].size(),
                                    "valid_count": distance_validation["valid_count"],
                                    "invalid_count": distance_validation["invalid_count"],
                                }

                                # Store validation results in session state
                                st.session_state["validation_results"] = validation_results
                                st.session_state["validation_step"] = "show_options"
                                st.session_state.step3_complete = True
                                # Display validation report
                                st.subheader("Validation Report")
                                st.text(generate_validation_report(validation_results))

                                # Display validation map
                                st.subheader("Validation Map")
                                validation_map = visualize_validation_results(
                                    st.session_state["Full_positive"], st.session_state["Waterway"], validation_results
                                )
                                validation_map.to_streamlit(width=MAP_WIDTH, height=MAP_HEIGHT)

                        except Exception as e:
                            st.error(f"Error during validation: {str(e)}")

        # Show options after validation is complete
        if st.session_state.validation_step == "show_options":
            if "validation_results" in st.session_state:
                validation_results = st.session_state["validation_results"]
                valid_count = validation_results["valid_count"].getInfo()
                invalid_count = validation_results["invalid_count"].getInfo()

                if valid_count == 0:
                    st.error("No valid dam locations found. All dams failed validation.")
                    st.write("Please check your dam locations and waterway data.")
                elif invalid_count > 0:
                    st.warning(
                        "Some dam locations have been identified as potentially invalid. Please review the validation report and map above. You can continue with all dams or only use the valid dams."
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Continue with all dams", key="use_all_dams_btn"):
                            st.session_state.validation_complete = True
                            st.session_state.use_all_dams = True
                            st.session_state.Dam_data = st.session_state["Full_positive"]
                            st.session_state.show_non_dam_section = True
                            st.session_state.validation_step = "completed"
                            st.success("✅ Selected to continue with all dams.")
                    with col2:
                        if st.button("Only use valid dams"):
                            valid_dams = validation_results["valid_dams"]
                            valid_count = validation_results["valid_count"].getInfo()

                            if valid_count > 0:
                                st.session_state["Full_positive"] = valid_dams
                                st.session_state.validation_step = "completed"
                                st.session_state.validation_complete = True
                                st.session_state.use_all_dams = False
                                st.session_state.Dam_data = valid_dams
                                st.session_state.show_non_dam_section = True
                                st.success(f"✅ Successfully filtered to {valid_count} valid dams.")
                            else:
                                st.warning("No valid dams found. Please adjust the validation criteria.")
                else:
                    st.session_state.validation_complete = True
                    st.session_state.use_all_dams = True
                    st.session_state.Dam_data = st.session_state["Full_positive"]
                    st.session_state.show_non_dam_section = True
                    st.session_state.validation_step = "completed"
                    st.success("✅ All dams are valid.")
            else:
                st.error("No validation results found. Please run validation first.")

    with st.expander(
        "Step 4: Upload or Generate Non-Dam Locations",
        expanded=st.session_state.step3_complete and not st.session_state.step4_complete,
    ):
        st.header("Step 4: Upload or Generate Non-Dam Locations")

        # Check required states
        if not st.session_state.get("validation_complete", False):
            st.error("Please complete the validation step first.")
        elif not st.session_state.get("show_non_dam_section", False):
            st.error("Please complete the validation step first.")
        else:
            if st.session_state.use_all_dams:
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
                    with st.spinner("Processing uploaded non-dam data..."):
                        try:
                            # Changed from upload_points_to_ee to upload_non_dam_points_to_ee
                            # This will use the date from dam data and not ask user to select a year
                            negative_feature_collection = upload_non_dam_points_to_ee(
                                uploaded_negatives, widget_prefix="NonDam"
                            )
                            if negative_feature_collection:
                                # Process negative sample data
                                from service.common_utilities import set_feature_ids_with_date_fallback

                                Neg_points_id = set_feature_ids_with_date_fallback(
                                    negative_feature_collection,
                                    "N",
                                    st.session_state.Positive_collection,
                                    dam_status="negative",
                                )

                                # Process positive samples
                                if not st.session_state.use_all_dams:
                                    Pos_collection = st.session_state.Dam_data
                                else:
                                    Pos_collection = st.session_state.Positive_collection

                                Pos_collection = Pos_collection.map(lambda feature: feature.set("Dam", "positive"))

                                Positive_dam_id = set_feature_ids_with_date_fallback(
                                    Pos_collection, "P", st.session_state.Positive_collection
                                )

                                # Create merged collection
                                Merged_collection = Positive_dam_id.merge(Neg_points_id)
                                st.session_state.Merged_collection = Merged_collection

                                # Set state variables
                                st.session_state.Negative_upload_collection = negative_feature_collection
                                st.session_state["Full_negative"] = st.session_state.Negative_upload_collection
                                st.session_state.buffer_complete = True
                                st.session_state.step4_complete = True
                                st.success("✅ Non-dam locations uploaded successfully!")

                                # Display data preview
                                st.subheader("Data Preview")
                                preview_map = geemap.Map()
                                preview_map.add_basemap("SATELLITE")
                                preview_map.addLayer(Neg_points_id, {"color": "red"}, "Non-dam locations")
                                preview_map.addLayer(Positive_dam_id, {"color": "blue"}, "Dam locations")
                                preview_map.centerObject(Merged_collection)
                                preview_map.to_streamlit(width=800, height=600)
                        except Exception as e:
                            st.error(f"Error processing file: {str(e)}")
                            st.error(traceback.format_exc())  # Show detailed error information

            if generate_negatives_checkbox:
                st.subheader("Specify the parameters for negative point generation:")
                st.image("assets/Negative_sampling_image.png")
                innerRadius = st.number_input(
                    "Inner Radius (meters)", value=300, min_value=0, step=50, key="inner_radius_input"
                )
                outerRadius = st.number_input(
                    "Outer Radius (meters)", value=500, min_value=0, step=50, key="outer_radius_input"
                )
                samplingScale = 10

                if st.button("Generate Negative Points"):
                    with st.spinner("Generating negative points..."):
                        try:
                            # Check required session state variables
                            if "Positive_collection" not in st.session_state:
                                st.error("Positive dam data not found. Please complete Step 1 first.")
                                st.stop()

                            if "selected_waterway" not in st.session_state:
                                st.error("Waterway data not found. Please complete Step 2 first.")
                                st.stop()

                            # Get the first positive dam for date
                            if not st.session_state.use_all_dams:
                                if "Dam_data" not in st.session_state:
                                    st.error("Dam data not found. Please complete previous steps first.")
                                    st.stop()
                                positive_dams_fc = st.session_state.Dam_data
                            else:
                                positive_dams_fc = st.session_state.Positive_collection

                            # Check if we have valid data
                            if positive_dams_fc.size().getInfo() == 0:
                                st.error("No valid dam data found. Please check your data and try again.")
                                st.stop()

                            # Get the bounds of positive dams
                            positive_bounds = positive_dams_fc.geometry().bounds()

                            # Check if bounds are valid with error margin
                            bounds_area = positive_bounds.area(1).getInfo()

                            if bounds_area == 0:
                                st.error("No valid dam locations found. Please check your data.")
                                st.stop()

                            # Clip waterway to positive dams bounds
                            waterway_fc = st.session_state.selected_waterway.filterBounds(positive_bounds)

                            # Check if waterway data is available
                            if waterway_fc.size().getInfo() == 0:
                                st.error(
                                    "No waterway data found within the dam locations area. Please check your waterway selection."
                                )
                                st.stop()

                            hydroRaster = prepareHydro(waterway_fc)

                            # Generate negative points
                            negativePoints = sampleNegativePoints(
                                positive_dams_fc, hydroRaster, innerRadius, outerRadius, samplingScale
                            )

                            # Check if negative points were generated
                            if negativePoints.size().getInfo() == 0:
                                st.error("No negative points were generated. Please try adjusting the parameters.")
                                st.stop()

                            # Get date from first positive dam
                            first_pos = positive_dams_fc.first()
                            date = ee.Date(first_pos.get("date"))
                            if not date:
                                st.error("No valid date found in the positive dam data. Please check your data.")
                                st.stop()

                            year_string = date.format("YYYY")
                            full_date = ee.String(year_string).cat("-07-01")

                            # Process negative points with proper error handling
                            try:
                                negativePoints = negativePoints.map(
                                    lambda feature: feature.set("Dam", "negative").set("date", full_date)
                                )
                            except Exception as e:
                                st.error(f"Error setting properties for negative points: {e}")
                                st.stop()

                            # Process negative points
                            from service.common_utilities import set_feature_ids

                            Neg_points_id = set_feature_ids(negativePoints, "N")

                            # Use filtered positive dams if only valid dams are selected
                            if not st.session_state.use_all_dams:
                                Pos_collection = st.session_state.Dam_data
                            else:
                                Pos_collection = st.session_state.Positive_collection

                            Pos_collection = Pos_collection.map(lambda feature: feature.set("Dam", "positive"))

                            Positive_dam_id = set_feature_ids(Pos_collection, "P")
                            Merged_collection = Positive_dam_id.merge(Neg_points_id)
                            st.session_state.Merged_collection = Merged_collection
                            st.session_state.buffer_complete = True
                            st.session_state.step4_complete = True
                            # Create and display the map
                            Negative_points = geemap.Map()
                            Negative_points.add_basemap("SATELLITE")
                            Negative_points.addLayer(negativePoints, {"color": "red", "width": 2}, "Negative")
                            Negative_points.addLayer(Positive_dam_id, {"color": "blue"}, "Positive")
                            Negative_points.centerObject(Merged_collection)
                            Negative_points.to_streamlit(width=MAP_WIDTH, height=MAP_HEIGHT)

                            # Set completion status
                            st.success("✅ Negative points generated successfully!")
                        except Exception as e:
                            st.error(f"Error generating negative points: {str(e)}")

    with st.expander(
        "Step 5: Create Buffers", expanded=st.session_state.step4_complete and not st.session_state.step5_complete
    ):
        st.header("Step 5: Create Buffers")

        # Check if step 4 is completed
        if not st.session_state.get("step4_complete", False):
            st.error("Please complete Step 4 first.")
        # Check if merged collection exists
        elif "Merged_collection" not in st.session_state:
            st.error("No merged data found. Please complete Step 4 first.")
        else:
            # Display buffer settings
            st.subheader("Buffer Settings")
            buffer_radius = st.number_input(
                "Enter buffer radius (meters). We will analyze locations within this buffer that are no more than 3m in elevation away from the dam location.",
                min_value=1,
                step=1,
                value=st.session_state.buffer_radius,
                key="buffer_radius_input",
            )

            if st.button("Create Buffers"):
                with st.spinner("Creating buffers..."):
                    try:
                        # Get date from first positive dam
                        first_pos = st.session_state.Positive_collection.first()
                        date = ee.Date(first_pos.get("date"))
                        year_string = date.format("YYYY")
                        full_date = ee.String(year_string).cat("-07-01")

                        # Create buffers
                        Buffered_collection = st.session_state.Merged_collection.map(
                            lambda feature: add_dam_buffer_and_standardize_date(feature, buffer_radius)
                        )

                        # Select relevant properties
                        Dam_data = Buffered_collection.select(["id_property", "Dam", "Survey_Date", "Damdate", "Point_geo"])

                        # Save to session state
                        st.session_state.Dam_data = Dam_data
                        st.session_state.buffers_created = True

                        # Split into positive and negative points
                        Negative = Dam_data.filter(ee.Filter.eq("Dam", "negative"))
                        Positive = Dam_data.filter(ee.Filter.eq("Dam", "positive"))

                        # Display buffer preview
                        st.subheader("Buffer Preview")
                        Buffer_map = geemap.Map()
                        Buffer_map.add_basemap("SATELLITE")
                        Buffer_map.addLayer(Negative, {"color": "red"}, "Negative")
                        Buffer_map.addLayer(Positive, {"color": "blue"}, "Positive")
                        Buffer_map.centerObject(Dam_data)
                        Buffer_map.to_streamlit(width=800, height=600)

                        # Set completion status
                        st.session_state.step5_complete = True

                        st.success(f"✅ Buffers created successfully with radius {buffer_radius} meters!")

                    except Exception as e:
                        st.error(f"Error creating buffers: {str(e)}")

    with st.expander("Step 6: Visualize Trends", expanded=st.session_state.step5_complete):
        st.header("Step 6: Visualize Trends")

        if not st.session_state.get("step5_complete", False):
            st.error("Please complete Step 5 first.")
        else:
            tab1, tab2 = st.tabs(["Combined Analysis", "Upstream & Downstream Analysis"])

            with tab1:
                if not st.session_state.visualization_complete:
                    if st.button("Analyze Combined Effects"):
                        with st.spinner("Analyzing combined effects..."):
                            try:
                                Dam_data = st.session_state.Dam_data

                                def validate_date(feature):
                                    try:
                                        date = feature.get("Survey_Date")
                                        if not date:
                                            date = feature.get("date")
                                            if not date:
                                                st.error("Find no date in the data. Please check your data.")
                                                return None

                                        standardized_date = ee.Date(date)
                                        return feature
                                    except Exception as e:
                                        st.error(f"Date validation error: {str(e)}")
                                        return None

                                Dam_data = Dam_data.map(validate_date).filter(ee.Filter.notNull(["Survey_Date"]))

                                if Dam_data.size().getInfo() == 0:
                                    st.error("No valid data with dates found. Please check your data.")
                                    st.stop()

                                def process_batch_for_export(batch_collection):
                                    # Process this batch through the entire pipeline
                                    S2_cloud_mask_batch = ee.ImageCollection(S2_Export_for_visual(batch_collection))
                                    S2_ImageCollection_batch = ee.ImageCollection(S2_cloud_mask_batch)
                                    S2_with_LST_batch = S2_ImageCollection_batch.map(add_landsat_lst_et)
                                    results_fc_lst_batch = S2_with_LST_batch.map(compute_all_metrics_LST_ET)
                                    return ee.FeatureCollection(results_fc_lst_batch)

                                df_lst = process_to_dataframe(
                                    collection=Dam_data,
                                    processing_function=process_batch_for_export,
                                    batch_size=LARGE_BATCH_SIZE,
                                    progress_label="Processing dam points for export",
                                )

                                if df_lst.empty:
                                    st.error("Error Message: No data could be processed from any batch.")
                                    st.stop()

                                df_lst["Image_month"] = pd.to_numeric(df_lst["Image_month"])
                                df_lst["Image_year"] = pd.to_numeric(df_lst["Image_year"])
                                df_lst["Dam_status"] = df_lst["Dam_status"].replace(
                                    {"positive": "Dam", "negative": "Non-dam"}
                                )

                                fig, axes = plt.subplots(4, 1, figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT_SMALL))

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
                                st.session_state.fig = fig
                                st.session_state.df_lst = df_lst
                                st.session_state.visualization_complete = True
                                st.success("✅ Visualization complete!")

                            except Exception as e:
                                st.error(f"Visualization error: {e}")
                                st.code(traceback.format_exc())

                if st.session_state.visualization_complete:
                    st.pyplot(st.session_state.fig)
                    col1, col2 = st.columns(2)

                    with col1:
                        buf = io.BytesIO()
                        st.session_state.fig.savefig(buf, format="png")
                        buf.seek(0)
                        st.download_button("Download Combined Figures", buf, "combined_trends.png", "image/png")

                    with col2:
                        # Create export DataFrame with coordinates
                        if st.session_state.df_lst is not None and "Dam_data" in st.session_state:
                            export_df = st.session_state.df_lst.copy()

                            # Extract coordinates and merge with main data
                            coords_df = extract_coordinates_df(st.session_state.Dam_data)

                            if not coords_df.empty:

                                if "id_property" in export_df.columns:
                                    # Check for matching id_property values
                                    export_ids = set(export_df["id_property"].unique())
                                    coord_ids = set(coords_df["id_property"].unique())

                                    # Find missing IDs
                                    missing_in_coords = export_ids - coord_ids
                                    if missing_in_coords:
                                        st.warning(f"Missing coordinates for IDs: {list(missing_in_coords)[:5]}...")

                                    # Merge using id_property
                                    export_df = export_df.merge(coords_df, on="id_property", how="left")

                                    # Check for NaN values
                                    nan_coords = export_df[export_df["longitude"].isna()].shape[0]
                                    if nan_coords > 0:
                                        st.warning(f"{nan_coords} rows could not be matched with coordinates")
                                        st.write("Sample of rows with missing coordinates:")
                                        st.write(export_df[export_df["longitude"].isna()].head())

                                    # Fill NaN values with 0
                                    export_df["longitude"] = export_df["longitude"].fillna(0)
                                    export_df["latitude"] = export_df["latitude"].fillna(0)

                                else:
                                    st.error("Export DataFrame missing 'id_property' column")
                                    st.write("Export DataFrame columns:", export_df.columns)
                            else:
                                st.warning("No coordinates were extracted from the features")
                                # Add placeholder columns
                                export_df["longitude"] = 0
                                export_df["latitude"] = 0
                        else:
                            st.error("Export DataFrame or Dam_data not found in session state")
                            export_df = st.session_state.df_lst.copy()
                            export_df["longitude"] = 0
                            export_df["latitude"] = 0

                        csv = export_df.to_csv(index=False).encode("utf-8")
                        st.download_button("Download Combined Data (CSV)", csv, "combined_data.csv", "text/csv")
            with tab2:
                if "upstream_analysis_complete" not in st.session_state:
                    st.session_state.upstream_analysis_complete = False

                if not st.session_state.upstream_analysis_complete:
                    if st.button("Analyze Upstream & Downstream Effects"):
                        with st.spinner("Analyzing Upstream & Downstream..."):
                            try:
                                if "Dam_data" not in st.session_state or "Waterway" not in st.session_state:
                                    st.error(
                                        "Required data (Dam locations or Waterway) not found. Please complete previous steps."
                                    )
                                else:
                                    Dam_data = st.session_state.Dam_data
                                    waterway_fc = st.session_state.Waterway

                                    def process_batch_with_upstream_downstream(batch_collection):
                                        # Process this batch through the entire pipeline
                                        S2_IC_batch = S2_Export_for_visual_flowdir(batch_collection, waterway_fc)
                                        S2_with_LST_ET = S2_IC_batch.map(add_landsat_lst_et)
                                        results_batch = S2_with_LST_ET.map(compute_all_metrics_up_downstream)
                                        return ee.FeatureCollection(results_batch)

                                    final_df = process_to_dataframe(
                                        collection=Dam_data,
                                        processing_function=process_batch_with_upstream_downstream,
                                        batch_size=LARGE_BATCH_SIZE,
                                        progress_label="Processing upstream/downstream analysis",
                                    )

                                    if final_df.empty:
                                        st.error("All batches failed processing. Please check your data.")
                                        st.stop()

                                    final_df["Dam_status"] = final_df["Dam_status"].replace(
                                        {"positive": "Dam", "negative": "Non-dam"}
                                    )
                                    st.session_state.final_df = final_df

                                    # Create visualization
                                    fig2, axes2 = plt.subplots(4, 1, figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT_LARGE))

                                    def melt_and_plot(df, metric, ax):
                                        melted = df.melt(
                                            ["Image_year", "Image_month", "Dam_status"],
                                            [f"{metric}_up", f"{metric}_down"],
                                            "Flow",
                                            metric,
                                        )
                                        melted["Flow"].replace(
                                            {f"{metric}_up": "Upstream", f"{metric}_down": "Downstream"}, inplace=True
                                        )
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
                                    st.session_state.fig2 = fig2
                                    st.session_state.upstream_analysis_complete = True
                                    st.pyplot(fig2)
                                    st.success("✅ Upstream & downstream analysis completed successfully!")

                                    # Add download buttons
                                    col3, col4 = st.columns(2)
                                    with col3:
                                        buf2 = io.BytesIO()
                                        fig2.savefig(buf2, format="png")
                                        buf2.seek(0)
                                        st.download_button(
                                            "Download Up/Downstream Figures",
                                            buf2,
                                            "up_downstream.png",
                                            "image/png",
                                            key="download_updown_fig",
                                        )

                                    with col4:
                                        if "final_df" in st.session_state and st.session_state.final_df is not None:
                                            # Create export DataFrame with coordinates
                                            export_df = st.session_state.final_df.copy()

                                            # Extract coordinates and merge with main data
                                            if "Dam_data" in st.session_state:
                                                coords_df = extract_coordinates_df(st.session_state.Dam_data)

                                                if not coords_df.empty:
                                                    # Calculate number of months per point
                                                    months_per_point = len(export_df) // len(coords_df)

                                                    # Create a list to store coordinates
                                                    longitudes = []
                                                    latitudes = []

                                                    # Assign coordinates to each point's data
                                                    for i in range(len(coords_df)):
                                                        coords = coords_df.iloc[i]
                                                        # Add coordinates for each month
                                                        for _ in range(months_per_point):
                                                            longitudes.append(coords["longitude"])
                                                            latitudes.append(coords["latitude"])

                                                    # Add coordinates to export_df
                                                    export_df["longitude"] = longitudes
                                                    export_df["latitude"] = latitudes

                                                else:
                                                    st.warning("No coordinates were extracted from the features")
                                                    # Add placeholder columns
                                                    export_df["longitude"] = 0
                                                    export_df["latitude"] = 0
                                            else:
                                                st.error("Dam_data not found in session state")
                                                # Add placeholder columns
                                                export_df["longitude"] = 0
                                                export_df["latitude"] = 0

                                            csv2 = export_df.to_csv(index=False).encode("utf-8")
                                            st.download_button(
                                                "Download Up/Downstream Data (CSV)",
                                                csv2,
                                                "updown_data.csv",
                                                "text/csv",
                                                key="download_updown_csv",
                                            )
                            except Exception as e:
                                st.error(f"Analysis error: {e}")
                                st.code(traceback.format_exc())

                # Display existing results if already computed
                elif st.session_state.upstream_analysis_complete and "fig2" in st.session_state:
                    st.pyplot(st.session_state.fig2)

                    col3, col4 = st.columns(2)
                    with col3:
                        buf2 = io.BytesIO()
                        st.session_state.fig2.savefig(buf2, format="png")
                        buf2.seek(0)
                        st.download_button(
                            "Download Up/Downstream Figures",
                            buf2,
                            "up_downstream.png",
                            "image/png",
                            key="redisplay_updown_fig",
                        )

                    with col4:
                        if "final_df" in st.session_state and st.session_state.final_df is not None:
                            # Create export DataFrame with coordinates
                            export_df = st.session_state.final_df.copy()

                            # Extract coordinates and merge with main data
                            if "Dam_data" in st.session_state:
                                coords_df = extract_coordinates_df(st.session_state.Dam_data)

                                if not coords_df.empty:
                                    # Create a list to store coordinates
                                    longitudes = []
                                    latitudes = []

                                    # Assign coordinates to each point's data
                                    for i in range(len(coords_df)):
                                        coords = coords_df.iloc[i]
                                        # Add coordinates for each month
                                        for _ in range(months_per_point):
                                            longitudes.append(coords["longitude"])
                                            latitudes.append(coords["latitude"])

                                    # Add coordinates to export_df
                                    export_df["longitude"] = longitudes
                                    export_df["latitude"] = latitudes

                                else:
                                    st.warning("No coordinates were extracted from the features")
                                    # Add placeholder columns
                                    export_df["longitude"] = 0
                                    export_df["latitude"] = 0
                            else:
                                st.error("Dam_data not found in session state")
                                # Add placeholder columns
                                export_df["longitude"] = 0
                                export_df["latitude"] = 0

                            csv2 = export_df.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "Download Up/Downstream Data (CSV)",
                                csv2,
                                "updown_data.csv",
                                "text/csv",
                                key="download_updown_csv",
                            )

                    st.success("Upstream & downstream analysis data loaded from session.")
    st.info(
        "You can make the Beaver Impacts Tool better by filling out our [feedback form](https://docs.google.com/forms/d/e/1FAIpQLSeE1GP7OptA4-z8Melz2AHxNsddtL9ZgJVXdVVtxLsrljJ10Q/viewform?usp=sharing)."
    )
