import ee
import geemap.foliumap as geemap
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from service.batch_processing import process_to_dataframe
from service.constants import (
    DEFAULT_BATCH_SIZE,
    PLOT_FIGURE_HEIGHT_LARGE,
    PLOT_FIGURE_HEIGHT_SMALL,
    PLOT_FIGURE_WIDTH,
    STATE_ABBREVIATIONS,
)
from service.Data_management import add_dam_buffer_and_standardize_date
from service.earth_engine_auth import initialize_earth_engine
from service.Negative_sample_functions import deduplicate_locations, prepareHydro, sampleNegativePoints
from service.Parser import upload_points_to_ee
from service.Visualize_trends import (
    S2_Export_for_visual,
    S2_Export_for_visual_flowdir,
    add_landsat_lst_et,
    compute_all_metrics_LST_ET,
    compute_all_metrics_up_downstream,
)

initialize_earth_engine()

st.title("Quick Analysis")

if "Dam_data" not in st.session_state:
    st.session_state.Dam_data = None
if "Buffer_map" not in st.session_state:
    st.session_state.Buffer_map = None
# Step 1: Data upload
uploaded_file = st.file_uploader("Upload Dam Locations (CSV or GeoJSON)", type=["csv", "geojson"])

if uploaded_file:
    with st.spinner("Uploading data..."):
        try:
            feature_collection = upload_points_to_ee(uploaded_file, widget_prefix="Dam")
            st.success("Dam locations uploaded successfully!")
            if feature_collection:
                # Preview uploaded points
                st.session_state.Positive_collection = feature_collection  # Save to session state
                st.session_state["Full_positive"] = st.session_state.Positive_collection

        except Exception as e:
            st.error(f"Error uploading data: {e}")
            data_confirmed = False
else:
    data_confirmed = False


if "Positive_collection" in st.session_state:
    st.header("Select Buffer Parameters")

    innerRadius = st.number_input("Inner Radius (meters)", value=200, min_value=0, step=50)
    outerRadius = st.number_input("Outer Radius (meters)", value=2000, min_value=0, step=100)
    buffer_radius = st.number_input("Buffer Radius (meters)", value=200, min_value=1, step=10)

    if st.button("Generate Buffer Map"):
        with st.spinner("Processing data..."):
            try:
                # Filter states by Dam bounding box
                positive_dam_bounds = st.session_state["Full_positive"].geometry().bounds()
                states_dataset = ee.FeatureCollection("TIGER/2018/States")
                states_with_dams = states_dataset.filterBounds(positive_dam_bounds)
                st.session_state["Positive_dam_state"] = states_with_dams
                states_geo = st.session_state["Positive_dam_state"]
                state_names = states_geo.aggregate_array("NAME").getInfo()

                nhd_collections = []
                for state in state_names:
                    state_initial = STATE_ABBREVIATIONS.get(state)
                    if state_initial:
                        nhd_dataset = ee.FeatureCollection(
                            f"projects/sat-io/open-datasets/NHD/NHD_{state_initial}/NHDFlowline"
                        )
                        nhd_collections.append(nhd_dataset)

                merged_nhd = ee.FeatureCollection(nhd_collections).flatten()
                st.session_state.selected_waterway = merged_nhd
                st.session_state["Waterway"] = merged_nhd

                st.session_state.Combined_collection = None

                first_pos = st.session_state.Positive_collection.first()
                date = ee.Date(first_pos.get("date"))
                year_string = date.format("YYYY")
                full_date = ee.String(year_string).cat("-07-01")

                positive_dams_fc = deduplicate_locations(st.session_state.Positive_collection)

                # Convert waterway feature collection to raster
                waterway_fc = st.session_state.selected_waterway
                hydroRaster = prepareHydro(waterway_fc)

                # Sample negative points
                negativePoints = sampleNegativePoints(positive_dams_fc, hydroRaster, innerRadius, outerRadius, 10)
                negativePoints = negativePoints.map(lambda feature: feature.set("Dam", "negative").set("date", full_date))

                from service.common_utilities import set_feature_ids

                Neg_points_id = set_feature_ids(negativePoints, "N")

                Pos_collection = st.session_state.Positive_collection.map(lambda feature: feature.set("Dam", "positive"))
                Positive_dam_id = set_feature_ids(Pos_collection, "P")
                Merged_collection = Positive_dam_id.merge(Neg_points_id)
                st.session_state["Merged_collection"] = Merged_collection

                Buffered_collection = Merged_collection.map(
                    lambda feature: add_dam_buffer_and_standardize_date(feature, buffer_radius, date)
                )
                Dam_data = Buffered_collection.select(["id_property", "Dam", "Survey_Date", "Damdate", "Point_geo"])
                st.session_state["Dam_data"] = Dam_data

                dam_bounds = Dam_data.geometry().bounds()
                states_with_dams = states_dataset.filterBounds(dam_bounds)
                st.session_state["Dam_state"] = states_with_dams

                Negative = Dam_data.filter(ee.Filter.eq("Dam", "negative"))
                Positive = Dam_data.filter(ee.Filter.eq("Dam", "positive"))

                # Create and store map in session_state
                Buffer_map = geemap.Map()
                Buffer_map.add_basemap("SATELLITE")
                Buffer_map.addLayer(Negative, {"color": "red"}, "Negative")
                Buffer_map.addLayer(Positive, {"color": "blue"}, "Positive")
                Buffer_map.centerObject(Dam_data)

                # Store the map object so it won't disappear
                st.session_state.Buffer_map = Buffer_map

                st.success("Buffer map generated successfully!")
            except Exception as e:
                st.error(f"Error generating buffer map: {e}")


