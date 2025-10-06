"""
Functions for visualizing trends.
Sentinel-2 Dam Imagery Processing Module.

This module provides functions for extracting and processing Sentinel-2 imagery around dam locations with
 elevation-based masking and optional flow direction analysis.
"""

import ee

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def add_cloud_mask_band(image):
    """
    Add bands for cloud mask where 1 is clear and 0 is cloudy pixels.
    Args:
        image: an image with bits for clouds and cirrus.
    Returns: image with additional bands
    """
    qa = image.select("QA60")

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11

    # Both flags should be set to zero, indicating clear conditions.
    cloud_mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    # Create a band with values 1 (clear) and 0 (cloudy or cirrus) and convert from byte to Uint16
    cloud_mask_band = cloud_mask.rename("cloudMask").toUint16()

    return image.addBands(cloud_mask_band)


def add_acquisition_date(image):
    """
    Add acquisition date metadata to image.
    Args:
        image: an image.
    Returns: image with acquisition date metadata added.
    """
    date = ee.Date(image.get("system:time_start"))
    return image.set("acquisition_date", date)


def rename_bands(s2_cloud_band):
    """Change band names"""
    old_band_names = ["B2", "B3", "B4", "B8", "cloudMask"]
    new_band_names = ["S2_Blue", "S2_Green", "S2_Red", "S2_NIR", "S2_Binary_cloudMask"]

    s2_named_bands = s2_cloud_band.map(lambda image: image.select(old_band_names).rename(new_band_names))
    return s2_named_bands


def apply_cloud_mask(image):
    """
    Mask out cloudy pixels (where cloudMask = 0) for relevant bands
    """
    cloud_mask = image.select("S2_Binary_cloudMask")
    return image.updateMask(cloud_mask).select(["S2_Blue", "S2_Green", "S2_Red", "S2_NIR"])


def get_monthly_median(collection):
    """
    Get the median of the images from each month
    """
    months = ee.List.sequence(1, 12)

    def get_month_image(month):
        monthly_images = collection.filter(ee.Filter.calendarRange(month, month, "month"))
        first = monthly_images.first()
        image_date = ee.Date(first.get("system:time_start"))
        image_month = image_date.get("month")
        image_year = image_date.get("year")
        median = monthly_images.median().set("Image_month", image_month).set("Image_year", image_year)
        return ee.Image(median)

    monthly_images_list = months.map(get_month_image)
    monthly_images_collection = ee.ImageCollection.fromImages(monthly_images_list)
    return monthly_images_collection


def add_elevation_band(image):

    dataset = ee.ImageCollection("USGS/3DEP/10m_collection")

    filtered_collection = dataset.filterBounds(image.geometry())
    filtered_mosaic = filtered_collection.mosaic()

    elevation_select = filtered_mosaic.select("elevation")
    elevation = ee.Image(elevation_select)

    # Extract sample area from elevation
    point_geom = image.get("DamGeo")
    buffered_area = image.get("boxArea")
    dam_status = image.get("DamStatus")
    dam_id = image.get("damId")
    # Extract elevation of dam location
    point_elevation = ee.Number(elevation.sample(point_geom, 10).first().get("elevation"))

    elevation_clipped = elevation.clip(buffered_area)

    # Create elevation radius around point to sample from
    point_plus = point_elevation.add(3)
    point_minus = point_elevation.subtract(5)
    elevation_masked = (
        elevation_clipped.where(elevation_clipped.lt(point_minus), 0)
        .where(elevation_clipped.gt(point_minus), 1)
        .where(elevation_clipped.gt(point_plus), 0)
    )
    elevation_masked2 = elevation_masked.updateMask(elevation_masked.eq(1))

    # Add bands, create new "id" property to name the file, and clip the images to the ROI
    full_image = (
        image.set("Dam_id", dam_id).set("Dam_status", dam_status).set("Area", buffered_area).clip(buffered_area)
    )
    full_image2 = full_image.addBands(elevation_masked2)

    return full_image2


