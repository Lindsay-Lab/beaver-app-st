import pytest
import ee
import pandas as pd
import streamlit as st
from unittest.mock import patch

from service.parser import (
    clean_coordinate,
    csv_to_ee_features,
    extract_coordinates_df,
)
from service.validation import (
    validate_dam_waterway_distance,
    generate_validation_report,
)
from service.negative_sampling import (
    sample_negative_points,
    prepare_hydro,
)
from service.visualize_trends import (
    add_elevation_band,
    add_landsat_lst_et,
    add_upstream_downstream_elevation_band,
    compute_all_metrics_lst_et,
    s2_export_for_visual,
)
from pages.analyze_impacts import (
    create_buffers,
)
from service.earth_engine_auth import initialize_earth_engine
from service.session_state import SessionStateManager


@pytest.fixture(scope="session", autouse=True)
def init_ee():
    """Initialize Earth Engine once for all tests"""
    initialize_earth_engine()


@pytest.fixture
def mock_streamlit():
    """Mock streamlit for functions that use st.session_state"""
    with patch('streamlit.session_state', {}) as mock_state:
        SessionStateManager.initialize()
        yield mock_state


def test_clean_coordinate():
    assert clean_coordinate("45.5°N") == 45.5
    assert clean_coordinate("-122.3W") == -122.3
    assert clean_coordinate("45,5") == 45.5
    assert clean_coordinate("invalid") is None


def test_csv_to_ee_features():
    """Test the actual csv_to_ee_features function from parser.py"""
    df = pd.DataFrame({
        'longitude': [-122.5, -122.6],
        'latitude': [45.5, 45.6]
    })

    features = csv_to_ee_features(df, 'longitude', 'latitude', '2020-07-01')
    fc = ee.FeatureCollection(features)

    assert fc.size().getInfo() == 2
    first_feature = fc.first()
    assert first_feature.geometry().type().getInfo() == "Point"
    assert first_feature.get("date").getInfo() == "2020-07-01"


def test_extract_coordinates_df():
    """Test extract_coordinates_df from parser.py"""
    # Create test dam data with Point_geo property
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.0]),
            {
                "id_property": "P1",
                "Point_geo": {"type": "Point", "coordinates": [-123.0, 44.0]}
            }
        ),
        ee.Feature(
            ee.Geometry.Point([-123.1, 44.1]),
            {
                "id_property": "P2",
                "Point_geo": {"type": "Point", "coordinates": [-123.1, 44.1]}
            }
        )
    ])

    df = extract_coordinates_df(dam_fc)

    assert len(df) == 2
    assert 'id_property' in df.columns
    assert 'longitude' in df.columns
    assert 'latitude' in df.columns
    assert df.loc[0, 'id_property'] == 'P1'
    assert df.loc[0, 'longitude'] == -123.0


def test_validate_dam_waterway_distance():
    """Test the actual validate_dam_waterway_distance function"""
    # Create test dams and waterway
    dam_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.0, 44.05]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-123.1, 44.15]), {"date": "2020-07-01"})
    ])

    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(dam_fc.geometry().bounds())

    results = validate_dam_waterway_distance(dam_fc, waterway, max_distance=500)

    # Check structure of results
    assert 'valid_dams' in results
    assert 'invalid_dams' in results
    assert 'valid_count' in results
    assert 'invalid_count' in results

    # Verify it's actually checking distances
    total = results['total_dams'].getInfo()
    valid = results['valid_count'].getInfo()
    invalid = results['invalid_count'].getInfo()
    assert total == valid + invalid


def test_generate_validation_report():
    """Test generate_validation_report function"""
    # Create mock validation results
    mock_results = {
        'valid_count': ee.Number(2),
        'invalid_count': ee.Number(1),
        'total_dams': ee.Number(3),
        'invalid_dams_info': ee.FeatureCollection([
            ee.Feature(None, {
                'distance': 150,
                'coordinates': [-123.5, 44.5]
            })
        ])
    }

    report = generate_validation_report(mock_results)

    assert "Total dams: 3" in report
    assert "Valid dams: 2" in report
    assert "Invalid dams: 1" in report
    assert "-123.5" in report  # Check coordinates are in report


