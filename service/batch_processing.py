"""
Batch Processing Utilities

Standardized batch processing functions to handle Earth Engine memory limits
and provide consistent progress reporting across the application.
"""

import ee
import geemap.foliumap as geemap
import pandas as pd
import streamlit as st

from .constants import DEFAULT_BATCH_SIZE, LARGE_BATCH_SIZE


def process_in_batches(
    collection,
    processing_function,
    batch_size=DEFAULT_BATCH_SIZE,
    show_progress=True,
    progress_label="Processing batches",
):
    """
    Process an Earth Engine FeatureCollection in batches to avoid memory limits.

    Args:
        collection: Earth Engine FeatureCollection to process
        processing_function: Function to apply to each batch (should accept ee.FeatureCollection)
        batch_size: Number of features to process per batch
        show_progress: Whether to show Streamlit progress bar
        progress_label: Label for the progress bar

    Returns:
        List of results from processing_function applied to each batch
    """
    total_count = collection.size().getInfo()

    if total_count == 0:
        if show_progress:
            st.warning("No features to process")
        return []

    num_batches = (total_count + batch_size - 1) // batch_size
    results = []

    if show_progress:
        st.write(f"Processing {total_count} features in {num_batches} batches of {batch_size}")
        progress_bar = st.progress(0)

    for i in range(num_batches):
        # Get batch of features
        batch_features = collection.toList(batch_size, i * batch_size)
        batch_collection = ee.FeatureCollection(batch_features)

        # Process the batch
        try:
            batch_result = processing_function(batch_collection)
            results.append(batch_result)

            if show_progress:
                progress_bar.progress((i + 1) / num_batches)

        except Exception as e:
            st.error(f"Error processing batch {i + 1}: {str(e)}")
            if show_progress:
                progress_bar.progress((i + 1) / num_batches)

    if show_progress:
        st.success(f"Completed processing {len(results)} batches")

    return results


def process_to_dataframe(
    collection,
    processing_function,
    batch_size=DEFAULT_BATCH_SIZE,
    show_progress=True,
    progress_label="Processing to DataFrame",
):
    """
    Process an Earth Engine FeatureCollection in batches and combine results into a DataFrame.

    Args:
        collection: Earth Engine FeatureCollection to process
        processing_function: Function to apply to each batch (should return ee.FeatureCollection)
        batch_size: Number of features to process per batch
        show_progress: Whether to show Streamlit progress bar
        progress_label: Label for the progress bar

    Returns:
        pandas.DataFrame: Combined results from all batches
    """
    total_count = collection.size().getInfo()

    if total_count == 0:
        if show_progress:
            st.warning("No features to process")
        return pd.DataFrame()

    num_batches = (total_count + batch_size - 1) // batch_size
    df_list = []

    if show_progress:
        st.write(f"Processing {total_count} features in {num_batches} batches of {batch_size}")
        progress_bar = st.progress(0)

    for i in range(num_batches):
        # Get batch of features
        batch_features = collection.toList(batch_size, i * batch_size)
        batch_collection = ee.FeatureCollection(batch_features)

        # Process the batch
        try:
            batch_result = processing_function(batch_collection)

            # Convert to DataFrame
            df_batch = geemap.ee_to_df(batch_result)
            df_list.append(df_batch)

            if show_progress:
                progress_bar.progress((i + 1) / num_batches)

        except Exception as e:
            st.error(f"Error processing batch {i + 1}: {str(e)}")
            if show_progress:
                progress_bar.progress((i + 1) / num_batches)

    if show_progress:
        st.success(f"Completed processing {len(df_list)} batches")

    # Combine all DataFrames
    if df_list:
        return pd.concat(df_list, ignore_index=True)
    else:
        return pd.DataFrame()


def process_large_collection(
    collection,
    processing_function,
    show_progress=True,
    progress_label="Processing large collection",
):
    """
    Process a large Earth Engine FeatureCollection using larger batch sizes.

    Args:
        collection: Earth Engine FeatureCollection to process
        processing_function: Function to apply to each batch
        show_progress: Whether to show Streamlit progress bar
        progress_label: Label for the progress bar

    Returns:
        List of results from processing_function applied to each batch
    """
    return process_in_batches(
        collection=collection,
        processing_function=processing_function,
        batch_size=LARGE_BATCH_SIZE,
        show_progress=show_progress,
        progress_label=progress_label,
    )


def process_with_error_handling(
    collection,
    processing_function,
    batch_size=DEFAULT_BATCH_SIZE,
    show_progress=True,
    progress_label="Processing with error handling",
    continue_on_error=True,
):
    """
    Process an Earth Engine FeatureCollection in batches with robust error handling.

    Args:
        collection: Earth Engine FeatureCollection to process
        processing_function: Function to apply to each batch
        batch_size: Number of features to process per batch
        show_progress: Whether to show Streamlit progress bar
        progress_label: Label for the progress bar
        continue_on_error: Whether to continue processing if a batch fails

    Returns:
        tuple: (successful_results, failed_batches)
    """
    total_count = collection.size().getInfo()

    if total_count == 0:
        if show_progress:
            st.warning("No features to process")
        return [], []

    num_batches = (total_count + batch_size - 1) // batch_size
    successful_results = []
    failed_batches = []

    if show_progress:
        st.write(f"Processing {total_count} features in {num_batches} batches of {batch_size}")
        progress_bar = st.progress(0)

    for i in range(num_batches):
        # Get batch of features
        batch_features = collection.toList(batch_size, i * batch_size)
        batch_collection = ee.FeatureCollection(batch_features)

        # Process the batch
        try:
            batch_result = processing_function(batch_collection)
            successful_results.append(batch_result)

        except Exception as e:
            error_msg = f"Error processing batch {i + 1}: {str(e)}"
            failed_batches.append({"batch_index": i, "error": str(e)})

            if continue_on_error:
                st.warning(error_msg)
            else:
                st.error(error_msg)
                if show_progress:
                    progress_bar.progress((i + 1) / num_batches)
                break

        if show_progress:
            progress_bar.progress((i + 1) / num_batches)

    if show_progress:
        if failed_batches:
            st.warning(
                f"Completed with {len(successful_results)} successful batches and {len(failed_batches)} failed batches"
            )
        else:
            st.success(f"Completed processing {len(successful_results)} batches successfully")

    return successful_results, failed_batches
