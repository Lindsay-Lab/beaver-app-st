"""
Session State Management for Beaver Impacts Analysis Application.

This module provides centralized management of Streamlit session state variables
for the beaver dam impact analysis workflow. It handles initialization of all
application state including user progress, data collections, configuration
settings, and UI flags.

The session state is organized into several categories:
- Questionnaire and survey tracking
- Data collections (dam locations, waterways, analysis results)
- Workflow progress and step completion
- Configuration values (buffer sizes, validation parameters)
- UI state (map visibility, section expansion)

Classes:
    SessionStateManager: Static methods for initializing and managing session state

Usage:
    from session_state import SessionStateManager

    # Initialize all session state variables at app startup
    SessionStateManager.initialize()

    # Reset workflow state when starting over
    SessionStateManager.reset_workflow()

Note:
    This module depends on constants.py for default values and assumes
    Streamlit's session_state is available in the global context.
"""
import streamlit as st

from service.constants import AppConstants


class SessionStateManager:
    @staticmethod
    def initialize():
        """Initialize all session state variables."""
        SessionStateManager._init_basic_state()
        SessionStateManager._init_step_completion()

    @staticmethod
    def _init_basic_state():
        for key, default_value in AppConstants.SESSION_DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    @staticmethod
    def _init_step_completion():
        for i in range(1, 7):
            step_key = f"step{i}_complete"
            if step_key not in st.session_state:
                st.session_state[step_key] = False

    @staticmethod
    def reset_workflow():
        """Reset workflow-related state (useful for starting over)."""
        workflow_keys = [
            "validation_complete", "buffer_complete", "buffers_created",
            "visualization_complete", "show_non_dam_section"
        ]
        for key in workflow_keys:
            st.session_state[key] = False

        for i in range(1, 7):
            st.session_state[f"step{i}_complete"] = False