def add_upstream_downstream_elevation_band(image, box, filtered_waterway):
    image_month = image.get("Image_month")
    image_year = image.get("Image_year")
    dam_id = image.get("damId")
    dam_status = image.get("DamStatus")

    ### buffered_geometry
    buffered_geometry = box.geometry()
    point_geom = buffered_geometry.centroid()
    buffered_geometry = point_geom.buffer(200)

    waterway_state = filtered_waterway.filterBounds(buffered_geometry)

    dataset = ee.ImageCollection("USGS/3DEP/10m_collection")
    filtered_collection = dataset.filterBounds(image.geometry())
    filtered_mosaic = filtered_collection.mosaic()
    elevation_select = filtered_mosaic.select("elevation")
    elevation = ee.Image(elevation_select)

    # point_geom = firstFeature.geometry()
    point_elevation = ee.Number(elevation.sample(point_geom, 10).first().get("elevation"))

    # Clip and mask based on some +/- thresholds
    point_plus = point_elevation.add(3)
    point_minus = point_elevation.subtract(10)
    elevation_clipped = elevation.clip(buffered_geometry)
    # 1 = within range, 0 = outside range
    elevation_masked = (
        elevation_clipped.where(elevation_clipped.lt(point_minus), 0)
        .where(elevation_clipped.gt(point_minus), 1)
        .where(elevation_clipped.gt(point_plus), 0)
    )
    elevation_masked2 = elevation_masked.updateMask(elevation_masked.eq(1))

    def find_closest_flowline(point_geom, waterway=filtered_waterway):
        # Filter to flowlines within some max distance bounding box
        # (This helps avoid dealing with massive data.)
        candidate_fc = waterway.filterBounds(point_geom.buffer(100))

        # Compute distance from each flowline to the point:
        candidate_fc_with_dist = candidate_fc.map(lambda f: f.set("dist", f.geometry().distance(point_geom)))

        # Sort by distance ascending and take the first feature
        closest = ee.Feature(candidate_fc_with_dist.sort("dist").first())
        return closest

    main_flowline = ee.Feature(find_closest_flowline(point_geom))
    main_geom = main_flowline.geometry()
    # Compute the distance from your point to the line (in meters, if your CRS is in meters)
    distance_to_line = main_geom.distance(point_geom)
    # Buffer the point by this distance.
    # (Note: if the point lies exactly on the line, distance_to_line will be 0)
    buffer_radius = ee.Number(distance_to_line).add(1)  # or some small number in degrees
    buffered_point = point_geom.buffer(buffer_radius)

    # The intersection of the line and this buffer gives the nearest point.
    closest_point_geom = main_geom.intersection(buffered_point, 1)
    coords = ee.List(closest_point_geom.coordinates())
    coord_list = coords.flatten()
    new_coord = ee.List([ee.Number(coord_list.get(0)), ee.Number(coord_list.get(1))])
    closest_point = ee.Geometry.Point(new_coord)
    p1 = ee.Geometry.Point(new_coord)

    second_coord = ee.List([ee.Number(coord_list.get(2)), ee.Number(coord_list.get(3))])
    p2 = ee.Geometry.Point(second_coord)

    # Cast each coordinate to an ee.Number so we can do arithmetic
    x1 = ee.Number(p1.coordinates().get(0))
    y1 = ee.Number(p1.coordinates().get(1))
    x2 = ee.Number(p2.coordinates().get(0))
    y2 = ee.Number(p2.coordinates().get(1))
    # Midpoint in latitude-longitude
    xm = x1.add(x2).divide(2)
    ym = y1.add(y2).divide(2)
    # Vector along line1
    dx = x2.subtract(x1)
    dy = y2.subtract(y1)

    # To rotate (dx, dy) by 90°, pick (dy, -dx) or (-dy, dx).
    dx_perp = dy
    dy_perp = dx.multiply(-1)
    length_factor = 10
    # Scale the perpendicular vector
    dx_long = dx_perp.multiply(length_factor).divide(2)
    dy_long = dy_perp.multiply(length_factor).divide(2)

    # Perpendicular line endpoints
    p3 = ee.Geometry.Point([xm.subtract(dx_long), ym.subtract(dy_long)])
    p4 = ee.Geometry.Point([xm.add(dx_long), ym.add(dy_long)])

    # Create the perpendicular LineString
    extended_perpendicular = ee.Geometry.LineString([p3.coordinates(), p4.coordinates()])

    buffer_distance = 130  # meters
    buffered_poly = extended_perpendicular.buffer(buffer_distance)

    bbox = buffered_poly.bounds()  # This is an ee.Geometry with a single ring
    bounding_coords = bbox.coordinates()  # ee.List
    bounding_ring = ee.List(bounding_coords.get(0))  # ee.List of [ [west, south], [west, north], ... ]

    west_south = ee.List(bounding_ring.get(0))  # [west, south]
    east_north = ee.List(bounding_ring.get(2))  # [east, north]
    west = ee.Number(west_south.get(0))
    south = ee.Number(west_south.get(1))
    east = ee.Number(east_north.get(0))
    north = ee.Number(east_north.get(1))

    # Mid-latitude
    mid_lat = south.add(north).divide(2)

    # Create top/bottom rectangles
    top_rect = ee.Geometry.Rectangle([west, mid_lat, east, north])
    bot_rect = ee.Geometry.Rectangle([west, south, east, mid_lat])
    # 6) Intersect rectangles with the buffer to get two halves
    top_poly = buffered_poly.intersection(top_rect, maxError=1)
    bot_poly = buffered_poly.intersection(bot_rect, maxError=1)
    top_feature = ee.Feature(top_poly, {"id": "top"})
    bot_feature = ee.Feature(bot_poly, {"id": "bot"})

    def get_closest_vertex_index(coords, pt):
        distances = coords.map(lambda c: ee.Geometry.Point(c).distance(pt))
        min_dist = distances.reduce(ee.Reducer.min())
        return ee.List(distances).indexOf(min_dist)

    # Get the full list of coordinates from the flowline geometry.
    line_coords = main_geom.coordinates()

    # Find the index of the vertex nearest to our computed closest point.
    closest_index = get_closest_vertex_index(line_coords, closest_point)

    upstream_coords = line_coords.slice(0, ee.Number(closest_index).add(1))
    downstream_coords = line_coords.slice(ee.Number(closest_index), line_coords.size())

    #################
    def ensure_two_coords(coords, main_coords, closest_idx, direction):
        """
        coords: The initial list of coordinates for upstream or downstream.
        main_coords: The entire coordinate list of the flowline.
        closest_idx: Index of the vertex nearest the point of interest.
        direction: 'up' or 'down' – determines where we add a fallback coordinate.
        """
        coords_list = ee.List(coords)
        size = coords_list.size()

        # If already >= 2, do nothing; otherwise add a neighbor from main_coords.
        return ee.Algorithms.If(
            size.gte(2),
            coords_list,
            ee.Algorithms.If(
                direction == "up",
                # Upstream fallback: add the vertex after closest_idx
                coords_list.cat([main_coords.get(ee.Number(closest_idx).add(1).min(main_coords.size().subtract(1)))]),
                # Downstream fallback: add the vertex before closest_idx
                coords_list.cat([main_coords.get(ee.Number(closest_idx).subtract(1).max(0))]),
            ),
        )

    # Ensure at least two coordinates for both slices.
    upstream_coords_fixed = ensure_two_coords(upstream_coords, line_coords, closest_index, "up")
    downstream_coords_fixed = ensure_two_coords(downstream_coords, line_coords, closest_index, "down")
    # Convert them to ee.List for further manipulation.
    upstream_list = ee.List(upstream_coords_fixed)
    downstream_list = ee.List(downstream_coords_fixed)

    # 3) Remove the shared coordinate from whichever slice is longer.
    def remove_shared_coordinate(up_coords, down_coords):
        up_size = up_coords.size()
        down_size = down_coords.size()

        # If upstream is bigger, remove its last coordinate.
        # Otherwise (or if equal), remove the first coordinate from downstream.
        trimmed_up = ee.Algorithms.If(
            up_size.gt(down_size), up_coords.slice(0, up_size.subtract(1)), up_coords  # remove last from upstream
        )
        trimmed_down = ee.Algorithms.If(
            up_size.gte(down_size), down_coords, down_coords.slice(1)  # remove first from downstream
        )
        return {"up": trimmed_up, "down": trimmed_down}

    # Apply the removal.
    removed_dict = remove_shared_coordinate(upstream_list, downstream_list)
    final_up_coords = ee.List(removed_dict.get("up"))
    final_down_coords = ee.List(removed_dict.get("down"))

    # 4) Convert to final LineString geometries.
    upstream_line = ee.Geometry.LineString(final_up_coords)
    downstream_line = ee.Geometry.LineString(final_down_coords)

    def label_flow_basic(feature):
        intersects_up = feature.geometry().intersects(upstream_line, ee.ErrorMargin(1))
        intersects_down = feature.geometry().intersects(downstream_line, ee.ErrorMargin(1))

        return ee.Algorithms.If(
            intersects_up,
            # If up == True
            ee.Algorithms.If(intersects_down, feature.set("flow", "both"), feature.set("flow", "upstream")),
            # else (up == False)
            ee.Algorithms.If(intersects_down, feature.set("flow", "downstream"), feature.set("flow", "unknown")),
        )

    halves = ee.FeatureCollection([top_feature, bot_feature])

    # Label each half with the basic rule above
    labeled_halves = halves.map(label_flow_basic)
    features = labeled_halves.toList(labeled_halves.size())
    f1 = ee.Feature(features.get(0))
    f2 = ee.Feature(features.get(1))
    f1_flow = f1.getString("flow")  ## upstream
    f2_flow = f2.getString("flow")  ## both

    def opposite(flow_str):
        return ee.String(ee.Algorithms.If(flow_str.equals("upstream"), "downstream", "upstream"))

    f1_new = ee.Feature(ee.Algorithms.If(f1_flow.equals("both"), f1.set("flow", opposite(f2_flow)), f1))
    f2_new = ee.Feature(ee.Algorithms.If(f2_flow.equals("both"), f2.set("flow", opposite(f1_flow)), f2))
    new_fc = ee.FeatureCollection([f1_new, f2_new])

    # # Filter into two variables
    upstream_half = new_fc.filter(ee.Filter.eq("flow", "upstream")).geometry()
    downstream_half = new_fc.filter(ee.Filter.eq("flow", "downstream")).geometry()

    # Filter out the main_flowline from the rest
    others = waterway_state.filter(ee.Filter.neq("system:index", main_flowline.get("system:index")))

    # 5) CLASSIFY THE OTHER FLOWLINES INTO UPSTREAM / DOWNSTREAM / UNCLASSIFIED
    def classify_flowline(feature, upstream, downstream):
        geom = feature.geometry()
        intersects_up = geom.intersects(upstream)
        intersects_down = geom.intersects(downstream)

        # Nested ee.Algorithms.If() to avoid using .and()
        return ee.Algorithms.If(
            intersects_up,
            ee.Algorithms.If(
                intersects_down,
                # Touches both => unclassified
                feature.set("flow_part", "unclassified"),
                # Touches only upstream
                feature.set("flow_part", "upstream_flow"),
            ),
            ee.Algorithms.If(
                intersects_down,
                # Touches only downstream
                feature.set("flow_part", "downstream_flow"),
                # Touches neither => unclassified
                feature.set("flow_part", "unclassified"),
            ),
        )

    classified_rest1 = others.map(lambda f: classify_flowline(f, upstream_line, downstream_line))

    upstream_others1 = classified_rest1.filter(ee.Filter.eq("flow_part", "upstream_flow"))
    downstream_others1 = classified_rest1.filter(ee.Filter.eq("flow_part", "downstream_flow"))
    unclassified_others1 = classified_rest1.filter(ee.Filter.eq("flow_part", "unclassified"))

    upstream_waterway = ee.FeatureCollection([ee.Feature(upstream_line)]).merge(upstream_others1)
    downstream_waterway = ee.FeatureCollection([ee.Feature(downstream_line)]).merge(downstream_others1)

    classified_rest2 = unclassified_others1.map(lambda f: classify_flowline(f, upstream_waterway, downstream_waterway))
    upstream_others2 = classified_rest2.filter(ee.Filter.eq("flow_part", "upstream_flow"))
    downstream_others2 = classified_rest2.filter(ee.Filter.eq("flow_part", "downstream_flow"))
    unclassified_others2 = classified_rest2.filter(ee.Filter.eq("flow_part", "unclassified"))
    upstream_waterway2 = upstream_others2.merge(upstream_waterway)
    downstream_waterway2 = downstream_others2.merge(downstream_waterway)
    classified_rest3 = unclassified_others2.map(
        lambda f: classify_flowline(f, upstream_waterway2, downstream_waterway2)
    )
    upstream_others3 = classified_rest3.filter(ee.Filter.eq("flow_part", "upstream_flow"))
    downstream_others3 = classified_rest3.filter(ee.Filter.eq("flow_part", "downstream_flow"))
    upstream_waterway3 = upstream_others3.merge(upstream_waterway2)
    downstream_waterway3 = downstream_others3.merge(downstream_waterway2)
    # 6) DISSOLVE EACH GROUP INTO SINGLE GEOMETRIES
    upstream_geometry = upstream_waterway3.geometry().dissolve()
    downstream_geometry = downstream_waterway3.geometry().dissolve()
    # 7) BUFFER & MASK ELEVATION
    buffer_dist = 100  # meters
    upstream_buffered = upstream_geometry.buffer(buffer_dist)
    downstream_buffered = downstream_geometry.buffer(buffer_dist)
    upstream_mask_img = ee.Image.constant(1).clip(upstream_buffered)
    downstream_mask_img = ee.Image.constant(1).clip(downstream_buffered)
    # Create inverse masks using downstream_half and upstream_half geometries
    downstream_half_mask = ee.Image.constant(0).paint(downstream_half, 1)
    upstream_half_mask = ee.Image.constant(0).paint(upstream_half, 1)
    upstream_final_mask = upstream_mask_img.updateMask(downstream_half_mask.Not())
    downstream_final_mask = downstream_mask_img.updateMask(upstream_half_mask.Not())
    # Apply the refined masks to the elevation image
    upstream_elev_mask = elevation_masked2.updateMask(elevation_masked2.mask().And(upstream_final_mask))

    downstream_elev_mask = elevation_masked2.updateMask(elevation_masked2.mask().And(downstream_final_mask))

    downstream_rename = downstream_elev_mask.rename("downstream")
    upstream_rename = upstream_elev_mask.rename("upstream")
    # Add bands, create new "id" property to name the file, and clip the images to the ROI
    full_image = (
        image.set("Dam_id", dam_id)
        .set("Dam_status", dam_status)
        .set("Image_month", image_month)
        .set("Image_year", image_year)
        .set("Area", box.geometry())
        .clip(box.geometry())
    )
    # .addBands(upstream_elev_mask).addBands(downstream_elev_mask)
    return full_image.addBands(downstream_rename).addBands(upstream_rename).addBands(elevation_masked2)