# -------------------- Always Show the Buffer Map (if we have it) --------------------
if st.session_state.Buffer_map:
    st.subheader("Buffered Dam Map")
    st.session_state.Buffer_map.to_streamlit(width=800, height=600)


# -------------------- Visualization Buttons --------------------
if st.session_state["Dam_data"]:
    col1, col2 = st.columns(2)
    with col1:
        clicked_all_area = st.button("Visualize All Area")
    with col2:
        clicked_up_down = st.button("Visualize Upstream & Downstream")

    if clicked_all_area:
        with st.spinner("Processing visualization for all areas..."):
            try:

                Dam_data = st.session_state["Dam_data"]
                waterway_fc = st.session_state["Waterway"]

                def process_batch(batch_collection):
                    S2_IC_batch = S2_Export_for_visual(batch_collection)
                    results_batch = S2_IC_batch.map(add_landsat_lst_et).map(compute_all_metrics_LST_ET)
                    return ee.FeatureCollection(results_batch)

                final_df = process_to_dataframe(
                    collection=Dam_data,
                    processing_function=process_batch,
                    batch_size=DEFAULT_BATCH_SIZE,
                    progress_label="Processing visualization for all areas",
                )
                st.session_state.final_df = final_df

                # Convert to DataFrame
                final_df["Image_month"] = pd.to_numeric(final_df["Image_month"])
                final_df["Image_year"] = pd.to_numeric(final_df["Image_year"])
                final_df["Dam_status"] = final_df["Dam_status"].replace({"positive": "Dam", "negative": "Non-dam"})

                # --- Produce some charts ---
                # (Below is just your original logic; be sure to call st.pyplot(fig)!)

                fig, axes = plt.subplots(4, 1, figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT_SMALL))

                metrics = ["NDVI", "NDWI_Green", "LST", "ET"]
                titles = ["NDVI", "NDWI Green", "LST (°C)", "ET"]

                for ax, metric, title in zip(axes, metrics, titles):
                    sns.lineplot(
                        data=final_df,
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
                st.pyplot(fig)

            except Exception as e:
                st.error(f"Visualization error: {e}")

    if clicked_up_down:
        with st.spinner("Processing upstream and downstream visualization..."):
            try:
                Dam_data = st.session_state["Dam_data"]
                waterway_fc = st.session_state["Waterway"]

                def process_batch_with_flow(batch_collection):
                    S2_IC_batch = S2_Export_for_visual_flowdir(batch_collection, waterway_fc)
                    results_batch = S2_IC_batch.map(add_landsat_lst_et).map(compute_all_metrics_up_downstream)
                    return ee.FeatureCollection(results_batch)

                final_df = process_to_dataframe(
                    collection=Dam_data,
                    processing_function=process_batch_with_flow,
                    batch_size=DEFAULT_BATCH_SIZE,
                    progress_label="Processing upstream/downstream analysis",
                )
                st.session_state.final_df = final_df

                fig2, axes2 = plt.subplots(4, 1, figsize=(PLOT_FIGURE_WIDTH, PLOT_FIGURE_HEIGHT_LARGE))

                def melt_and_plot(df, metric, ax):
                    up_col = f"{metric}_up"
                    down_col = f"{metric}_down"
                    melted = df.melt(["Image_year", "Image_month", "Dam_status"], [up_col, down_col], "Flow", metric)
                    melted["Flow"].replace({up_col: "Upstream", down_col: "Downstream"}, inplace=True)
                    sns.lineplot(
                        data=melted,
                        x="Image_month",
                        y=metric,
                        hue="Dam_status",
                        style="Flow",
                        markers=True,
                        dashes=False,
                        ax=ax,
                    )
                    ax.set_title(f"{metric.upper()} by Month (Upstream vs Downstream)")
                    ax.set_xticks(range(1, 13))

                for ax, met in zip(axes2, ["NDVI", "NDWI", "LST", "ET"]):
                    melt_and_plot(final_df, met, ax)

                plt.tight_layout()
                st.pyplot(fig2)

            except Exception as e:
                st.error(f"Upstream/downstream visualization error: {e}")
