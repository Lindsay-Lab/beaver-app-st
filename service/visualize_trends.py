"""
Functions for visualizing trends.
Sentinel-2 Dam Imagery Processing Module.

This module provides functions for extracting and processing Sentinel-2 imagery around dam locations with
 elevation-based masking and optional flow direction analysis.
"""

import ee
import streamlit as st

from .earth_engine_auth import initialize_earth_engine

initialize_earth_engine()


def s2_export_for_visual(dam_collection: ee.FeatureCollection) -> ee.ImageCollection:
    """
    Extract cloud-masked Sentinel-2 imagery with elevation masking for dam monitoring.

    This function processes a collection of dam locations to extract Sentinel-2 imagery
    with cloud masking and elevation-based filtering. Unlike the flow direction version,
    this function focuses on basic imagery extraction with elevation constraints around
    each dam location. It returns monthly composites of the least cloudy images.

    Parameters
    ----------
    dam_collection : ee.FeatureCollection
        Collection of dam features with required properties:
        - Survey_Date : ee.Date or str
            Date for temporal filtering (±6 months window)
        - id_property : str
            Unique identifier for the dam
        - Dam : str
            Dam status/type classification
        - Damdate : str
            Date string associated with the dam
        - Point_geo : ee.Geometry.Point, optional
            Point geometry of the dam location. If None/null, 
            the centroid of the feature geometry will be used.

    Returns
    -------
    ee.ImageCollection
        Collection of processed monthly Sentinel-2 images with bands:
        - S2_Blue, S2_Green, S2_Red, S2_NIR : ee.Image bands
            Renamed Sentinel-2 spectral bands (B2, B3, B4, B8)
        - S2_Binary_cloudMask : ee.Image band
            Binary cloud mask (1=clear, 0=cloudy/cirrus)
        - elevation : ee.Image band  
            Elevation mask filtered to ±3m/±5m around dam elevation

        Each image includes metadata properties:
        - First_id : str
            Composite identifier: {dam_id}_{dam_status}_S2id:_{s2_index}_{dam_date}
        - Full_id : str
            Extended identifier with cloud coverage: {First_id}_Cloud_{cloud_percent}
        - Dam_id : str
            Original dam identifier
        - Dam_status : str
            Dam classification status
        - Image_month : int
            Month of image acquisition (1-12)
        - Image_year : int
            Year of image acquisition
        - Area : ee.Geometry
            Bounding geometry for the analysis area
        - Cloud_coverage : float
            Percentage of cloud coverage in the image (0-100)
        - acquisition_date : ee.Date
            Date when the Sentinel-2 image was acquired
        - Point_geo : ee.Geometry.Point
            Dam point location (original or computed centroid)

    Notes
    -----
    The function performs several key processing steps:

    1. **Temporal Filtering**: Filters Sentinel-2 data to ±6 months from Survey_Date
    2. **Cloud Masking**: Uses QA60 band to create binary cloud masks
    3. **Elevation Masking**: Filters elevation data to dam elevation +3m/-5m using 3DEP 10m DEM
    4. **Monthly Aggregation**: Selects the least cloudy image for each month (1-12)
    5. **Band Renaming**: Standardizes band names for consistency

    The elevation masking process:
    - Samples elevation at the dam point location
    - Creates elevation range: [dam_elevation - 5m, dam_elevation + 3m] 
    - Masks pixels outside this elevation range
    - Clips all data to the dam's bounding geometry

    Error handling is implemented to catch processing failures and display
    warnings through Streamlit interface.

    Examples
    --------
    `>>> dams = ee.FeatureCollection('projects/my-project/assets/dam-locations')`
    `>>> result_images = S2_Export_for_visual(dams)`
    `>>> print(f"Generated {result_images.size().getInfo()} images")`
    `>>> first_image = ee.Image(result_images.first())`
    `>>> print(f"Bands: {first_image.bandNames().getInfo()}")`
    `>>> print(f"Dam ID: {first_image.get('Dam_id').getInfo()}")`

    See Also
    --------
    S2_Export_for_visual_flowdir : Version with flow direction analysis

    Raises
    ------
    Exception
        Any processing errors are caught and logged as Streamlit warnings.
        Failed dam locations return None and are filtered from final collection.
    """

    imagery_collections = dam_collection.map(extract_pixels).flatten()
    return ee.ImageCollection(imagery_collections)