def s2_export_for_visual(dam_collection, elevation_function, filtered_waterway=None):
    """Apply the required transformations and filtration to the images"""

    def extract_pixels(box):
        image_date = ee.Date(box.get("Survey_Date"))
        start_date = image_date.advance(-6, "month").format("YYYY-MM-dd")
        end_date = image_date.advance(6, "month").format("YYYY-MM-dd")

        box_area = box.geometry()
        dam_id = box.get("id_property")
        dam_status = box.get("Dam")
        dam_geo = box.get("Point_geo")
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        filtered_collection = s2.filterDate(start_date, end_date).filterBounds(box_area)

        # Define the dataset
        s2_cloud_band = filtered_collection.map(add_cloud_mask_band)
        s2_named_bands = rename_bands(s2_cloud_band)
        s2_cloud_masked = s2_named_bands.map(apply_cloud_mask)
        s2_cloud_filter = s2_cloud_masked.map(add_acquisition_date)
        filtered_collection_bands = get_monthly_median(s2_cloud_filter)

        # Set metadata to each image
        filtered_collection_bands = filtered_collection_bands.map(
            lambda img: img.set("DamGeo", dam_geo)
            .set("boxArea", box_area)
            .set("damId", dam_id)
            .set("DamStatus", dam_status)
        )

        # Apply elevation_function
        if elevation_function == add_upstream_downstream_elevation_band:
            filtered_collection_bands = filtered_collection_bands.map(
                lambda img: elevation_function(img, box, filtered_waterway)
            )
        else:
            filtered_collection_bands = filtered_collection_bands.map(elevation_function)

        return filtered_collection_bands

    imagery_collections = dam_collection.map(extract_pixels).flatten()
    return ee.ImageCollection(imagery_collections)


