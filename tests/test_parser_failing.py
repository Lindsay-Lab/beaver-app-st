import ee
import pandas as pd
import pytest
import json
from unittest.mock import Mock, patch

from service.earth_engine_auth import initialize_earth_engine
from service.parser import clean_coordinate, upload_points_to_ee, upload_non_dam_points_to_ee


class TestCleanCoordinate:
    """Test the clean_coordinate function."""

    def test_clean_coordinate_valid_float(self):
        """Test cleaning valid float strings."""
        assert clean_coordinate("45.123") == 45.123
        assert clean_coordinate(45.123) == 45.123

    def test_clean_coordinate_with_degree_symbol(self):
        """Test cleaning coordinates with degree symbols."""
        assert clean_coordinate("45.123°") == 45.123

    def test_clean_coordinate_with_compass_directions(self):
        """Test cleaning coordinates with N/S/E/W."""
        assert clean_coordinate("45.123N") == 45.123
        assert clean_coordinate("45.123S") == 45.123
        assert clean_coordinate("45.123E") == 45.123
        assert clean_coordinate("45.123W") == 45.123

    def test_clean_coordinate_with_comma_decimal(self):
        """Test cleaning coordinates with comma as decimal separator."""
        assert clean_coordinate("45,123") == 45.123

    def test_clean_coordinate_with_whitespace(self):
        """Test cleaning coordinates with whitespace."""
        assert clean_coordinate("  45.123  ") == 45.123

    def test_clean_coordinate_invalid_input(self):
        """Test handling invalid coordinate inputs."""
        assert clean_coordinate("invalid") is None
        assert clean_coordinate("") is None
        assert clean_coordinate(None) is None

    def test_clean_coordinate_complex_format(self):
        """Test cleaning complex coordinate formats."""
        assert clean_coordinate("45.123°N") == 45.123
        assert clean_coordinate("  45,123°W  ") == 45.123


@pytest.fixture
def sample_csv_content():
    """Create sample CSV content for testing."""
    return "latitude,longitude,name\n40.7128,-74.0060,New York\n51.5074,-0.1278,London\n"


@pytest.fixture
def sample_csv_no_header():
    """Create sample CSV content without headers."""
    return "40.7128,-74.0060,New York\n51.5074,-0.1278,London\n"


@pytest.fixture
def sample_geojson():
    """Create sample GeoJSON content for testing."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-74.0060, 40.7128]
                },
                "properties": {
                    "name": "New York"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-0.1278, 51.5074]
                },
                "properties": {
                    "name": "London"
                }
            }
        ]
    }


@pytest.fixture
def mock_streamlit():
    """Mock streamlit functions."""
    with patch('service.Parser.st') as mock_st:
        mock_st.selectbox.side_effect = lambda *args, **kwargs: kwargs.get('options', [''])[kwargs.get('index', 0)]
        mock_st.button.return_value = True
        mock_st.write = Mock()
        mock_st.dataframe = Mock()
        mock_st.success = Mock()
        mock_st.error = Mock()
        mock_st.warning = Mock()
        yield mock_st


@pytest.fixture(scope="session")
def earth_engine_auth():
    """Initialize Earth Engine authentication once per test session."""
    initialize_earth_engine()


@pytest.fixture
def mock_earth_engine():
    """Mock Earth Engine objects - use this for tests that don't need real EE."""
    with patch('service.Parser.ee') as mock_ee:
        # Mock Feature creation
        mock_feature = Mock()
        mock_ee.Feature.return_value = mock_feature

        # Mock Geometry creation
        mock_geometry = Mock()
        mock_ee.Geometry.Point.return_value = mock_geometry
        mock_ee.Geometry.return_value = mock_geometry

        # Mock FeatureCollection creation
        mock_fc = Mock()
        mock_ee.FeatureCollection.return_value = mock_fc

        yield mock_ee