def test_prepare_hydro():
    """Test prepare_hydro function from negative_sampling.py"""
    # Small waterway feature collection
    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline").limit(10)

    hydro_raster = prepare_hydro(waterway)

    # Check it returns an image
    assert isinstance(hydro_raster, ee.Image)
    # Check it has the hydro_mask band
    bands = hydro_raster.bandNames().getInfo()
    assert 'hydro_mask' in bands


def test_sample_negative_points():
    """Test sample_negative_points function"""
    positive_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.021055, 44.080697]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-123.001068, 44.079008]), {"date": "2020-07-01"}),
        ee.Feature(ee.Geometry.Point([-122.976106, 44.084595]), {"date": "2020-07-01"})
    ])

    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(positive_fc.geometry().bounds().buffer(1000))

    hydro_raster = prepare_hydro(waterway)

    negative_fc = sample_negative_points(
        positive_fc,
        hydro_raster,
        inner_radius=300,
        outer_radius=500,
        sampling_scale=10
    )

    size = negative_fc.size().getInfo()
    assert size > 0
    # Should generate approximately same number as positive (may vary)
    assert abs(size - positive_fc.size().getInfo()) < 1


def test_create_buffers(mock_streamlit):
    """Test the actual create_buffers function from analyze_impacts.py"""
    merged_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.021055, 44.080697]), {
            "Dam": "positive",
            "date": "2020-07-01",
            "id_property": "P1"
        }),
        ee.Feature(ee.Geometry.Point([-122.976106, 44.084595]), {
            "Dam": "negative",
            "date": "2020-07-01",
            "id_property": "N1"
        })
    ])

    st.session_state['Merged_collection'] = merged_fc
    st.session_state['Positive_collection'] = merged_fc.filter(ee.Filter.eq('Dam', 'positive'))

    result = create_buffers(buffer_radius=150)

    assert result is not None
    # Check geometry type changed to Polygon
    first = result.first()
    assert first.geometry().type().getInfo() == "Polygon"

    # Check properties are preserved
    props = first.propertyNames().getInfo()
    assert 'Dam' in props
    assert 'Survey_Date' in props
    assert 'id_property' in props
    assert 'Point_geo' in props


def test_date_standardization_by_create_buffers():
    """Test Survey_Date handling in buffer creation"""
    merged_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([-123.0, 44.0]), {
            "Dam": "positive",
            "date": "2020-07-01",
            "id_property": "P1"
        })
    ])

    st.session_state['Merged_collection'] = merged_fc
    st.session_state['Positive_collection'] = merged_fc

    result = create_buffers(150)
    first = result.first()

    # Check Survey_Date is set
    survey_date = first.get('Survey_Date').getInfo()
    assert survey_date is not None

    # Check formatted date
    damdate = first.get('Damdate').getInfo()
    assert 'DamDate_' in damdate
    assert '20200701' in damdate


def test_s2_export_for_visual():
    """Test s2_export_for_visual function"""
    # Create small buffered collection
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    image_collection = s2_export_for_visual(dam_fc, add_elevation_band)

    # Check it returns ImageCollection
    assert isinstance(image_collection, ee.ImageCollection)
    size = image_collection.size().getInfo()
    assert size > 0  # Should have some images


def test_add_landsat_lst_et():
    """Test add_landsat_lst_et adds LST and ET bands"""
    # Create a simple S2 image with required properties
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    ic = s2_export_for_visual(dam_fc, add_elevation_band).limit(1)
    first_image = ic.first()

    result = add_landsat_lst_et(first_image)

    # Check bands were added
    bands = result.bandNames().getInfo()
    assert 'LST' in bands
    assert 'ET' in bands


