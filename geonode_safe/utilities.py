"""Utilities for impact.storage
"""

import os
import copy
import numpy
import math
import logging

from osgeo import ogr
from tempfile import mkstemp
from urllib2 import urlopen
from safe.api import read_layer
from safe.impact_functions.core import requirements_collect
from safe.impact_functions.core import requirements_met

logger = logging.getLogger(__name__)

# Spatial layer file extensions that are recognised in Risiko
# FIXME: Perhaps add '.gml', '.zip', ...
LAYER_TYPES = ['.shp', '.asc', '.tif', '.tiff', '.geotif', '.geotiff']

# Map between extensions and ORG drivers
DRIVER_MAP = {'.shp': 'ESRI Shapefile',
              '.gml': 'GML',
              '.tif': 'GTiff',
              '.asc': 'AAIGrid'}

# Map between Python types and OGR field types
# FIXME (Ole): I can't find a double precision type for OGR
TYPE_MAP = {type(None): ogr.OFTString,  # What else should this be?
            type(''): ogr.OFTString,
            type(0): ogr.OFTInteger,
            type(0.0): ogr.OFTReal,
            type(numpy.array([0.0])[0]): ogr.OFTReal,  # numpy.float64
            type(numpy.array([[0.0]])[0]): ogr.OFTReal}  # numpy.ndarray

# Templates for downloading layers through rest
WCS_TEMPLATE = '%s?version=1.0.0' + \
    '&service=wcs&request=getcoverage&format=GeoTIFF&' + \
    'store=false&coverage=%s&crs=EPSG:4326&bbox=%s' + \
    '&resx=%s&resy=%s'

WFS_TEMPLATE = '%s?service=WFS&version=1.0.0' + \
    '&request=GetFeature&typeName=%s' + \
    '&outputFormat=SHAPE-ZIP&bbox=%s'


# Miscellaneous auxiliary functions
def unique_filename(**kwargs):
    """Create new filename guaranteed not to exist previoously

    Use mkstemp to create the file, then remove it and return the name

    See http://docs.python.org/library/tempfile.html for details.
    """

    _, filename = mkstemp(**kwargs)

    try:
        os.remove(filename)
    except:
        pass

    return filename


# GeoServer utility functions
def is_server_reachable(url):
    """Make an http connection to url to see if it is accesible.

       Returns boolean
    """
    try:
        urlopen(url)
    except Exception:
        return False
    else:
        return True


def write_keywords(keywords, filename):
    """Write keywords dictonary to file

    Input
        keywords: Dictionary of keyword, value pairs
        filename: Name of keywords file. Extension expected to be .keywords

    Keys must be strings
    Values must be strings or None.

    If value is None, only the key will be written. Otherwise key, value pairs
    will be written as key: value

    Trailing or preceding whitespace will be ignored.
    """

    # Input checks
    basename, ext = os.path.splitext(filename)

    # FIXME (Ole): Why don't we just pass in the filename and let
    # this function decide the extension?
    msg = ('Unknown extension for file %s. '
           'Expected %s.keywords' % (filename, basename))
    assert ext == '.keywords', msg

    # Write
    fid = open(filename, 'w')
    for k, v in keywords.items():

        msg = ('Key in keywords dictionary must be a string. '
               'I got %s with type %s' % (k, str(type(k))[1:-1]))
        assert isinstance(k, basestring), msg

        key = k.strip()

        msg = ('Key in keywords dictionary must not contain the ":" '
               'character. I got "%s"' % key)
        assert ':' not in key, msg

        if v is None:
            fid.write('%s\n' % key)
        else:
            msg = ('Keyword value must be a string. '
                   'For key %s, I got %s with type %s'
                   % (k, v, str(type(v))[1:-1]))
            assert isinstance(v, basestring), msg

            val = v.strip()

            msg = ('Value in keywords dictionary must be a string or None. '
                   'I got %s with type %s' % (val, type(val)))
            assert isinstance(val, basestring), msg

            msg = ('Value must not contain the ":" character. '
                   'I got "%s"' % val)
            assert ':' not in val, msg

            # FIXME (Ole): Have to remove commas (issue #148)
            val = val.replace(',', '')

            fid.write('%s: %s\n' % (key, val))
    fid.close()


