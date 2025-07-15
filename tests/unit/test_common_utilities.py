"""
Unit tests for common_utilities.py functions.

Tests utility functions with mocked Earth Engine objects to avoid
requiring actual Earth Engine authentication.
"""

import os
from unittest.mock import Mock, patch

import pytest

# Set testing environment before importing modules
os.environ["TESTING"] = "true"


class TestNDVICalculation:
    """Test NDVI calculation functionality."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_calculate_ndvi_basic(self, mock_ee, sample_ndvi_data):
        """Test basic NDVI calculation."""
        from service.common_utilities import calculate_ndvi

        # Mock Earth Engine Image
        mock_image = Mock()
        mock_ndvi_result = Mock()
        mock_image.normalizedDifference.return_value.rename.return_value = mock_ndvi_result

        # Test the function
        result = calculate_ndvi(mock_image, "B5", "B4")

        # Verify Earth Engine methods were called correctly
        mock_image.normalizedDifference.assert_called_once_with(["B5", "B4"])
        mock_image.normalizedDifference.return_value.rename.assert_called_once_with("NDVI")

        # Verify result
        assert result == mock_ndvi_result

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_calculate_ndvi_different_bands(self, mock_ee):
        """Test NDVI calculation with different band names."""
        from service.common_utilities import calculate_ndvi

        mock_image = Mock()
        mock_ndvi_result = Mock()
        mock_image.normalizedDifference.return_value.rename.return_value = mock_ndvi_result

        # Test with Landsat bands
        calculate_ndvi(mock_image, "B4", "B3")
        mock_image.normalizedDifference.assert_called_once_with(["B4", "B3"])

        # Reset mock
        mock_image.reset_mock()

        # Test with Sentinel-2 bands
        calculate_ndvi(mock_image, "B8", "B4")
        mock_image.normalizedDifference.assert_called_once_with(["B8", "B4"])


class TestCloudMasking:
    """Test cloud masking functionality."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_add_sentinel2_cloud_mask(self, mock_ee):
        """Test Sentinel-2 cloud masking."""
        from service.common_utilities import add_sentinel2_cloud_mask

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_qa = Mock()
        mock_cloud_mask = Mock()
        # _mock_shadow_mask = Mock()  # Unused but kept for documentation
        mock_combined_mask = Mock()

        # Set up mock chain
        mock_image.select.return_value = mock_qa
        mock_qa.bitwiseAnd.return_value.eq.return_value = mock_cloud_mask
        mock_cloud_mask.And.return_value = mock_combined_mask
        mock_image.addBands.return_value = mock_image

        # Test the function
        result = add_sentinel2_cloud_mask(mock_image)

        # Verify QA band was selected
        mock_image.select.assert_called_with("QA60")

        # Verify result
        assert result == mock_image

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_add_landsat_cloud_mask(self, mock_ee):
        """Test Landsat cloud masking."""
        from service.common_utilities import add_landsat_cloud_mask

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_qa = Mock()
        mock_cloud_mask = Mock()

        # Set up mock chain
        mock_image.select.return_value = mock_qa
        mock_qa.bitwiseAnd.return_value.eq.return_value.And.return_value = mock_cloud_mask
        mock_image.updateMask.return_value = mock_image

        # Test the function
        result = add_landsat_cloud_mask(mock_image)

        # Verify QA band was selected
        mock_image.select.assert_called_with("QA_PIXEL")

        # Verify result
        assert result == mock_image