def test_compute_all_metrics_lst_et():
    """Test compute_all_metrics_lst_et returns feature with metrics"""
    dam_fc = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([-123.0, 44.05]).buffer(150),
            {
                "Dam": "positive",
                "Survey_Date": "2020-07-01",
                "id_property": "P1",
                "Point_geo": ee.Geometry.Point([-123.0, 44.05])
            }
        )
    ])

    ic = s2_export_for_visual(dam_fc, add_elevation_band).limit(1)
    ic_with_bands = ic.map(add_landsat_lst_et)

    # Apply metrics computation
    results_fc = ic_with_bands.map(compute_all_metrics_lst_et)

    first_result = results_fc.first()
    props = first_result.propertyNames().getInfo()

    # Check expected properties exist
    assert 'NDVI' in props
    assert 'NDWI_Green' in props
    assert 'LST' in props
    assert 'ET' in props
    assert 'Image_month' in props
    assert 'Dam_status' in props


def test_end_to_end_small_dataset(mock_streamlit):
    """Integration test with 2 points through key functions"""
    # Setup
    dam_coords = [[-123.0, 44.05], [-123.05, 44.06]]
    dam_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point(coord), {"date": "2020-07-01"})
        for coord in dam_coords
    ])

    # Load waterway
    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_OR/NHDFlowline")
    waterway = waterway.filterBounds(dam_fc.geometry().bounds())

    # Validate
    validation = validate_dam_waterway_distance(dam_fc, waterway, max_distance=500)
    assert validation['valid_count'].getInfo() > 0

    # Generate negatives
    hydro_raster = prepare_hydro(waterway)
    negatives = sample_negative_points(dam_fc, hydro_raster, 300, 500, 10)
    assert negatives.size().getInfo() > 0


def test_upstream_downstream(mock_streamlit):
    """Test upstream/downstream analysis"""

    dam_data = [
        {"date": "2020-06-15", "DamID": "24", "latitude": 35.95997899451,
         "longitude": -118.180696749346, "Dam": "positive"},
        {"date": "2020-06-15", "DamID": "23", "latitude": 35.9707477235541,
         "longitude": -118.183876088397, "Dam": "positive"}
    ]

    # Transform to buffered FeatureCollection (matching your pipeline)
    buffered_features = []
    for dam in dam_data:
        point = ee.Geometry.Point([dam['longitude'], dam['latitude']])
        buffered_geom = point.buffer(200)  # 200m buffer

        feature = ee.Feature(buffered_geom, {
            "Dam": dam["Dam"],
            "Survey_Date": dam["date"],
            "id_property": dam["DamID"],
            "Point_geo": point
        })
        buffered_features.append(feature)

    dam_fc = ee.FeatureCollection(buffered_features)

    waterway = ee.FeatureCollection("projects/sat-io/open-datasets/NHD/NHD_CA/NHDFlowline")
    waterway_filtered = waterway.filterBounds(dam_fc.geometry().bounds().buffer(1000))

    # Verify waterway exists in this area
    waterway_count = waterway_filtered.size().getInfo()
    if waterway_count == 0:
        pytest.skip("No waterway data found for California test location")

    # Now run through the actual pipeline
    # This calls s2_export_for_visual which internally:
    # 1. Filters S2 imagery by date and bounds
    # 2. Adds cloud masks
    # 3. Gets monthly medians
    # 4. Sets required properties (DamGeo, boxArea, damId, DamStatus)
    image_collection = s2_export_for_visual(
        dam_fc,
        add_upstream_downstream_elevation_band,
        waterway_filtered
    )

    ic_size = image_collection.size().getInfo()
    if ic_size == 0:
        pytest.skip("No Sentinel-2 imagery available for test date/location")

    # Get first image and verify it has the upstream/downstream bands
    first_image = image_collection.first()
    bands = first_image.bandNames().getInfo()

    # Verify that the upstream and downstream mask bands have been added
    assert 'upstream' in bands, f"Missing upstream band. Available bands: {bands}"
    assert 'downstream' in bands, f"Missing downstream band. Available bands: {bands}"

    # Verify the image has required metadata
    props = first_image.propertyNames().getInfo()
    assert 'Dam_id' in props
    assert 'Dam_status' in props
    assert 'Image_month' in props
    assert 'Image_year' in props