def extract_WGS84_geotransform(layer):
    """Extract geotransform from OWS layer object.

    Input
        layer: Raster layer object e.g. obtained from WebCoverageService

    Output:
        geotransform: GDAL geotransform (www.gdal.org/gdal_tutorial.html)

    Notes:
        The datum of the returned geotransform is always WGS84 geographic
        irrespective of the native datum/projection.

        Unlike the code for extracting native geotransform, this one
        does not require registration to be offset by half a pixel.
        Unit test test_geotransform_from_geonode in test_calculations verifies
        that the two extraction methods are equivalent for WGS84 layers.
    """

    # Get bounding box in WGS84 geographic coordinates
    bbox = layer.boundingBoxWGS84
    top_left_x = bbox[0]
    top_left_y = bbox[3]
    bottom_right_x = bbox[2]
    bottom_right_y = bbox[1]

    # Get number of rows and columns
    grid = layer.grid
    ncols = int(grid.highlimits[0]) + 1
    nrows = int(grid.highlimits[1]) + 1

    # Derive resolution
    we_pixel_res = (bottom_right_x - top_left_x) / ncols
    ns_pixel_res = (bottom_right_y - top_left_y) / nrows

    # Return geotransform 6-tuple with rotation 0
    x_rotation = 0.0
    y_rotation = 0.0

    return (top_left_x, we_pixel_res, x_rotation,
            top_left_y, y_rotation, ns_pixel_res)


def geotransform2resolution(geotransform, isotropic=False,
                            # FIXME (Ole): Check these tolerances (issue #173)
                            rtol=5.0e-2, atol=1.0e-2):
    """Convert geotransform to resolution

    Input
        geotransform: GDAL geotransform (6-tuple).
                      (top left x, w-e pixel resolution, rotation,
                      top left y, rotation, n-s pixel resolution).
                      See e.g. http://www.gdal.org/gdal_tutorial.html
        Input
            isotropic: If True, verify that dx == dy and return dx
                       If False (default) return 2-tuple (dx, dy)
            rtol, atol: Used to control how close dx and dy must be
                        to quality for isotropic. These are passed on to
                        numpy.allclose for comparison.

    Output
        resolution: grid spacing (resx, resy) in (positive) decimal
                    degrees ordered as longitude first, then latitude.
                    or resx (if isotropic is True)
    """

    resx = geotransform[1]     # w-e pixel resolution
    resy = - geotransform[5]   # n-s pixel resolution (always negative)

    if isotropic:
        msg = ('Resolution requested with '
               'isotropic=True, but '
               'resolutions in the horizontal and vertical '
               'are different: resx = %.12f, resy = %.12f. '
               % (resx, resy))
        assert numpy.allclose(resx, resy,
                              rtol=rtol, atol=atol), msg

        return resx
    else:
        return resx, resy


def bbox_intersection(*args):
    """Compute intersection between two or more bounding boxes

    Input
        args: two or more bounding boxes.
              Each is assumed to be a list or a tuple with
              four coordinates (W, S, E, N)

    Output
        result: The minimal common bounding box

    """

    msg = 'Function bbox_intersection must take at least 2 arguments.'
    assert len(args) > 1, msg

    result = [-180, -90, 180, 90]
    for a in args:
        msg = ('Bounding box expected to be a list of the '
               'form [W, S, E, N]. '
               'Instead i got "%s"' % str(a))
        try:
            box = list(a)
        except:
            raise Exception(msg)

        assert len(box) == 4, msg

        msg = 'Western boundary must be less than eastern. I got %s' % box
        assert box[0] < box[2], msg

        msg = 'Southern boundary must be less than northern. I got %s' % box
        assert box[1] < box[3], msg

        # Compute intersection

        # West and South
        for i in [0, 1]:
            result[i] = max(result[i], box[i])

        # East and North
        for i in [2, 3]:
            result[i] = min(result[i], box[i])

    # Check validity and return
    if result[0] < result[2] and result[1] < result[3]:
        return result
    else:
        return None