def extract_pixels(box):
    """
    Extract Sentinel-2 pixels for dam monitoring within a specified date range.

    This function processes Sentinel-2 imagery around a dam location, applies cloud masking,
    adds elevation data, and returns monthly composite images with the least cloud coverage.

    Args:
        box (ee.Feature): Earth Engine Feature containing dam information with properties:
            - Survey_Date: Date of the survey
            - id_property: Unique dam identifier
            - Dam: Dam status information
            - Damdate: Dam construction/modification date
            - Point_geo: Point geometry for dam location (optional)

    Returns:
        ee.ImageCollection or None: Collection of processed monthly images with added bands
                                   and metadata, or None if processing fails

    Raises:
        Exception: Logs warning and returns None for any processing errors
    """
    try:
        image_date = ee.Date(box.get("Survey_Date"))
        start_date = image_date.advance(-6, "month").format("YYYY-MM-dd")
        end_date = image_date.advance(6, "month").format("YYYY-MM-dd")

        box_area = box.geometry()
        dam_id = box.get("id_property")
        dam_status = box.get("Dam")
        dam_date = box.get("Damdate")
        dam_geo = box.get("Point_geo")

        # Ensure Point_geo is a valid point geometry; Use centroid if Point_geo is None
        point_geo = ee.Algorithms.If(
            ee.Algorithms.IsEqual(dam_geo, None),
            box_area.centroid(),
            dam_geo
        )

        # Get and preprocess Sentinel-2 collection
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        s2_cloud_band = s2.map(add_cloud_mask_band)
        s2_named_bands = rename_bands(s2_cloud_band)
        s2_cloud_filter = s2_named_bands.map(add_acquisition_date)
        filtered_collection = s2_cloud_filter.filterDate(start_date, end_date).filterBounds(box_area)

        def add_band(image):
            index = image.get("system:index")
            image_date = ee.Date(image.get("system:time_start"))
            image_month = image_date.get("month")
            image_year = image_date.get("year")

            dataset = ee.Image("USGS/3DEP/10m")
            elevation_select = dataset.select("elevation")
            elevation = ee.Image(elevation_select)

            point_geom = point_geo  # Use processed point_geo
            point_elevation = ee.Number(elevation.sample(point_geom, 10).first().get("elevation"))
            buffered_area = box_area
            elevation_clipped = elevation.clip(buffered_area)

            point_plus = point_elevation.add(3)
            point_minus = point_elevation.subtract(5)
            elevation_masked = (
                elevation_clipped.where(elevation_clipped.lt(point_minus), 0)
                .where(elevation_clipped.gt(point_minus), 1)
                .where(elevation_clipped.gt(point_plus), 0)
            )
            elevation_masked2 = elevation_masked.updateMask(elevation_masked.eq(1))

            first_id = ee.String(dam_id).cat("_").cat(dam_status).cat("_S2id:_").cat(index).cat("_").cat(dam_date)

            full_image = (
                image
                .set("First_id", first_id)
                .set("Dam_id", dam_id)
                .set("Dam_status", dam_status)
                .set("Image_month", image_month)
                .set("Image_year", image_year)
                .set("Area", box_area)
                .set("id_property", dam_id)
                .set("Point_geo", point_geo)
                .clip(box_area)
            )

            return full_image.addBands(elevation_masked2)

        filtered_collection2 = filtered_collection.map(add_band)

        def calculate_cloud_coverage(image):
            cloud = image.select("S2_Binary_cloudMask")
            cloud_stats = cloud.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=image.geometry(), scale=10, maxPixels=1e9
            )
            clear_coverage_percentage = ee.Number(cloud_stats.get("S2_Binary_cloudMask")).multiply(100).round()
            cloud_coverage_percentage = ee.Number(100).subtract(clear_coverage_percentage)
            return image.set("Cloud_coverage", cloud_coverage_percentage)

        filtered_cloud_collection = filtered_collection2.map(calculate_cloud_coverage)

        filtered_collection_bands = get_monthly_least_cloudy_images(filtered_cloud_collection)

        complete_collection = filtered_collection_bands.map(_add_cloud_coverage_to_id)
        return complete_collection

    except Exception as e:  # pylint: disable=broad-except
        st.warning(f"Error processing image: {str(e)}")
        return None