class TestElevationMasking:
    """Test elevation masking functionality."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_create_elevation_mask_basic(self, mock_ee):
        """Test basic elevation masking."""
        from service.common_utilities import create_elevation_mask

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_point = Mock()
        mock_area = Mock()
        mock_dem = Mock()
        mock_elevation = Mock()
        mock_center_elevation = Mock()
        mock_mask = Mock()

        # Set up mock chain
        mock_ee.Image.return_value = mock_dem
        mock_dem.select.return_value = mock_elevation
        mock_elevation.clip.return_value = mock_elevation
        mock_elevation.sample.return_value.first.return_value.get.return_value = mock_center_elevation
        mock_ee.Number.return_value = mock_center_elevation
        mock_center_elevation.add.return_value = mock_center_elevation
        mock_center_elevation.subtract.return_value = mock_center_elevation
        mock_elevation.where.return_value.where.return_value.where.return_value = mock_mask
        mock_mask.updateMask.return_value = mock_mask

        # Test the function
        result = create_elevation_mask(mock_image, mock_point, mock_area)

        # Verify DEM was accessed
        mock_ee.Image.assert_called_with("USGS/3DEP/10m")

        # Verify result
        assert result == mock_mask

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_create_elevation_mask_thresholds(self, mock_ee):
        """Test elevation masking with custom thresholds."""
        from service.common_utilities import create_elevation_mask

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_point = Mock()
        mock_area = Mock()
        mock_dem = Mock()
        mock_elevation = Mock()
        mock_center_elevation = Mock()
        mock_mask = Mock()

        # Set up mock chain
        mock_ee.Image.return_value = mock_dem
        mock_dem.select.return_value = mock_elevation
        mock_elevation.clip.return_value = mock_elevation
        mock_elevation.sample.return_value.first.return_value.get.return_value = mock_center_elevation
        mock_ee.Number.return_value = mock_center_elevation
        mock_center_elevation.add.return_value = mock_center_elevation
        mock_center_elevation.subtract.return_value = mock_center_elevation
        mock_elevation.where.return_value.where.return_value.where.return_value = mock_mask
        mock_mask.updateMask.return_value = mock_mask

        # Test with custom thresholds
        result = create_elevation_mask(mock_image, mock_point, mock_area, upper_threshold=5.0, lower_threshold=10.0)

        # Verify the function was called (exact verification of threshold logic
        # would require more complex mocking)
        assert result == mock_mask


class TestFeatureIDAssignment:
    """Test feature ID assignment functionality."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_set_feature_ids_basic(self, mock_ee):
        """Test basic feature ID assignment."""
        from service.common_utilities import set_feature_ids

        # Mock Earth Engine objects
        mock_collection = Mock()
        mock_features_list = Mock()
        mock_indices = Mock()
        mock_result_collection = Mock()

        # Set up mock chain
        mock_size = Mock()
        mock_size.subtract.return_value = 2
        mock_collection.size.return_value = mock_size
        mock_collection.toList.return_value = mock_features_list
        mock_ee.List.sequence.return_value = mock_indices
        mock_ee.FeatureCollection.return_value = mock_result_collection

        # Test the function
        result = set_feature_ids(mock_collection, "P", 1)

        # Verify Earth Engine methods were called
        mock_collection.toList.assert_called_once_with(mock_size)
        mock_ee.List.sequence.assert_called_once_with(0, 2)

        # Verify result
        assert result == mock_result_collection

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_set_feature_ids_with_additional_properties(self, mock_ee):
        """Test feature ID assignment with additional properties."""
        from service.common_utilities import set_feature_ids

        # Mock Earth Engine objects
        mock_collection = Mock()
        mock_features_list = Mock()
        mock_indices = Mock()
        mock_result_collection = Mock()

        # Set up mock chain
        mock_size = Mock()
        mock_size.subtract.return_value = 2
        mock_collection.size.return_value = mock_size
        mock_collection.toList.return_value = mock_features_list
        mock_ee.List.sequence.return_value = mock_indices
        mock_ee.FeatureCollection.return_value = mock_result_collection

        # Test with additional properties
        additional_props = {"Dam": "positive", "source": "manual"}
        result = set_feature_ids(mock_collection, "P", 1, additional_props)

        # Verify result
        assert result == mock_result_collection


class TestBandStandardization:
    """Test band standardization functionality."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_standardize_sentinel2_bands(self, mock_ee):
        """Test Sentinel-2 band standardization."""
        from service.common_utilities import standardize_sentinel2_bands

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_standardized = Mock()

        # Set up mock chain
        mock_image.select.return_value.rename.return_value = mock_standardized

        # Test the function
        result = standardize_sentinel2_bands(mock_image)

        # Verify bands were selected and renamed
        mock_image.select.assert_called_once()

        # Verify result
        assert result == mock_standardized

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_add_acquisition_date(self, mock_ee):
        """Test acquisition date addition."""
        from service.common_utilities import add_acquisition_date

        # Mock Earth Engine objects
        mock_image = Mock()
        mock_date = Mock()
        mock_month = Mock()
        # _mock_year = Mock()  # Unused but kept for documentation
        mock_result = Mock()

        # Set up mock chain
        mock_ee.Date.return_value = mock_date
        mock_date.get.return_value = mock_month
        mock_image.set.return_value = mock_result

        # Test the function
        result = add_acquisition_date(mock_image)

        # Verify date was extracted
        mock_ee.Date.assert_called_once_with(mock_image.get.return_value)

        # Verify result
        assert result == mock_result


class TestErrorHandling:
    """Test error handling in utility functions."""

    @pytest.mark.unit
    @patch("service.common_utilities.ee")
    def test_calculate_ndvi_error_handling(self, mock_ee):
        """Test error handling in NDVI calculation."""
        from service.common_utilities import calculate_ndvi

        # Mock Earth Engine Image that raises an exception
        mock_image = Mock()
        mock_image.normalizedDifference.side_effect = Exception("EE API Error")

        # Test that the function handles the error gracefully
        # (In a real implementation, you might want to add try-catch)
        with pytest.raises(Exception):
            calculate_ndvi(mock_image, "B5", "B4")

    @pytest.mark.unit
    def test_function_parameter_validation(self):
        """Test parameter validation in utility functions."""
        from service.common_utilities import calculate_ndvi

        # Test with None parameters
        # (In a real implementation, you might want to add parameter validation)
        with pytest.raises(AttributeError):
            calculate_ndvi(None, "B5", "B4")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