def buffered_bounding_box(bbox, resolution):
    """Grow bounding box with one unit of resolution in each direction


    This will ensure there is enough pixels to robustly provide
    interpolated values without having to painstakingly deal with
    all corner cases such as 1 x 1, 1 x 2 and 2 x 1 arrays.

    The border will also make sure that points that would otherwise fall
    outside the domain (as defined by a tight bounding box) get assigned
    values.

    Input
        bbox: Bounding box with format [W, S, E, N]
        resolution: (resx, resy) - Raster resolution in each direction.
                    res - Raster resolution in either direction
                    If resolution is None bbox is returned unchanged.

    Ouput
        Adjusted bounding box


    Case in point: Interpolation point O would fall outside this domain
                   even though there are enough grid points to support it

    --------------
    |            |
    |   *     *  | *    *
    |           O|
    |            |
    |   *     *  | *    *
    --------------
    """

    bbox = copy.copy(list(bbox))

    if resolution is None:
        return bbox

    try:
        resx, resy = resolution
    except:
        resx = resy = resolution

    bbox[0] -= resx
    bbox[1] -= resy
    bbox[2] += resx
    bbox[3] += resy

    return bbox


def is_sequence(x):
    """Determine if x behaves like a true sequence but not a string

    This will for example return True for lists, tuples and numpy arrays
    but False for strings and dictionaries.
    """

    if isinstance(x, basestring):
        return False

    try:
        x[0]
    except:
        return False
    else:
        return True


# Map of ogr numerical geometry types to their textual representation
# FIXME (Ole): Some of them don't exist, even though they show up
# when doing dir(ogr) - Why?:
geometry_type_map = {ogr.wkbPoint: 'Point',
                     ogr.wkbPoint25D: 'Point25D',
                     ogr.wkbPolygon: 'Polygon',
                     ogr.wkbPolygon25D: 'Polygon25D',
                     #ogr.wkbLinePoint: 'LinePoint',  # ??
                     ogr.wkbGeometryCollection: 'GeometryCollection',
                     ogr.wkbGeometryCollection25D: 'GeometryCollection25D',
                     ogr.wkbLineString: 'LineString',
                     ogr.wkbLineString25D: 'LineString25D',
                     ogr.wkbLinearRing: 'LinearRing',
                     ogr.wkbMultiLineString: 'MultiLineString',
                     ogr.wkbMultiLineString25D: 'MultiLineString25D',
                     ogr.wkbMultiPoint: 'MultiPoint',
                     ogr.wkbMultiPoint25D: 'MultiPoint25D',
                     ogr.wkbMultiPolygon: 'MultiPolygon',
                     ogr.wkbMultiPolygon25D: 'MultiPolygon25D',
                     ogr.wkbNDR: 'NDR',
                     ogr.wkbNone: 'None',
                     ogr.wkbUnknown: 'Unknown'}


def geometrytype2string(g_type):
    """Provides string representation of numeric geometry types

    FIXME (Ole): I can't find anything like this in ORG. Why?
    """

    if g_type in geometry_type_map:
        return geometry_type_map[g_type]
    elif g_type is None:
        return 'No geometry type assigned'
    else:
        return 'Unknown geometry type: %s' % str(g_type)