def get_monthly_least_cloudy_images(collection):
    """
    Get the least cloudy image for each month from the collection.

    Args:
        collection (ee.ImageCollection): Collection of images with cloud coverage data

    Returns:
        ee.ImageCollection: Collection with one image per month (least cloudy)
    """
    months = ee.List.sequence(1, 12)

    def get_month_image(month):
        monthly_images = collection.filter(ee.Filter.calendarRange(month, month, "month"))
        return ee.Image(monthly_images.sort("CLOUDY_PIXEL_PERCENTAGE").first())

    monthly_images_list = months.map(get_month_image)
    monthly_images_collection = ee.ImageCollection.fromImages(monthly_images_list)
    return monthly_images_collection


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


def s2_export_for_visual_flowdir(dam_collection: ee.FeatureCollection,
                                 filtered_waterway: ee.FeatureCollection) -> ee.ImageCollection:
    """
    Filtering with flowline.

    Extract Sentinel-2 imagery with flow direction analysis for dam monitoring.

    This function processes a collection of dam locations to extract cloud-masked Sentinel-2
    imagery along with upstream/downstream flow direction analysis based on nearby waterways
    and elevation data. For each dam location, it identifies the closest flowline, determines
    flow direction, and creates masked elevation bands for upstream and downstream areas.

    Parameters
    ----------
    dam_collection : ee.FeatureCollection
        Collection of dam features with required properties:
        - Survey_Date: Date for temporal filtering (±6 months)
        - id_property: Unique identifier for the dam
        - Dam: Dam status/type
        - Damdate: Date string for the dam
        - Point_geo: Point geometry of the dam location

    filtered_waterway : ee.FeatureCollection
        Collection of waterway/flowline features used for flow direction analysis.
        Should contain linear geometries representing water flow paths.

    Returns
    -------
    ee.ImageCollection
        Collection of processed Sentinel-2 images with additional bands:
        - S2_Blue, S2_Green, S2_Red, S2_NIR: Renamed Sentinel-2 bands
        - S2_Binary_cloudMask: Binary cloud mask (1=clear, 0=cloudy)
        - downstream: Elevation mask for downstream flow areas
        - upstream: Elevation mask for upstream flow areas
        - elevation: Base elevation mask around dam location

        Each image includes metadata:
        - First_id, Full_id: Composite identifiers
        - Dam_id, Dam_status: Dam identification
        - Image_month, Image_year: Temporal information
        - Cloud_coverage: Percentage cloud coverage
        - Area: Bounding geometry

    Notes
    -----
    The function performs several complex operations:
    1. Temporal filtering of Sentinel-2 data (±6 months from survey date)
    2. Cloud masking using QA60 band
    3. Elevation-based masking using 3DEP 10m DEM
    4. Flow direction analysis using closest flowline identification
    5. Geometric splitting into upstream/downstream regions
    6. Monthly aggregation selecting least cloudy images

    The flow direction analysis works by:
    - Finding the closest flowline to the dam point
    - Creating a perpendicular line across the flow
    - Splitting the analysis area into upstream/downstream halves
    - Classifying other flowlines based on spatial relationships
    - Creating elevation masks for each flow direction

    Examples
    --------
    `>>> dam_points = ee.FeatureCollection('projects/my-project/assets/dam-locations')`
    `>>> waterways = ee.FeatureCollection('USGS/NHDPlus/HR/NHDFlowline')`
    `>>> result = S2_Export_for_visual_flowdir(dam_points, waterways)`
    `>>> print(f"Generated {result.size().getInfo()} images")`
    """

    def extract_pixels(box):
        image_date = ee.Date(box.get("Survey_Date"))
        start_date = image_date.advance(-6, "month").format("YYYY-MM-dd")

        end_date = image_date.advance(6, "month").format("YYYY-MM-dd")

        box_area = box.geometry()
        # DateString = box.get("stringID")
        dam_id = box.get("id_property")
        dam_status = box.get("Dam")
        dam_date = box.get("Damdate")
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

        # Add band for cloud coverage
        # Define the dataset
        s2_cloud_band = s2.map(add_cloud_mask_band)

        s2_named_bands = rename_bands(s2_cloud_band)

        s2_cloud_filter = s2_named_bands.map(add_acquisition_date)

        filtered_collection = s2_cloud_filter.filterDate(start_date, end_date).filterBounds(box_area)

        def add_band(image):
            index = image.get("system:index")
            image_date = ee.Date(image.get("system:time_start"))
            image_month = image_date.get("month")
            image_year = image_date.get("year")

            ## buffered_geometry
            buffered_geometry = box.geometry()
            point_geom = buffered_geometry.centroid()
            buffered_geometry = point_geom.buffer(200)

            waterway_state = filtered_waterway.filterBounds(buffered_geometry)

            dataset = ee.Image("USGS/3DEP/10m")
            elevation_select = dataset.select("elevation")
            elevation = ee.Image(elevation_select)

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
            # Note: if the point lies exactly on the line, distance_to_line will be 0. You might need a check for that.
            buffer_radius = ee.Number(distance_to_line).add(1)  # or some small number in degrees
            buffered_point = point_geom.buffer(buffer_radius)
            # buffered_point_2 = point_geom.buffer(distance_to_line)

            # The intersection of the line and this buffer gives the nearest point.
            closest_point_geom = main_geom.intersection(buffered_point, 1)

            coords = ee.List(closest_point_geom.coordinates())

            coords_list = coords.flatten()

            new_coord = ee.List([ee.Number(coords_list.get(0)), ee.Number(coords_list.get(1))])
            closest_point = ee.Geometry.Point(new_coord)

            # closest_point = ee.Geometry.Point(coords.get(0))

            p1 = ee.Geometry.Point(new_coord)

            second_coord = ee.List([ee.Number(coords_list.get(2)), ee.Number(coords_list.get(3))])

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
            # We'll choose (dy, -dx) here.
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
            bounding_coords = bbox.coordinates()  # ee.coords_list
            bounding_ring = ee.List(bounding_coords.get(0))  # ee.coords_list of [ [west, south], [west, north], ... ]

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

            # Step 2: Buffer the extended line just enough to make a thin clipping strip
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

            #

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
                        coords_list.cat(
                            [main_coords.get(ee.Number(closest_idx).add(1).min(main_coords.size().subtract(1)))]
                        ),
                        # Downstream fallback: add the vertex before closest_idx
                        coords_list.cat([main_coords.get(ee.Number(closest_idx).subtract(1).max(0))]),
                    ),
                )

            # Ensure at least two coordinates for both slices.
            upstream_coords_fixed = ensure_two_coords(upstream_coords, line_coords, closest_index, "up")
            downstream_coords_fixed = ensure_two_coords(downstream_coords, line_coords, closest_index, "down")

            # Convert them to ee.coords_list for further manipulation.
            upstream_list = ee.List(upstream_coords_fixed)
            downstream_list = ee.List(downstream_coords_fixed)

            # 3) Remove the shared coordinate from whichever slice is longer.
            def remove_shared_coordinate(up_coords, down_coords):
                up_size = up_coords.size()
                down_size = down_coords.size()

                # If upstream is bigger, remove its last coordinate.
                # Otherwise (or if equal), remove the first coordinate from downstream.
                trimmed_up = ee.Algorithms.If(
                    up_size.gt(down_size),
                    up_coords.slice(0, up_size.subtract(1)),
                    up_coords,  # remove last from upstream
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

            ##
            # Define upstream and downstream lines
            # upstream_line = ee.Geometry.LineString(upstream_coords)
            # downstream_line = ee.Geometry.LineString(downstream_coords)

            def label_flow_basic(feature):
                intersects_up = feature.geometry().intersects(upstream_line, ee.ErrorMargin(1))
                intersects_down = feature.geometry().intersects(downstream_line, ee.ErrorMargin(1))

                return ee.Algorithms.If(
                    intersects_up,
                    # If up == True
                    ee.Algorithms.If(intersects_down, feature.set("flow", "both"), feature.set("flow", "upstream")),
                    # else (up == False)
                    ee.Algorithms.If(
                        intersects_down, feature.set("flow", "downstream"), feature.set("flow", "unknown")
                    ),
                )

            halves = ee.FeatureCollection([top_feature, bot_feature])

            # Label each half with the basic rule above
            labeled_halves = halves.map(label_flow_basic)
            features = labeled_halves.toList(labeled_halves.size())
            f1 = ee.Feature(features.get(0))
            f2 = ee.Feature(features.get(1))
            f1_flow = f1.getString("flow")  # upstream
            f2_flow = f2.getString("flow")  # both

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

            classified_rest2 = unclassified_others1.map(
                lambda f: classify_flowline(f, upstream_waterway, downstream_waterway)
            )

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
                image.set(
                    "First_id",
                    ee.String(dam_id)
                    .cat("_")
                    .cat(dam_status)
                    .cat("_S2id:_")
                    .cat(index)
                    .cat("_")
                    .cat(dam_date)
                    .cat("_intersect_"),
                )
                .set("Dam_id", dam_id)
                .set("Dam_status", dam_status)
                .set("Image_month", image_month)
                .set("Image_year", image_year)
                .set("Area", box_area)
                .clip(box_area)
            )
            # .addBands(upstream_elev_mask).addBands(downstream_elev_mask)
            return full_image.addBands(downstream_rename).addBands(upstream_rename).addBands(elevation_masked2)

        filtered_collection2 = filtered_collection.map(add_band)

        def calculate_cloud_coverage(image):
            cloud = image.select("S2_Binary_cloudMask")

            # Compute cloud coverage percentage using a simpler approach
            cloud_stats = cloud.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=image.geometry(), scale=10, maxPixels=1e9
            )

            clear_coverage_percentage = ee.Number(cloud_stats.get("S2_Binary_cloudMask")).multiply(100).round()
            cloud_coverage_percentage = ee.Number(100).subtract(clear_coverage_percentage)  # Invert the percentage

            return image.set("Cloud_coverage", cloud_coverage_percentage)

        filtered_cloud_collection = filtered_collection2.map(calculate_cloud_coverage)
        # filteredCollection_overlap = filtered_cloud_collection.filterMetadata('intersection_ratio',
        # 'greater_than', 0.95)

        # filtered_collection_bands = get_monthly_least_cloudy_images(filteredCollection_overlap)
        filtered_collection_bands = get_monthly_least_cloudy_images(filtered_cloud_collection)

        complete_collection = filtered_collection_bands.map(_add_cloud_coverage_to_id)

        return complete_collection

    imagery_collections = dam_collection.map(extract_pixels).flatten()
    return ee.ImageCollection(imagery_collections)


