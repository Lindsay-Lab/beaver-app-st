"""
Earth Engine Authentication Module

Centralized authentication for Google Earth Engine to eliminate code duplication
across the application.
"""

import ee
import streamlit as st
from google.oauth2 import service_account


def get_credentials():
    """
    Get Google Earth Engine credentials from Streamlit secrets.

    Returns:
        google.oauth2.service_account.Credentials: Configured credentials object
    """
    credentials_info = {
        "type": st.secrets["gcp_service_account"]["type"],
        "project_id": st.secrets["gcp_service_account"]["project_id"],
        "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
        "private_key": st.secrets["gcp_service_account"]["private_key"],
        "client_email": st.secrets["gcp_service_account"]["client_email"],
        "client_id": st.secrets["gcp_service_account"]["client_id"],
        "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
        "token_uri": st.secrets["gcp_service_account"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"],
        "universe_domain": st.secrets["gcp_service_account"]["universe_domain"],
    }

    return service_account.Credentials.from_service_account_info(
        credentials_info, scopes=["https://www.googleapis.com/auth/earthengine"]
    )


def initialize_earth_engine():
    """
    Initialize Google Earth Engine with the configured credentials.

    This function handles the complete Earth Engine initialization process
    including credential retrieval and project setup.
    """
    credentials = get_credentials()
    ee.Initialize(credentials, project="ee-beaver-lab")
