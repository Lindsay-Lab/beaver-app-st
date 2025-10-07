"""
Functions for negative sampling of dam locations for comparative analyses.
"""

import ee


def deduplicate_locations(orig_set):
    """Merge close points, take centroids, and return unique feature collection."""
    buffer_distance = 10  # Adjust based on your criteria
    buffered_points = orig_set.map(lambda point: point.buffer(buffer_distance))
    union_of_buffers = buffered_points.union()
    simplified_union = union_of_buffers.geometry().simplify(buffer_distance / 2)
    centroids = simplified_union.geometries().map(lambda geom: ee.Feature(ee.Geometry(geom).centroid()))
    return ee.FeatureCollection(centroids)


def prepare_hydro(waterway_fc) -> ee.Image:
    """
    Convert a lines/polygons FeatureCollection (hydro) to a raster image
    for sampling, with 'hydro_mask' band = 1 where waterway is present.
    """
    # Paint the features onto an empty image
    base = ee.Image(0).int()
    hydro_raster = base.paint(waterway_fc, 1, 1)

    # Focal max to fill small gaps (optional). Adjust radius/iterations as needed
    filled_image = hydro_raster.focal_max(radius=2, units="meters", iterations=8)
    hydro_raster = filled_image.gt(0).rename(["hydro_mask"])

    return hydro_raster


def sample_negative_points(positive_dams, hydro_raster, inner_radius, outer_radius, sampling_scale):
    """
    Create negative points by:
      1) Buffering positive sites with innerRadius, dissolving them.
      2) Buffering that dissolved geometry again by outerRadius.
      3) Taking the difference (outer minus inner).
      4) Sampling from hydroRaster within that ring, ensuring hydro_mask == 1.
    """

    # Buffer each point by innerRadius with error margin
    inner_buffers = positive_dams.map(lambda pt: pt.buffer(inner_radius, 1))  # Add 1 meter error margin
    inner_dissolved = inner_buffers.geometry().dissolve(1)  # Add 1 meter error margin

    # Buffer the dissolved geometry by outerRadius with error margin
    outer_buffer = ee.Feature(inner_dissolved.buffer(outer_radius, 1))  # Add 1 meter error margin
    # We want just the ring (outer minus inner)
    ring_area = outer_buffer.geometry().difference(inner_dissolved, 1)  # Add 1 meter error margin

    # Clip hydroRaster to that ring
    clipped_hydro = hydro_raster.clip(ring_area)

    # Sample the same number of negatives as positives
    num_points = positive_dams.size()

    # Use stratifiedSample, specifying classBand='hydro_mask'
    samples = clipped_hydro.stratifiedSample(
        numPoints=num_points, classBand="hydro_mask", region=ring_area, scale=sampling_scale, seed=42, geometries=True
    )

    # Filter only where hydro_mask == 1
    negative_points = samples.filter(ee.Filter.eq("hydro_mask", 1))
    return negative_points
