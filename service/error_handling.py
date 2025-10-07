"""Error handling utilities for the streamlit app"""

import traceback
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Any, Optional

import streamlit as st


def handle_processing_errors(operation_name: str, show_details: bool = True):
    """Decorator for consistent error handling with user-friendly messages"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                st.error(f"Error during {operation_name}: {str(e)}")
                if show_details:
                    with st.expander("Technical Details", expanded=False):
                        st.code(traceback.format_exc())
                return None

        return wrapper

    return decorator


@contextmanager
def safe_processing(operation_name: str, show_spinner: bool = True):
    """Context manager for operations with loading states and error handling"""
    try:
        if show_spinner:
            with st.spinner(f"{operation_name}..."):
                yield
        else:
            yield
    except Exception as e:
        st.error(f"Error during {operation_name}: {str(e)}")
        with st.expander("Technical Details", expanded=False):
            st.code(traceback.format_exc())
        raise


def display_validation_error(message: str, suggestions: Optional[list] = None):
    """Standardized validation error display"""
    st.error(message)
    if suggestions:
        st.info("Suggestions:")
        for suggestion in suggestions:
            st.write(f"• {suggestion}")


def display_success_message(message: str, details: Optional[str] = None):
    """Standardized success message display"""
    st.success(f"✅ {message}")
    if details:
        st.info(details)


def display_warning_with_options(message: str, options_dict: dict):
    """Display warning with action buttons"""
    st.warning(message)

    cols = st.columns(len(options_dict))
    results = {}

    for i, (button_text, key) in enumerate(options_dict.items()):
        with cols[i]:
            if st.button(button_text, key=key):
                results[key] = True
            else:
                results[key] = False

    return results


def handle_file_processing_error(filename: str, error: Exception):
    """Specialized error handling for file processing"""
    error_msg = str(error).lower()

    if "format" in error_msg or "parse" in error_msg:
        display_validation_error(
            f"File format error in '{filename}'",
            [
                "Check that your file is a valid CSV or GeoJSON",
                "Ensure coordinate columns are named correctly",
                "Verify the file isn't corrupted",
            ],
        )
    elif "coordinate" in error_msg or "geometry" in error_msg:
        display_validation_error(
            f"Coordinate error in '{filename}'",
            [
                "Check that coordinates are in decimal degrees",
                "Ensure latitude is between -90 and 90",
                "Ensure longitude is between -180 and 180",
            ],
        )
    elif "empty" in error_msg or "no data" in error_msg:
        display_validation_error(
            f"No valid data found in '{filename}'",
            ["Check that the file contains data rows", "Verify column headers match expected format"],
        )
    else:
        st.error(f"Error processing file '{filename}': {str(error)}")
        with st.expander("Technical Details", expanded=False):
            st.code(traceback.format_exc())
