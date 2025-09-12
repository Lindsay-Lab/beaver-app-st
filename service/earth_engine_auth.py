"""
Earth Engine Authentication Module

Centralized authentication for Google Earth Engine to eliminate code duplication
across the application. Supports multiple authentication methods for different
environments (production, testing, development).
"""

import json
import os

import ee
from google.oauth2 import service_account


class MockCredentials:
    """Mock credentials for testing without Earth Engine authentication."""

    def __init__(self):
        self.service_account_email = "test@test.com"
        self.token = "mock_token"

    def refresh(self, request):
        """Mock refresh method."""


def get_streamlit_credentials():
    """Get credentials from Streamlit secrets (production environment)."""
    import streamlit as st

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


def get_environment_credentials():
    """Get credentials from environment variables (testing/CI environment)."""
    # Method 1: Service account file path
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        return service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=["https://www.googleapis.com/auth/earthengine"]
        )

    # Method 2: Service account JSON string
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in os.environ:
        credentials_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return service_account.Credentials.from_service_account_info(
            credentials_info, scopes=["https://www.googleapis.com/auth/earthengine"]
        )

    # Method 3: Individual environment variables
    required_vars = ["GCP_PROJECT_ID", "GCP_PRIVATE_KEY", "GCP_CLIENT_EMAIL", "GCP_CLIENT_ID", "GCP_PRIVATE_KEY_ID"]

    if all(var in os.environ for var in required_vars):
        credentials_info = {
            "type": "service_account",
            "project_id": os.environ["GCP_PROJECT_ID"],
            "private_key_id": os.environ["GCP_PRIVATE_KEY_ID"],
            "private_key": os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["GCP_CLIENT_EMAIL"],
            "client_id": os.environ["GCP_CLIENT_ID"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ['GCP_CLIENT_EMAIL']}",
            "universe_domain": "googleapis.com",
        }
        return service_account.Credentials.from_service_account_info(
            credentials_info, scopes=["https://www.googleapis.com/auth/earthengine"]
        )

    return None


def get_credentials():
    """
    Get Google Earth Engine credentials using multiple fallback methods.

    Authentication priority:
    1. Streamlit secrets (production)
    2. Environment variables (testing/CI)
    3. Mock credentials (unit tests)

    Returns:
        google.oauth2.service_account.Credentials or MockCredentials: Configured credentials object
    """
    # Check if we're in testing mode
    if os.environ.get("TESTING") == "true":
        return MockCredentials()

    # Try Streamlit secrets first (production)
    try:
        return get_streamlit_credentials()
    except Exception:
        pass

    # Try environment variables (testing/CI)
    env_credentials = get_environment_credentials()
    if env_credentials:
        return env_credentials

    # Fall back to mock credentials for unit tests
    return MockCredentials()


def initialize_earth_engine():
    """
    Initialize Google Earth Engine with the configured credentials.

    This function handles the complete Earth Engine initialization process
    including credential retrieval and project setup. It supports multiple
    authentication methods for different environments.
    """
    credentials = get_credentials()

    # Skip initialization for mock credentials
    if isinstance(credentials, MockCredentials):
        return

    try:
        ee.Initialize(credentials, project="ee-beaver-lab")
    except Exception as e:
        # In testing mode, create a mock ee module
        if os.environ.get("TESTING") == "true":
            return
        raise e