def points_between_points(point1, point2, delta):
    """Creates an array of points between two points given a delta

       u = (x1-x0, y1-y0)/L, where
       L=sqrt( (x1-x0)^2 + (y1-y0)^2).
       If r is the resolution, then the
       points will be given by       
       (x0, y0) + u * n * r for n = 1, 2, ....
       while len(n*u*r) < L
    """
    x0, y0 = point1
    x1, y1 = point2
    L = math.sqrt(math.pow((x1-x0),2) + math.pow((y1-y0), 2)) 
    pieces = int(L / delta)
    uu = numpy.array([x1 - x0, y1 -y0]) / L
    points = [point1]
    for nn in range(pieces):
        point = point1 + uu * (nn + 1) * delta
        points.append(point)
    return numpy.array(points)


def titelize(s):
    """Convert string into title

    This is better than the built-in method title() because
    it leaves all uppercase words like UK unchanged.

    Source http://stackoverflow.com/questions/1549641/
           how-to-capitalize-the-first-letter-of-each-word-in-a-string-python
    """

    # Replace underscores with spaces
    s = s.replace('_', ' ')

    # Capitalise
    #s = s.title()  # This will capitalize first letter force the rest down
    s = ' '.join([w[0].upper() + w[1:] for w in s.split(' ')])

    return s


def nanallclose(x, y, rtol=1.0e-5, atol=1.0e-8):
    """Numpy allclose function which allows NaN

    Input
        x, y: Either scalars or numpy arrays

    Output
        True or False

    Returns True if all non-nan elements pass.
    """

    xn = numpy.isnan(x)
    yn = numpy.isnan(y)
    if numpy.any(xn != yn):
        # Presence of NaNs is not the same in x and y
        return False

    if numpy.all(xn):
        # Everything is NaN.
        # This will also take care of x and y being NaN scalars
        return True

    # Filter NaN's out
    if numpy.any(xn):
        x = x[-xn]
        y = y[-yn]

    # Compare non NaN's and return
    return numpy.allclose(x, y, rtol=rtol, atol=atol)

def get_common_resolution(haz_metadata, exp_metadata):
    """Determine common resolution for raster layers

    Input
        haz_metadata: Metadata for hazard layer
        exp_metadata: Metadata for exposure layer

    Output
        raster_resolution: Common resolution or None (in case of vector layers)
    """

    # Determine resolution in case of raster layers
    haz_res = exp_res = None
    if haz_metadata['layertype'] == 'raster':
        haz_res = haz_metadata['resolution']

    if exp_metadata['layertype'] == 'raster':
        exp_res = exp_metadata['resolution']

    # Determine common resolution in case of two raster layers
    if haz_res is None or exp_res is None:
        # This means native resolution will be used
        raster_resolution = None
    else:
        # Take the minimum
        resx = min(haz_res[0], exp_res[0])
        resy = min(haz_res[1], exp_res[1])

        raster_resolution = (resx, resy)

    return raster_resolution