def _add_cloud_coverage_to_id(image: ee.Image) -> ee.Image:
    """Add cloud coverage percentage to the image identifier."""
    first_id: ee.ComputedObject = image.get("First_id")
    cloud_coverage: ee.ComputedObject = image.get("Cloud_coverage")
    return image.set("Full_id", ee.String(first_id).cat("_Cloud_").cat(cloud_coverage))


def add_landsat_lst_et(s2_image):
    """Adds robust Landsat LST and OpenET ET bands to a Sentinel-2 image."""

    year = ee.Number(s2_image.get("Image_year"))
    month = ee.Number(s2_image.get("Image_month"))
    start_date = ee.Date.fromYMD(year, month, 1)
    end_date = start_date.advance(1, "month")

    box_area = s2_image.geometry()

    # STEP 1: PROCESS LANDSAT FOR LST
    def apply_scale_factors(image):
        optical_bands = image.select("SR_B.").multiply(0.0000275).add(-0.2)
        thermal_bands = image.select("ST_B.*").multiply(0.00341802).add(149.0)
        return image.addBands(optical_bands, overwrite=True).addBands(thermal_bands, overwrite=True)

    def cloud_mask(image):
        qa = image.select("QA_PIXEL")
        mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 5).eq(0))
        return image.updateMask(mask)

    lc08 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterDate(start_date, end_date).filterBounds(box_area)
    lc09 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterDate(start_date, end_date).filterBounds(box_area)
    landsat_col = lc08.merge(lc09).map(apply_scale_factors).map(cloud_mask)

    def add_ndvi_stats(img):
        """
        Add NDVI stats as properties for filtering
        """
        ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        d = ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13)
        # Store only if we actually got values
        return img.setMulti(ee.Dictionary(d))

    landsat_col = landsat_col.map(add_ndvi_stats)

    filtered_col = landsat_col.filter(ee.Filter.notNull(["NDVI_min", "NDVI_max"]))
    collection_size = filtered_col.size()

    def lst_from_image(img):
        ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        d = ee.Dictionary(ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13))

        has_min = d.contains("NDVI_min")
        has_max = d.contains("NDVI_max")

        # Python EE: no And/Or; do nested If to compute "has_both"
        has_both = ee.Algorithms.If(has_min, ee.Algorithms.If(has_max, True, False), False)

        ndvi_min = ee.Number(ee.Algorithms.If(has_min, d.get("NDVI_min"), 0))
        ndvi_max = ee.Number(ee.Algorithms.If(has_max, d.get("NDVI_max"), 1))

        # If we have both stats, check real range; otherwise treat as zero-range (invalid)
        zero_range = ee.Algorithms.If(has_both, ndvi_max.subtract(ndvi_min).abs().lt(1e-6), True)

        fv = ee.Image(
            ee.Algorithms.If(
                zero_range,
                # fully masked placeholder so downstream math stays valid
                ee.Image.constant(0).toFloat().selfMask(),
                ndvi.subtract(ndvi_min).divide(ndvi_max.subtract(ndvi_min)).pow(2),
            )
        ).rename("FV")

        em = fv.multiply(0.004).add(0.986).rename("EM")
        tb = img.select("ST_B10").rename("TB")

        lst = tb.expression("(TB / (1 + (0.00115 * (TB / 1.438)) * log(em))) - 273.15", {"TB": tb, "em": em}).rename(
            "LST"
        )

        return lst.updateMask(fv.mask())

    lst_image = ee.Image(
        ee.Algorithms.If(
            filtered_col.size().eq(0),
            # no valid Landsat → masked LST image (no bogus 99s)
            ee.Image.constant(0).toFloat().selfMask().rename("LST").clip(box_area),
            ee.Algorithms.If(
                filtered_col.size().eq(1),
                lst_from_image(filtered_col.first()).clip(box_area),
                lst_from_image(filtered_col.median()).clip(box_area),
            ),
        )
    )
    # STEP 2: PROCESS OPENET ET DATA
    et_collection = (
        ee.ImageCollection("OpenET/ENSEMBLE/CONUS/GRIDMET/MONTHLY/v2_0")
        .filterDate(start_date, end_date)
        .filterBounds(box_area)
    )

    et_monthly = et_collection.mean().select("et_ensemble_mad").rename("ET")
    et_final = ee.Image(
        ee.Algorithms.If(
            et_collection.size().eq(0),
            ee.Image.constant(0).toFloat().selfMask().rename("ET").clip(box_area),
            et_monthly.clip(box_area),
        )
    )

    # STEP 3: ADD BANDS BACK TO SENTINEL-2 IMAGE
    return s2_image.addBands(lst_image).addBands(et_final).set("landsat_collection_size", collection_size)