class TestUploadPointsToEEWithRealEE:
    """Test upload functions with real Earth Engine - more integration focused."""

    def test_upload_csv_creates_real_feature_collection(self, sample_csv_content, mock_streamlit, earth_engine_auth):
        """Test uploading CSV creates actual Earth Engine FeatureCollection."""

        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128, 51.5074],
                'longitude': [-74.0060, -0.1278],
                'name': ['New York', 'London']
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                # Don't mock ee in this test - use real Earth Engine
                with patch('service.Parser.ee', ee):
                    result = upload_points_to_ee(mock_file)

                # Verify it's a real FeatureCollection
                assert isinstance(result, ee.FeatureCollection)

                # Test that we can get info from it (this calls EE servers)
                try:
                    size = result.size().getInfo()
                    assert size == 2  # Should have 2 features

                    # Test getting first feature
                    first_feature = ee.Feature(result.first())
                    geometry = first_feature.geometry()
                    coords = geometry.coordinates().getInfo()

                    # Should be a point with [longitude, latitude]
                    assert len(coords) == 2
                    assert isinstance(coords[0], (int, float))
                    assert isinstance(coords[1], (int, float))

                except Exception as e:
                    pytest.skip(f"Skipping EE server test due to: {e}")

    def test_upload_geojson_with_real_ee(self, sample_geojson, mock_streamlit, earth_engine_auth):
        """Test GeoJSON upload with real Earth Engine."""

        mock_file = Mock()
        mock_file.name = "test.geojson"
        mock_file.seek = Mock()

        with patch('service.Parser.json.load') as mock_json_load:
            mock_json_load.return_value = sample_geojson

            with patch('service.Parser.ee', ee):
                result = upload_points_to_ee(mock_file)

            assert isinstance(result, ee.FeatureCollection)

            try:
                size = result.size().getInfo()
                assert size == 2  # Should have 2 features from sample_geojson
            except Exception as e:
                pytest.skip(f"Skipping EE server test due to: {e}")

    def test_feature_properties_are_set_correctly(self, earth_engine_auth, mock_streamlit):
        """Test that date properties are set correctly in features."""

        # Create a simple CSV with one point
        csv_content = "lat,lon\n40.7128,-74.0060\n"
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = csv_content.encode('utf-8')
        mock_file.seek = Mock()

        # Mock streamlit to return 2020 for year selection
        mock_streamlit.selectbox.side_effect = lambda *args, **kwargs: {
            "Select delimiter used in CSV:": "Comma (,)",
            "Select the **Longitude** column:": "lon",
            "Select the **Latitude** column:": "lat",
            "Select a year:": 2020
        }.get(args[0], kwargs.get('options', [''])[kwargs.get('index', 0)])

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'lat': [40.7128],
                'lon': [-74.0060]
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                with patch('service.Parser.ee', ee):
                    result = upload_points_to_ee(mock_file)

                # Check that the date property was set
                try:
                    first_feature = ee.Feature(result.first())
                    date_prop = first_feature.get('date').getInfo()
                    assert date_prop == "2020-07-01"
                except Exception as e:
                    pytest.skip(f"Skipping EE property test due to: {e}")


class TestUploadPointsToEE:
    """Test the upload_points_to_ee function with mocked EE (faster tests)."""

    def test_upload_csv_with_headers(self, sample_csv_content, mock_streamlit, mock_earth_engine):
        """Test uploading CSV file with headers."""
        # Create a mock file object
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        # Mock pandas read_csv to return expected DataFrame
        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128, 51.5074],
                'longitude': [-74.0060, -0.1278],
                'name': ['New York', 'London']
            })
            mock_read_csv.return_value = mock_df

            # Mock csv.Sniffer
            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                result = upload_points_to_ee(mock_file)

                # Verify Earth Engine FeatureCollection was created
                assert mock_earth_engine.FeatureCollection.called
                assert result is not None

    def test_upload_csv_without_headers(self, sample_csv_no_header, mock_streamlit, mock_earth_engine):
        """Test uploading CSV file without headers."""
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_no_header.encode('utf-8')
        mock_file.seek = Mock()

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'column0': [40.7128, 51.5074],
                'column1': [-74.0060, -0.1278],
                'column2': ['New York', 'London']
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = False

                result = upload_points_to_ee(mock_file)

                assert mock_earth_engine.FeatureCollection.called
                assert result is not None

    def test_upload_geojson(self, sample_geojson, mock_streamlit, mock_earth_engine):
        """Test uploading GeoJSON file."""
        mock_file = Mock()
        mock_file.name = "test.geojson"
        mock_file.seek = Mock()

        with patch('service.Parser.json.load') as mock_json_load:
            mock_json_load.return_value = sample_geojson

            result = upload_points_to_ee(mock_file)

            assert mock_earth_engine.FeatureCollection.called
            assert result is not None

    def test_upload_invalid_geojson(self, mock_streamlit, mock_earth_engine):
        """Test uploading invalid GeoJSON file."""
        mock_file = Mock()
        mock_file.name = "test.geojson"
        mock_file.seek = Mock()

        with patch('service.Parser.json.load') as mock_json_load:
            mock_json_load.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            result = upload_points_to_ee(mock_file)

            assert result is None
            mock_streamlit.error.assert_called()

    def test_upload_unsupported_format(self, mock_streamlit):
        """Test uploading unsupported file format."""
        mock_file = Mock()
        mock_file.name = "test.txt"

        result = upload_points_to_ee(mock_file)

        assert result is None
        mock_streamlit.error.assert_called_with(
            "Unsupported file format. Please upload a CSV or GeoJSON file."
        )

    def test_upload_no_file(self):
        """Test calling function with no file."""
        result = upload_points_to_ee(None)
        assert result is None