def get_bounding_boxes(haz_metadata, exp_metadata, req_bbox):
    """Check and get appropriate bounding boxes for input layers

    Input
        haz_metadata: Metadata for hazard layer
        exp_metadata: Metadata for exposure layer
        req_bbox: Bounding box (string as requested by HTML POST, or list)

    Output
        haz_bbox: Bounding box to be used for hazard layer.
        exp_bbox: Bounding box to be used for exposure layer
        imp_bbox: Bounding box to be used for resulting impact layer

    Note exp_bbox and imp_bbox are the same and calculated as the
         intersection among hazard, exposure and viewport bounds.
         haz_bbox may be grown by one pixel size in case exposure data
         is vector data to make sure points always can be interpolated
    """

    # Check requested bounding box and establish viewport bounding box
    if isinstance(req_bbox, basestring):
        check_bbox_string(req_bbox)
        vpt_bbox = bboxstring2list(req_bbox)
    elif is_sequence(req_bbox):
        x = bboxlist2string(req_bbox)
        check_bbox_string(x)
        vpt_bbox = bboxstring2list(x)
    else:
        msg = ('Invalid bounding box %s (%s). '
               'It must be a string or a list' % (str(req_bbox), type(req_bbox)))
        raise Exception(msg)

    # Get bounding boxes for layers
    haz_bbox = haz_metadata['bounding_box']
    exp_bbox = exp_metadata['bounding_box']

    # New bounding box for data common to hazard, exposure and viewport
    # Download only data within this intersection
    intersection_bbox = bbox_intersection(vpt_bbox, haz_bbox, exp_bbox)
    if intersection_bbox is None:
        # Bounding boxes did not overlap
        msg = ('Bounding boxes of hazard data [%s], exposure data [%s] '
               'and viewport [%s] did not overlap, so no computation was '
               'done. Please make sure you pan to where the data is and '
               'that hazard and exposure data overlaps.'
               % (bboxlist2string(haz_bbox, decimals=3),
                  bboxlist2string(exp_bbox, decimals=3),
                  bboxlist2string(vpt_bbox, decimals=3)))
        logger.info(msg)
        raise Exception(msg)

    # Grow hazard bbox to buffer this common bbox in case where
    # hazard is raster and exposure is vector
    if (haz_metadata['layertype'] == 'raster' and
        exp_metadata['layertype'] == 'vector'):

        haz_res = haz_metadata['resolution']
        haz_bbox = buffered_bounding_box(intersection_bbox, haz_res)
    else:
        haz_bbox = intersection_bbox

    # Usually the intersection bbox is used for both exposure layer and result
    exp_bbox = imp_bbox = intersection_bbox

    return haz_bbox, exp_bbox, imp_bbox


def get_linked_layers(main_layers):
    """Get list of layers that are required by main layers

    Input
       main_layers: List of layers of the form (server, layer_name,
                                                bbox, metadata)
    Output
       new_layers: New layers flagged by the linked keywords in main layers


    Algorithm will recursively pull layers from new layers if their
    keyword linked exists and points to available layers.
    """

    # FIXME: I don't think the naming is very robust.
    # Main layer names and workspaces come from the app, while
    # we just use the basename from the keywords for the linked layers.
    # Not sure if the basename will always work as layer name.

    new_layers = []
    for server, name, bbox, metadata in main_layers:

        workspace, layername = name.split(':')

        keywords = metadata['keywords']
        if 'linked' in keywords:
            basename, _ = os.path.splitext(keywords['linked'])

            # FIXME (Ole): Geoserver converts names to lowercase @#!!
            basename = basename.lower()

            new_layer = '%s:%s' % (workspace, basename)
            if new_layer == name:
                msg = 'Layer %s linked to itself' % name
                raise Exception(msg)

            try:
                new_metadata = get_metadata(server, new_layer)
            except Exception, e:
                msg = ('Linked layer %s could not be found: %s'
                       % (basename, str(e)))
                logger.info(msg)
                #raise Exception(msg)
            else:
                new_layers.append((server, new_layer, bbox, new_metadata))

    # Recursively search for linked layers required by the newly added layers
    if len(new_layers) > 0:
        new_layers += get_linked_layers(new_layers)

    # Return list of new layers
    return new_layers


def compatible_layers(func, layer_descriptors):
    """Fetches all the layers that match the plugin requirements.

    Input
        func: ? (FIXME(Ole): Ted, can you fill in here?
        layer_descriptor: Layer names and meta data (keywords, type, etc)

    Output:
        Array of compatible layers, can be an empty list.
    """

    layers = []
    requirements = requirements_collect(func)

    for layer_name, layer_params in layer_descriptors:
        if requirements_met(requirements, layer_params):
            layers.append(layer_name)

    return layers


