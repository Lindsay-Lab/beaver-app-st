from .common_utilities import add_acquisition_date, add_sentinel2_cloud_mask
from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def process_Sentinel2_with_cloud_coverage(S2_collection):
    """
    Process Sentinel-2 collection by adding a cloud mask band, renaming bands,
    adding acquisition date, and calculating cloud coverage percentage.
    """

    # Use centralized cloud masking function

    # Rename bands
    oldBandNames = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12", "cloudMask"]
    newBandNames = [
        "S2_Aerosols",
        "S2_Blue",
        "S2_Green",
        "S2_Red",
        "S2_Red_Edge1",
        "S2_Red_Edge2",
        "S2_Red_Edge3",
        "S2_NIR",
        "S2_Red_Edge4",
        "S2_Water_Vapor",
        "S2_SWIR1",
        "S2_SWIR2",
        "S2_Binary_cloudMask",
    ]

    def rename_bands(image):
        return image.select(oldBandNames).rename(newBandNames)

    # Add acquisition date
    # Use centralized acquisition date function

    # Process the collection
    processed_collection = S2_collection.map(add_sentinel2_cloud_mask).map(rename_bands).map(add_acquisition_date)

    return processed_collection
