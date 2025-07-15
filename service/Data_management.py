import ee

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def set_id_year_property_GEE_Collection(feature):
    # Get the feature id
    feature_id = feature.id()
    short_id = feature_id.slice(-2)  # Extract the last two characters
    date = ee.Date(feature.get("date"))
    year = date.get("year")
    # Set the feature id as a property
    return feature.set("id_property", feature_id).set("year", year).set("DamID", short_id)


def set_id_negatives(feature_collection):
    """Set IDs for negative points in a feature collection."""
    features_list = feature_collection.toList(feature_collection.size())
    indices = ee.List.sequence(0, feature_collection.size().subtract(1))

    def set_id(idx):
        idx = ee.Number(idx)
        feature = ee.Feature(features_list.get(idx))
        return feature.set("id_property", ee.String("N").cat(idx.add(1).int().format()))

    return ee.FeatureCollection(indices.map(set_id))


def add_dam_buffer_and_standardize_date(feature):
    # Add Dam property and other metadata
    dam_status = feature.get("Dam")

    # Force the date to July 1st of the specified year
    standardized_date = ee.Date.fromYMD(year_selection, 7, 1)
    formatted_date = standardized_date.format("YYYYMMdd")

    # Buffer geometry while retaining properties
    buffered_geometry = feature.geometry().buffer(buffer_radius)

    # Create a new feature with buffered geometry and updated properties
    return ee.Feature(buffered_geometry).set(
        {
            "Dam": dam_status,
            "Survey_Date": standardized_date,  # Set survey date to July 1st
            "Damdate": ee.String("DamDate_").cat(formatted_date),  # Updated date format
            "Point_geo": feature.geometry(),
            "id_property": feature.get("id_property"),
        }
    )