def check_bbox_string(bbox_string):
    """Check that bbox string is valid
    """

    msg = 'Expected bbox as a string with format "W,S,E,N"'
    assert isinstance(bbox_string, basestring), msg

    # Use checks from string to list conversion
    # FIXME (Ole): Would be better to separate the checks from the conversion
    # and use those checks directly.
    minx, miny, maxx, maxy = bboxstring2list(bbox_string)

    # Check semantic integrity
    msg = ('Western border %.5f of bounding box %s was out of range '
           'for longitudes ([-180:180])' % (minx, bbox_string))
    assert -180 <= minx <= 180, msg

    msg = ('Eastern border %.5f of bounding box %s was out of range '
           'for longitudes ([-180:180])' % (maxx, bbox_string))
    assert -180 <= maxx <= 180, msg

    msg = ('Southern border %.5f of bounding box %s was out of range '
           'for latitudes ([-90:90])' % (miny, bbox_string))
    assert -90 <= miny <= 90, msg

    msg = ('Northern border %.5f of bounding box %s was out of range '
           'for latitudes ([-90:90])' % (maxy, bbox_string))
    assert -90 <= maxy <= 90, msg

    msg = ('Western border %.5f was greater than or equal to eastern border '
           '%.5f of bounding box %s' % (minx, maxx, bbox_string))
    assert minx < maxx, msg

    msg = ('Southern border %.5f was greater than or equal to northern border '
           '%.5f of bounding box %s' % (miny, maxy, bbox_string))
    assert miny < maxy, msg


def bboxstring2list(bbox_string):
    """Convert bounding box string to list

    Input
        bbox_string: String of bounding box coordinates of the form 'W,S,E,N'
    Output
        bbox: List of floating point numbers with format [W, S, E, N]
    """

    msg = ('Bounding box must be a string with coordinates following the '
           'format 105.592,-7.809,110.159,-5.647\n'
           'Instead I got %s of type %s.' % (str(bbox_string),
                                             type(bbox_string)))
    assert isinstance(bbox_string, basestring), msg

    fields = bbox_string.split(',')
    msg = ('Bounding box string must have 4 coordinates in the form '
           '"W,S,E,N". I got bbox == "%s"' % bbox_string)
    assert len(fields) == 4, msg

    for x in fields:
        try:
            float(x)
        except ValueError, e:
            msg = ('Bounding box %s contained non-numeric entry %s, '
                   'original error was "%s".' % (bbox_string, x, e))
            raise AssertionError(msg)

    return [float(x) for x in fields]


def get_bounding_box_string(filename):
    """Get bounding box for specified raster or vector file

    Input:
        filename

    Output:
        bounding box as python string 'West, South, East, North'
    """

    return bboxlist2string(get_bounding_box(filename))


def bboxlist2string(bbox, decimals=6):
    """Convert bounding box list to comma separated string

    Input
        bbox: List of coordinates of the form [W, S, E, N]
    Output
        bbox_string: Format 'W,S,E,N' - each will have 6 decimal points
    """

    msg = 'Got string %s, but expected bounding box as a list' % str(bbox)
    assert not isinstance(bbox, basestring), msg

    try:
        bbox = list(bbox)
    except:
        msg = 'Could not coerce bbox %s into a list' % str(bbox)
        raise Exception(msg)

    msg = ('Bounding box must have 4 coordinates [W, S, E, N]. '
           'I got %s' % str(bbox))
    assert len(bbox) == 4, msg

    for x in bbox:
        try:
            float(x)
        except ValueError, e:
            msg = ('Bounding box %s contained non-numeric entry %s, '
                   'original error was "%s".' % (bbox, x, e))
            raise AssertionError(msg)

    # Make template of the form '%.5f,%.5f,%.5f,%.5f'
    template = (('%%.%if,' % decimals) * 4)[:-1]

    # Assign numbers and return
    return template % tuple(bbox)


def get_bounding_box(filename):
    """Get bounding box for specified raster or vector file

    Input:
        filename

    Output:
        bounding box as python list of numbers [West, South, East, North]
    """

    layer = read_layer(filename)
    return layer.get_bounding_box()