def compute_all_metrics_lst_et(image) -> ee.Feature:
    """
    Returns an ee.Feature containing mean NDVI, NDWI_Green, LST, and ET
    for the geometry of interest.
    """
    # Get geometry from elevation band
    elevation_mask = image.select("elevation")
    geometry = elevation_mask.geometry()

    # Compute indices
    ndvi, ndwi_green = _compute_indices(image)

    # Prepare bands for reduction
    bands = {"NDVI": ndvi, "NDWI_Green": ndwi_green, "LST": image.select("LST"), "ET": image.select("ET")}

    # Reduce all bands over geometry
    reduced_values = _reduce_bands_by_mask(bands, geometry=geometry)

    # Extract metadata and combine with metrics
    metadata = _extract_metadata(image)
    combined_metrics = {**metadata, **reduced_values}

    return ee.Feature(None, ee.Dictionary(combined_metrics))


def compute_all_metrics_up_downstream(image):
    """
    Returns an ee.Feature containing separate upstream/downstream mean NDVI, NDWI_Green, LST, and ET.
    """
    # Get masks
    upstream_mask = image.select("upstream")
    downstream_mask = image.select("downstream")
    geometry = image.geometry()

    # Compute indices
    ndvi, ndwi_green = _compute_indices(image)

    # Prepare bands for reduction
    bands = {"NDVI": ndvi, "NDWI_Green": ndwi_green, "LST": image.select("LST"), "ET": image.select("ET")}

    # Reduce for upstream and downstream
    upstream_results = {}
    downstream_results = {}

    for band_name, band in bands.items():
        # Upstream
        up_value = _reduce_bands_by_mask(bands={band_name: band}, mask=upstream_mask, geometry=geometry)[band_name]
        upstream_results[f"{band_name}_up"] = up_value

        # Downstream
        down_value = _reduce_bands_by_mask(bands={band_name: band}, mask=downstream_mask, geometry=geometry)[band_name]
        downstream_results[f"{band_name}_down"] = down_value

    # Extract metadata and combine all results
    metadata = _extract_metadata(image)
    combined_metrics = {**metadata, **upstream_results, **downstream_results}

    # Fix naming inconsistency: NDWI_Green -> NDWI for downstream function
    if "NDWI_Green_up" in combined_metrics:
        combined_metrics["NDWI_up"] = combined_metrics.pop("NDWI_Green_up")
    if "NDWI_Green_down" in combined_metrics:
        combined_metrics["NDWI_down"] = combined_metrics.pop("NDWI_Green_down")

    return ee.Feature(None, ee.Dictionary(combined_metrics))