def _add_cloud_coverage_to_id(image: ee.Image) -> ee.Image:
    """Add cloud coverage percentage to the image identifier."""
    first_id: ee.ComputedObject = image.get("First_id")
    cloud_coverage: ee.ComputedObject = image.get("Cloud_coverage")
    return image.set("Full_id", ee.String(first_id).cat("_Cloud_").cat(cloud_coverage))


def add_landsat_lst_et(s2_image):
    """Adds robust Landsat LST and OpenET ET bands to a Sentinel-2 image."""

    # st.write("DEBUG: Starting add_landsat_lst_et function")

    year = ee.Number(s2_image.get("Image_year"))
    month = ee.Number(s2_image.get("Image_month"))
    start_date = ee.Date.fromYMD(year, month, 1)
    end_date = start_date.advance(1, "month")

    box_area = s2_image.geometry()
    # st.write(f"DEBUG: Processing area for year")

    # STEP 1: PROCESS LANDSAT FOR LST
    def apply_scale_factors(image):
        optical_bands = image.select("SR_B.").multiply(0.0000275).add(-0.2)
        thermal_bands = image.select("ST_B.*").multiply(0.00341802).add(149.0)
        return image.addBands(optical_bands, overwrite=True).addBands(thermal_bands, overwrite=True)

    def cloud_mask(image):
        qa = image.select("QA_PIXEL")
        mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 5).eq(0))
        return image.updateMask(mask)

    # st.write("DEBUG: Fetching Landsat collection")
    landsat_col = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate(start_date, end_date)
        .filterBounds(box_area)
        .map(apply_scale_factors)
        .map(cloud_mask)
    )

    # st.write(f"DEBUG: Landsat collection size")

    def add_ndvi_stats(img):
        ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        ndvi_dict = ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13)
        return img.setMulti(ndvi_dict)

    # st.write("DEBUG: Adding NDVI stats")
    landsat_col = landsat_col.map(add_ndvi_stats)
    filtered_col = landsat_col.filter(ee.Filter.neq("NDVI_min", None))
    collection_size = filtered_col.size()
    # st.write(f"DEBUG: Filtered collection size")

    # Robust LST calculation handling special cases
    def robust_compute_lst(filtered_col, box_area):
        def lst_from_image(img):
            # st.write("DEBUG: Computing LST from single image")
            ndvi = img.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
            # st.write("DEBUG: Computing NDVI stats")
            ndvi_dict = ndvi.reduceRegion(reducer=ee.Reducer.minMax(), geometry=box_area, scale=30, maxPixels=1e13)

            ndvi_min = ee.Number(ndvi_dict.get("NDVI_min"))
            ndvi_max = ee.Number(ndvi_dict.get("NDVI_max"))

            # Handle None values explicitly
            ndvi_min = ee.Number(ee.Algorithms.If(ndvi_min, ndvi_min, 0))
            ndvi_max = ee.Number(ee.Algorithms.If(ndvi_max, ndvi_max, 1))

            # Check explicitly for identical min/max or zero-range NDVI
            zero_range = ndvi_max.subtract(ndvi_min).abs().lt(1e-6)

            # st.write("DEBUG: Computing FV")
            fv = ee.Image(
                ee.Algorithms.If(
                    zero_range,
                    ee.Image.constant(99).rename("FV"),  # default FV for no variation
                    ndvi.subtract(ndvi_min).divide(ndvi_max.subtract(ndvi_min)).pow(2).rename("FV"),
                )
            )

            # st.write("DEBUG: Computing EM")
            em = fv.multiply(0.004).add(0.986).rename("EM")
            thermal = img.select("ST_B10").rename("thermal")

            # st.write("DEBUG: Computing final LST")
            lst = thermal.expression(
                "(TB / (1 + (0.00115 * (TB / 1.438)) * log(em))) - 273.15", {"TB": thermal, "em": em}
            ).rename("LST")

            return lst

        # st.write("DEBUG: Starting robust LST computation")
        lst_image = ee.Algorithms.If(
            filtered_col.size().eq(0),
            ee.Image.constant(99).rename("LST").clip(box_area),
            ee.Algorithms.If(
                filtered_col.size().eq(1),
                lst_from_image(filtered_col.first().clip(box_area)),
                lst_from_image(filtered_col.median().clip(box_area)),
            ),
        )
        return ee.Image(lst_image)

    # st.write("DEBUG: Computing LST image")
    lst_image = robust_compute_lst(filtered_col, box_area)

    # STEP 2: PROCESS OPENET ET DATA
    # st.write("DEBUG: Processing OpenET data")
    et_collection = (
        ee.ImageCollection("OpenET/ENSEMBLE/CONUS/GRIDMET/MONTHLY/v2_0")
        .filterDate(start_date, end_date)
        .filterBounds(box_area)
    )

    # st.write(f"DEBUG: OpenET collection size")
    et_monthly = et_collection.mean().select("et_ensemble_mad").rename("ET")

    et_final = ee.Algorithms.If(
        et_collection.size().eq(0), ee.Image.constant(99).rename("ET").clip(box_area), et_monthly.clip(box_area)
    )

    et_final = ee.Image(et_final)

    # STEP 3: ADD BANDS BACK TO SENTINEL-2 IMAGE
    # st.write("DEBUG: Adding bands back to Sentinel-2 image")
    return s2_image.addBands(lst_image).addBands(et_final).set("landsat_collection_size", collection_size)


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
        "id_property": image.get("id_property")
    }