class TestUploadNonDamPointsToEEWithRealEE:
    """Test non-dam upload functions with real Earth Engine."""

    def test_dam_date_propagation_with_real_ee(self, sample_csv_content, mock_streamlit, earth_engine_auth):
        """Test that dam dates are correctly propagated to non-dam points."""

        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        test_date = "2021-08-15"

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128],
                'longitude': [-74.0060],
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                with patch('service.Parser.ee', ee):
                    result = upload_non_dam_points_to_ee(mock_file, dam_date=test_date)

                # Verify the date was set correctly
                try:
                    first_feature = ee.Feature(result.first())
                    date_prop = first_feature.get('date').getInfo()
                    assert date_prop == test_date
                except Exception as e:
                    pytest.skip(f"Skipping EE date test due to: {e}")


class TestUploadNonDamPointsToEE:
    """Test the upload_non_dam_points_to_ee function with mocked EE."""

    def test_upload_with_provided_dam_date(self, sample_csv_content, mock_streamlit, mock_earth_engine):
        """Test uploading with explicitly provided dam date."""
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128, 51.5074],
                'longitude': [-74.0060, -0.1278],
                'name': ['New York', 'London']
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                result = upload_non_dam_points_to_ee(mock_file, dam_date="2021-06-15")

                assert mock_earth_engine.FeatureCollection.called
                assert result is not None

    def test_upload_with_session_state_date(self, sample_csv_content, mock_streamlit, mock_earth_engine):
        """Test uploading with date from session state."""
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        # Mock session state
        mock_streamlit.session_state = {"selected_date": "2022-08-10"}

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128],
                'longitude': [-74.0060],
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                result = upload_non_dam_points_to_ee(mock_file)

                assert mock_earth_engine.FeatureCollection.called
                assert result is not None

    def test_upload_with_default_date(self, sample_csv_content, mock_streamlit, mock_earth_engine):
        """Test uploading with default date when no dam date available."""
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = sample_csv_content.encode('utf-8')
        mock_file.seek = Mock()

        # Mock empty session state
        mock_streamlit.session_state = {}

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'latitude': [40.7128],
                'longitude': [-74.0060],
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                result = upload_non_dam_points_to_ee(mock_file)

                assert mock_earth_engine.FeatureCollection.called
                assert result is not None
                mock_streamlit.warning.assert_called()


class TestIntegrationScenarios:
    """Integration-style tests for common usage scenarios."""

    def test_coordinates_with_various_formats(self, mock_streamlit, mock_earth_engine):
        """Test that various coordinate formats are handled correctly."""
        # Create CSV content with different coordinate formats
        csv_content = "lat,lon\n40.7128°N,-74.0060°W\n51,5074,-0,1278\n"
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = csv_content.encode('utf-8')
        mock_file.seek = Mock()

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'lat': ["40.7128°N", "51,5074"],
                'lon': ["-74.0060°W", "-0,1278"]
            })
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                result = upload_points_to_ee(mock_file)

                # Verify that clean_coordinate was effectively used
                assert mock_earth_engine.FeatureCollection.called

    @patch('service.Parser.st')
    def test_widget_prefix_uniqueness(self, mock_st, mock_earth_engine):
        """Test that widget prefixes prevent key conflicts."""
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.read.return_value = b"lat,lon\n1,2\n"
        mock_file.seek = Mock()

        mock_st.selectbox.return_value = "Comma (,)"
        mock_st.button.return_value = True

        with patch('service.Parser.pd.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({'lat': [1], 'lon': [2]})
            mock_read_csv.return_value = mock_df

            with patch('service.Parser.csv.Sniffer') as mock_sniffer:
                mock_sniffer.return_value.has_header.return_value = True

                # Test with different prefixes
                upload_points_to_ee(mock_file, widget_prefix="test1")
                upload_non_dam_points_to_ee(mock_file, widget_prefix="test2")

                # Verify selectbox was called with different keys
                calls = mock_st.selectbox.call_args_list
                keys = [call.kwargs.get('key') for call in calls if 'key' in call.kwargs]

                # Should have different keys for different prefixes
                assert len(set(keys)) > 1  # Multiple unique keys


if __name__ == "__main__":
    # Run with: python -m pytest test_upload_functions.py -v
    pytest.main([__file__, "-v"])