def _compute_indices(image):
    """Helper function to compute NDVI and NDWI_Green indices."""
    ndvi = image.normalizedDifference(["S2_NIR", "S2_Red"]).rename("NDVI")
    ndwi_green = image.normalizedDifference(["S2_Green", "S2_NIR"]).rename("NDWI_Green")
    return ndvi, ndwi_green


def _extract_metadata(image):
    """Helper function to extract common metadata from image."""
    return {
        "Image_month": image.get("Image_month"),
        "Image_year": image.get("Image_year"),
        "Dam_status": image.get("Dam_status"),
        "id_property": image.get("id_property"),
    }


def _reduce_bands_by_mask(bands, mask=None, geometry=None):
    """
    Helper function to reduce bands with optional mask over geometry.
    Uses appropriate scale for each band type:
    - 10m for Sentinel-2 derived indices (NDVI, NDWI_Green)
    - 30m for Landsat derived bands (LST, ET)

    Args:
        bands: dict mapping band names to ee.Image bands
        mask: optional ee.Image mask to apply
        geometry: geometry for reduction

    Returns:
        dict of reduced values
    """
    results = {}

    # Define appropriate scales for each band type
    scale_map = {
        "NDVI": 10,  # Sentinel-2 derived
        "NDWI_Green": 10,  # Sentinel-2 derived
        "LST": 30,  # Landsat derived
        "ET": 30,  # Landsat derived
    }

    for band_name, band in bands.items():
        if mask is not None:
            masked_band = band.updateMask(mask)
        else:
            masked_band = band

        # Use appropriate scale for this band type
        scale = scale_map.get(band_name, 30)  # Default to 30m if unknown

        reduced_value = masked_band.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=scale, maxPixels=1e13
        ).get(band.bandNames().get(0))

        results[band_name] = reduced_value

    return results
