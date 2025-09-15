import pytest
import subprocess
import time
import requests


@pytest.fixture(scope="session")
def streamlit_app():
    """Start streamlit app for testing."""
    process = subprocess.Popen([
        "streamlit", "run", "app.py",
        "--server.port", "8503",
        "--server.headless", "true"
    ])

    # Wait for startup
    time.sleep(5)

    yield "http://localhost:8503"

    # Cleanup
    process.terminate()
    process.wait()


def test_app_loads(streamlit_app):
    """Test that the main page loads."""
    response = requests.get(streamlit_app)
    assert response.status_code == 200


def test_health_endpoint(streamlit_app):
    """Test the health endpoint."""
    response = requests.get(f"{streamlit_app}/healthz")
    assert response.status_code == 200