def _reduce_bands_by_mask(image, bands, mask=None, geometry=None):
    """
    Helper function to reduce bands with optional mask over geometry.
    Uses appropriate scale for each band type:
    - 10m for Sentinel-2 derived indices (NDVI, NDWI_Green)
    - 30m for Landsat derived bands (LST, ET)

    Args:
        image: ee.Image containing the bands
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
        "ET": 30  # Landsat derived
    }

    for band_name, band in bands.items():
        if mask is not None:
            masked_band = band.updateMask(mask)
        else:
            masked_band = band

        # Use appropriate scale for this band type
        scale = scale_map.get(band_name, 30)  # Default to 30m if unknown

        reduced_value = masked_band.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=scale,
            maxPixels=1e13
        ).get(band.bandNames().get(0))

        results[band_name] = reduced_value

    return results


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
    bands = {
        "NDVI": ndvi,
        "NDWI_Green": ndwi_green,
        "LST": image.select("LST"),
        "ET": image.select("ET")
    }

    # Reduce all bands over geometry
    reduced_values = _reduce_bands_by_mask(image, bands, geometry=geometry)

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
    bands = {
        "NDVI": ndvi,
        "NDWI_Green": ndwi_green,
        "LST": image.select("LST"),
        "ET": image.select("ET")
    }

    # Reduce for upstream and downstream
    upstream_results = {}
    downstream_results = {}

    for band_name, band in bands.items():
        # Upstream
        up_value = _reduce_bands_by_mask(
            image, {band_name: band},
            mask=upstream_mask,
            geometry=geometry
        )[band_name]
        upstream_results[f"{band_name}_up"] = up_value

        # Downstream
        down_value = _reduce_bands_by_mask(
            image, {band_name: band},
            mask=downstream_mask,
            geometry=geometry
        )[band_name]
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
