"""
Common Utilities Module

Centralized utility functions to eliminate code duplication across the application.
Contains commonly used Earth Engine operations for ID assignment, cloud masking, 
elevation processing, and metric calculations.
"""

import ee

from .constants import ELEVATION_THRESHOLD_LOWER, ELEVATION_THRESHOLD_UPPER
from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def set_feature_ids(feature_collection, prefix, start_index=1, additional_properties=None):
    """
    Assign sequential IDs to features in a collection.

    Args:
        feature_collection: Earth Engine FeatureCollection to process
        prefix: String prefix for IDs (e.g., "P" for positive, "N" for negative)
        start_index: Starting index for ID numbering (default: 1)
        additional_properties: Optional dictionary of additional properties to set

    Returns:
        Earth Engine FeatureCollection with id_property set
    """
    features_list = feature_collection.toList(feature_collection.size())
    indices = ee.List.sequence(0, feature_collection.size().subtract(1))

    def set_id(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(features_list.get(idx))
        id_value = ee.String(prefix).cat(idx.add(start_index).int().format())
        result = feature.set("id_property", id_value)

        # Add additional properties if provided
        if additional_properties:
            for key, value in additional_properties.items():
                result = result.set(key, value)

        return result

    return ee.FeatureCollection(indices.map(set_id))


def set_feature_ids_with_date_fallback(feature_collection, prefix, fallback_date_source, start_index=1, dam_status=None):
    """
    Assign sequential IDs to features with date fallback logic.

    Args:
        feature_collection: Earth Engine FeatureCollection to process
        prefix: String prefix for IDs (e.g., "P" for positive, "N" for negative)
        fallback_date_source: FeatureCollection to get date from if feature doesn't have one
        start_index: Starting index for ID numbering (default: 1)
        dam_status: Optional Dam status to set ("positive" or "negative")

    Returns:
        Earth Engine FeatureCollection with id_property and date set
    """
    features_list = feature_collection.toList(feature_collection.size())
    indices = ee.List.sequence(0, feature_collection.size().subtract(1))

    def set_id_with_date(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(features_list.get(idx))
        id_value = ee.String(prefix).cat(idx.add(start_index).int().format())

        # Handle date fallback
        date = feature.get("date")
        date = ee.Algorithms.If(ee.Algorithms.IsEqual(date, None), fallback_date_source.first().get("date"), date)

        result = feature.set("id_property", id_value).set("date", date)

        # Set dam status if provided
        if dam_status:
            result = result.set("Dam", dam_status)

        return result

    return ee.FeatureCollection(indices.map(set_id_with_date))


def add_sentinel2_cloud_mask(image):
    """
    Add cloud mask band to Sentinel-2 image.

    Args:
        image: Sentinel-2 Earth Engine Image

    Returns:
        Image with added cloudMask band
    """
    qa = image.select("QA60")
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    cloud_mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    cloud_mask_band = cloud_mask.rename("cloudMask").toUint16()
    return image.addBands(cloud_mask_band)


def add_landsat_cloud_mask(image):
    """
    Add cloud mask to Landsat image using QA_PIXEL band.

    Args:
        image: Landsat Earth Engine Image

    Returns:
        Image with cloud mask applied
    """
    qa = image.select("QA_PIXEL")
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 5).eq(0))
    return image.updateMask(mask)


def create_elevation_mask(image, point_geometry, buffer_area, upper_threshold=None, lower_threshold=None):
    """
    Create elevation mask based on point elevation with configurable thresholds.

    Args:
        image: Earth Engine Image to process
        point_geometry: Point geometry for elevation reference
        buffer_area: Buffer area geometry for clipping
        upper_threshold: Upper elevation threshold in meters (default: ELEVATION_THRESHOLD_UPPER)
        lower_threshold: Lower elevation threshold in meters (default: ELEVATION_THRESHOLD_LOWER)

    Returns:
        Image with elevation mask applied
    """
    if upper_threshold is None:
        upper_threshold = ELEVATION_THRESHOLD_UPPER
    if lower_threshold is None:
        lower_threshold = ELEVATION_THRESHOLD_LOWER

    # Get elevation dataset
    dataset = ee.Image("USGS/3DEP/10m")
    elevation = dataset.select("elevation")

    # Get point elevation
    point_elevation = ee.Number(elevation.sample(point_geometry, 10).first().get("elevation"))
    elevation_clipped = elevation.clip(buffer_area)

    # Create thresholds
    point_plus = point_elevation.add(upper_threshold)
    point_minus = point_elevation.subtract(lower_threshold)

    # Create elevation mask
    elevation_masked = (
        elevation_clipped.where(elevation_clipped.lt(point_minus), 0)
        .where(elevation_clipped.gt(point_minus), 1)
        .where(elevation_clipped.gt(point_plus), 0)
    )

    return elevation_masked.updateMask(elevation_masked.eq(1))


def calculate_ndvi(image, nir_band, red_band):
    """
    Calculate Normalized Difference Vegetation Index (NDVI).

    Args:
        image: Earth Engine Image
        nir_band: Near-infrared band name
        red_band: Red band name

    Returns:
        Image with NDVI band added
    """
    ndvi = image.normalizedDifference([nir_band, red_band]).rename("NDVI")
    return image.addBands(ndvi)


def calculate_ndwi(image, green_band, nir_band):
    """
    Calculate Normalized Difference Water Index (NDWI).

    Args:
        image: Earth Engine Image
        green_band: Green band name
        nir_band: Near-infrared band name

    Returns:
        Image with NDWI band added
    """
    ndwi = image.normalizedDifference([green_band, nir_band]).rename("NDWI")
    return image.addBands(ndwi)


def standardize_sentinel2_bands(image):
    """
    Standardize Sentinel-2 band names for consistency (B2,B3,B4,B8,cloudMask -> S2_Blue,S2_Green,S2_Red,S2_NIR,S2_Binary_cloudMask).

    Args:
        image: Sentinel-2 Earth Engine Image

    Returns:
        Image with standardized band names
    """
    old_band_names = ["B2", "B3", "B4", "B8", "cloudMask"]
    new_band_names = ["S2_Blue", "S2_Green", "S2_Red", "S2_NIR", "S2_Binary_cloudMask"]
    return image.select(old_band_names).rename(new_band_names)


def add_acquisition_date(image):
    """
    Add acquisition date as image property.

    Args:
        image: Earth Engine Image

    Returns:
        Image with acquisition_date property set
    """
    date = ee.Date(image.get("system:time_start"))
    return image.set("acquisition_date", date)


def get_image_date_properties(image):
    """
    Extract month and year from image acquisition date.

    Args:
        image: Earth Engine Image

    Returns:
        Image with Image_month and Image_year properties
    """
    image_date = ee.Date(image.get("system:time_start"))
    image_month = image_date.get("month")
    image_year = image_date.get("year")
    return image.set("Image_month", image_month).set("Image_year", image_year)
