import os
import time
import unittest
import numpy
import urllib2
import tempfile
import datetime
import gisdata

from geonode_safe.storage import save_to_geonode, RisikoException
from geonode_safe.storage import check_layer, assert_bounding_box_matches
from geonode_safe.storage import get_bounding_box
from geonode_safe.storage import download, get_metadata
from geonode_safe.storage import read_layer
from geonode_safe.utilities import get_bounding_box_string
from geonode_safe.utilities import bboxstring2list
from geonode_safe.utilities import unique_filename, LAYER_TYPES
from geonode_safe.utilities import nanallclose
from geonode_safe.tests.utilities import TESTDATA, INTERNAL_SERVER_URL
from geonode_safe.tests.utilities import get_web_page

from safe.common.testing import UNITDATA

from geonode.layers.utils import upload, GeoNodeException
from geonode.layers.models import Layer
from geonode.layers.utils import get_valid_user
from geonode.layers.utils import cleanup
from geonode.layers.utils import get_valid_layer_name
 
from django.db import connection, transaction
from django.conf import settings

#---Jeff
from owslib.wcs import WebCoverageService


# FIXME: Can go when OWSLib patch comes on line
def ns(tag):
    return '{http://www.opengis.net/wcs}' + tag
#---


class TestGeoNode(unittest.TestCase):
    """Tests file uploads, metadata etc
    """

    def setUp(self):
        """Create valid superuser
        """
        self.user = get_valid_user()

    def tearDown(self):
        pass

    def test_extension_not_implemented(self):
        """RisikoException is returned for not compatible extensions
        """
        sampletxt = os.path.join(UNITDATA, 'exposure', 'buildings_osm_4326.lic')
        try:
            save_to_geonode(sampletxt, user=self.user)
        except RisikoException, e:
            pass
        else:
            msg = ('Expected an exception for invalid .dbf type')
            raise Exception(msg)

    def test_shapefile(self):
        """Shapefile can be uploaded
        """
        thefile = os.path.join(UNITDATA, 'exposure', 'buildings_osm_4326.shp')
        layer = save_to_geonode(thefile, user=self.user, overwrite=True)
        check_layer(layer, full=True)

        assert isinstance(layer.geographic_bounding_box, basestring)

    def test_asciifile_without_prj(self):
        """ASCII file with without prj file is rejected
        """

        thefile = os.path.join(gisdata.BAD_DATA,
                               'grid_without_projection.asc')

        try:
            uploaded = save_to_geonode(thefile, user=self.user)
        except RisikoException, e:
            pass
        except Exception, e:
            msg = ('Was expecting a %s, got %s instead.' %
                   (RisikoException, type(e)))
            assert e is RisikoException, msg

    def test_tiff(self):
        """GeoTIF file can be uploaded
        """
        thefile = os.path.join(UNITDATA, 'hazard', 'jakarta_flood_design.tif')
        uploaded = save_to_geonode(thefile, user=self.user, overwrite=True)
        check_layer(uploaded, full=True)

    def test_repeated_upload(self):
        """The same file can be uploaded more than once
        """
        thefile = os.path.join(UNITDATA, 'hazard', 'jakarta_flood_design.tif')
        uploaded1 = save_to_geonode(thefile, overwrite=True,
                                    user=self.user)
        check_layer(uploaded1, full=True)
        uploaded2 = save_to_geonode(thefile, overwrite=True,
                                    user=self.user)
        check_layer(uploaded2, full=True)
        uploaded3 = save_to_geonode(thefile, overwrite=False,
                                    user=self.user)
        check_layer(uploaded3, full=True)

        msg = ('Expected %s but got %s' % (uploaded1.name, uploaded2.name))
        assert uploaded1.name == uploaded2.name, msg

        msg = ('Expected a different name when uploading %s using '
               'overwrite=False but got %s' % (thefile, uploaded3.name))
        assert uploaded1.name != uploaded3.name, msg


    def test_non_existing_file(self):
        """RisikoException is returned for non existing file
        """
        sampletxt = os.path.join(UNITDATA, 'smoothoperator.shp')
        try:
            save_to_geonode(sampletxt, user=self.user)
        except RisikoException, e:
            pass
        else:
            msg = ('Expected an exception for non existing file')
            assert False, msg

    def test_non_existing_dir(self):
        """RisikoException is returned for non existing dir
        """
        sampletxt = os.path.join(UNITDATA, 'smoothoperator')
        try:
            uploaded_layers = save_to_geonode(sampletxt, user=self.user)
            for uploaded in uploaded_layers:
                print uploaded
        except RisikoException, e:
            pass
        else:
            msg = ('Expected an exception for non existing dir')
            assert False, msg

    def test_keywords(self):
        """Keywords are read correctly from the .keywords file
        """

        for filename in ['jakarta_flood_design.tif',
                         'multipart_polygons_osm_4326.shp']:

            _, ext = os.path.splitext(filename)
            thefile = os.path.join(UNITDATA, 'hazard', filename)
            uploaded = save_to_geonode(thefile, user=self.user, overwrite=True)

            # Get uploaded keywords from uploaded layer object
            uploaded_keywords = uploaded.keyword_list()
            msg = 'No keywords found in layer %s' % uploaded.name
            assert len(uploaded_keywords) > 0, msg

            # Get reference keywords from file
            keywords_file = thefile.replace(ext, '.keywords')
            f = open(keywords_file, 'r')
            keywords_list = []
            for line in f.readlines():
                keywords_list.append(unicode(line.strip()).replace(': ', ':'))
            f.close()

            # Verify that every keyword from file has been uploaded
            for keyword in keywords_list:
                msg = 'Could not find keyword "%s" in %s' % (keyword,
                                                             uploaded_keywords)
                assert keyword in uploaded_keywords, msg

    def test_metadata_twice(self):
        """Layer metadata can be correctly uploaded multiple times
        """

        # This test reproduces ticket #99 by creating new data,
        # uploading twice and verifying metadata

        # Base test data
        filenames = ['jakarta_flood_design.tif', ]

        for org_filename in filenames:
            org_basename, ext = os.path.splitext(os.path.join(UNITDATA, 'hazard',
                                                              org_filename))

            # Copy data to temporary unique name
            basename = unique_filename(dir='/tmp')

            cmd = '/bin/cp -f %s.keywords %s.keywords' % (org_basename, basename)
            os.system(cmd)

            # Not needed since we are dealing with a raster
            #cmd = '/bin/cp -f %s.prj %s.prj' % (org_basename, basename)
            #os.system(cmd)

            if ext == '.tif':
                layer_type = 'raster'
                filename = '%s.tif' % basename
                cmd = '/bin/cp %s.tif %s' % (org_basename, filename)
                os.system(cmd)
            elif ext == '.shp':
                layer_type = 'vector'
                filename = '%s.shp' % basename
                for e in ['shp', 'shx', 'sbx', 'sbn', 'dbf']:
                    cmd = '/bin/cp %s.%s %s.%s' % (org_basename, e,
                                                   basename, e)
                    os.system(cmd)
            else:
                msg = ('Unknown layer extension in %s. '
                       'Expected .shp or .asc' % filename)
                raise Exception(msg)

            # Repeat multiple times
            for i in range(3):

                # Upload
                layer = save_to_geonode(filename, user=self.user,
                                        overwrite=True)

                # Get metadata
                layer_name = '%s:%s' % (layer.workspace, layer.name)
                metadata = get_metadata(INTERNAL_SERVER_URL,
                                        layer_name)

                # Verify
                assert 'id' in metadata
                assert 'title' in metadata
                assert 'layer_type' in metadata
                assert 'keywords' in metadata
                assert 'bounding_box' in metadata
                assert len(metadata['bounding_box']) == 4

                # Check integrity between Django layer and file
                assert_bounding_box_matches(layer, filename)

                # Check integrity between file and OWS metadata
                ref_bbox = get_bounding_box(filename)
                msg = ('Bounding box from OWS did not match bounding box '
                       'from file. They are\n'
                       'From file %s: %s\n'
                       'From OWS: %s' % (filename,
                                         ref_bbox,
                                         metadata['bounding_box']))

                assert numpy.allclose(metadata['bounding_box'],
                                      ref_bbox), msg
                assert layer.name == metadata['title']
                assert layer_name == metadata['id']
                assert layer_type == metadata['layer_type']

                # Check keywords
                if layer_type == 'raster':
                    category = 'hazard'
                    subcategory = 'flood'
                else:
                    msg = 'Unknown layer type %s' % layer_type
                    raise Exception(msg)

                keywords = metadata['keywords']

                msg = 'Did not find key "category" in keywords: %s' % keywords
                assert 'category' in keywords, msg

                msg = ('Did not find key "subcategory" in keywords: %s'
                       % keywords)
                assert 'subcategory' in keywords, msg

                msg = ('Category keyword %s did not match expected %s'
                       % (keywords['category'], category))
                assert category == keywords['category'], msg

                msg = ('Subcategory keyword %s did not match expected %s'
                       % (keywords['subcategory'], category))
                assert subcategory == keywords['subcategory'], msg

    def test_metadata(self):
        """Metadata is retrieved correctly for both raster and vector data
        """

        # Upload test data
        filenames = [os.path.join('hazard', 'jakarta_flood_design.tif'),
                     os.path.join('exposure', 'buildings_osm_4326.shp')]

        layers = []
        paths = []
        for filename in filenames:
            path = os.path.join(UNITDATA, filename)
            layer = save_to_geonode(path, user=self.user, overwrite=True)

            # Record layer and file
            layers.append(layer)
            paths.append(path)

        # Check integrity
        for i, layer in enumerate(layers):

            if filenames[i].endswith('.shp'):
                layer_type = 'vector'
            elif filenames[i].endswith('.tif'):
                layer_type = 'raster'
            else:
                msg = ('Unknown layer extension in %s. '
                       'Expected .shp or .tif' % filenames[i])
                raise Exception(msg)

            layer_name = '%s:%s' % (layer.workspace, layer.name)
            metadata = get_metadata(INTERNAL_SERVER_URL,
                                    layer_name)

            assert 'id' in metadata
            assert 'title' in metadata
            assert 'layer_type' in metadata
            assert 'keywords' in metadata
            assert 'bounding_box' in metadata
            assert len(metadata['bounding_box']) == 4

            # Check integrity between Django layer and file
            assert_bounding_box_matches(layer, paths[i])

            # Check integrity between file and OWS metadata
            ref_bbox = get_bounding_box(paths[i])
            msg = ('Bounding box from OWS did not match bounding box '
                   'from file. They are\n'
                   'From file %s: %s\n'
                   'From OWS: %s' % (paths[i],
                                     ref_bbox,
                                     metadata['bounding_box']))

            assert numpy.allclose(metadata['bounding_box'],
                                  ref_bbox), msg
            assert layer.name == metadata['title']
            assert layer_name == metadata['id']
            assert layer_type == metadata['layer_type']

            # Check keywords
            if layer_type == 'raster':
                category = 'hazard'
                subcategory = 'flood'
            elif layer_type == 'vector':
                category = 'exposure'
                subcategory = 'building'
            else:
                msg = 'Unknown layer type %s' % layer_type
                raise Exception(msg)

            keywords = metadata['keywords']

            msg = 'Did not find key "category" in keywords: %s' % keywords
            assert 'category' in keywords, msg

            msg = 'Did not find key "subcategory" in keywords: %s' % keywords
            assert 'subcategory' in keywords, msg

            msg = ('Category keyword %s did not match expected %s'
                   % (keywords['category'], category))
            assert category == keywords['category'], msg

            msg = ('Subcategory keyword %s did not match expected %s'
                   % (keywords['subcategory'], category))
            assert subcategory == keywords['subcategory'], msg

    def test_native_raster_resolution(self):
        """Raster layer retains native resolution through Geoserver

        Raster layer can be uploaded and downloaded again with
        native resolution. This is one test for ticket #103
        """

        hazard_filename = os.path.join(UNITDATA, 'hazard', 'jakarta_flood_design.tif')

        # Get reference values
        H = read_layer(hazard_filename)
        A_ref = H.get_data(nan=True)
        depth_min_ref, depth_max_ref = H.get_extrema()

        # Upload to internal geonode
        hazard_layer = save_to_geonode(hazard_filename, user=self.user)
        hazard_name = '%s:%s' % (hazard_layer.workspace, hazard_layer.name)

        # Download data again with native resolution
        bbox = get_bounding_box_string(hazard_filename)
        H = download(INTERNAL_SERVER_URL, hazard_name, bbox)
        A = H.get_data(nan=True)

        # Compare shapes
        msg = ('Shape of downloaded raster was [%i, %i]. '
               'Expected [%i, %i].' % (A.shape[0], A.shape[1],
                                       A_ref.shape[0], A_ref.shape[1]))
        assert numpy.allclose(A_ref.shape, A.shape, rtol=0, atol=0), msg

        # Compare extrema to values reference values (which have also been
        # verified by QGIS for this layer and tested in test_engine.py)
        depth_min, depth_max = H.get_extrema()
        msg = ('Extrema of downloaded file were [%f, %f] but '
               'expected [%f, %f]' % (depth_min, depth_max,
                                      depth_min_ref, depth_max_ref))
        assert numpy.allclose([depth_min, depth_max],
                              [depth_min_ref, depth_max_ref],
                              rtol=1.0e-6, atol=1.0e-10), msg

        # Compare data number by number
        assert nanallclose(A, A_ref, rtol=1.0e-8)

    @numpy.testing.dec.skipif(True, 'Re-enable after talking to Ole')
    def test_specified_raster_resolution(self):
        """Raster layers can be downloaded with specific resolution

        This is another test for ticket #103

        Native test data:

        maumere....asc
        ncols 931
        nrows 463
        cellsize 0.00018

        Population_Jakarta
        ncols         638
        nrows         649
        cellsize      0.00045228819716044

        Population_2010
        ncols         5525
        nrows         2050
        cellsize      0.0083333333333333


        Here we download it at a range of fixed resolutions that
        are both coarser and finer, and check that the dimensions
        of the downloaded matrix are as expected.

        We also check that the extrema of the subsampled matrix are sane
        """

        hazard_filename = os.path.join(UNITDATA, 'hazard', 'jakarta_flood_design.tif')

        # Get reference values
        H = read_layer(hazard_filename)
        depth_min_ref, depth_max_ref = H.get_extrema()
        native_resolution = H.get_resolution()

        # Upload to internal geonode
        hazard_layer = save_to_geonode(hazard_filename, user=self.user)
        hazard_name = '%s:%s' % (hazard_layer.workspace,
                                 hazard_layer.name)

        # Test for a range of resolutions
        for res in [0.02, 0.01, 0.005, 0.002, 0.001, 0.0005,  # Coarser
                    0.0002, 0.0001, 0.00006, 0.00003]:        # Finer

            # Set bounding box
            bbox = get_bounding_box_string(hazard_filename)
            compare_extrema = True

            bb = bboxstring2list(bbox)

            # Download data at specified resolution
            H = download(INTERNAL_SERVER_URL, hazard_name,
                         bbox, resolution=res)
            A = H.get_data()

            # Verify that data has the requested bobx and resolution
            actual_bbox = H.get_bounding_box()
            msg = ('Bounding box for %s was not as requested. I got %s '
                   'but '
                   'expected %s' % (hazard_name, actual_bbox, bb))
            assert numpy.allclose(actual_bbox, bb, rtol=1.0e-6)

            # FIXME (Ole): How do we sensibly resolve the issue with
            #              resx, resy vs one resolution (issue #173)
            actual_resolution = H.get_resolution()[0]

            # FIXME (Ole): Resolution is often far from the requested
            #              see issue #102
            #              Here we have to accept up to 5%
            tolerance102 = 5.0e-2
            msg = ('Resolution of %s was not as requested. I got %s but '
                   'expected %s' % (hazard_name, actual_resolution, res))
            assert numpy.allclose(actual_resolution, res,
                                  rtol=tolerance102), msg

            # Determine expected shape from bbox (W, S, E, N)
            ref_rows = int(round((bb[3] - bb[1]) / res))
            ref_cols = int(round((bb[2] - bb[0]) / res))

            # Compare shapes (generally, this may differ by 1)
            msg = ('Shape of downloaded raster was [%i, %i]. '
                   'Expected [%i, %i].' % (A.shape[0], A.shape[1],
                                           ref_rows, ref_cols))
            assert (ref_rows == A.shape[0] and
                    ref_cols == A.shape[1]), msg

            # Assess that the range of the interpolated data is sane
            if not compare_extrema:
                continue

            # For these test sets we get exact match of the minimum
            msg = ('Minimum of %s resampled at resolution %f '
                   'was %f. Expected %f.' % (hazard_layer.name,
                                             res,
                                             numpy.nanmin(A),
                                             depth_min_ref))
            assert numpy.allclose(depth_min_ref, numpy.nanmin(A),
                                  rtol=0.0, atol=0.0), msg

            # At the maximum it depends on the subsampling
            msg = ('Maximum of %s resampled at resolution %f '
                   'was %f. Expected %f.' % (hazard_layer.name,
                                             res,
                                             numpy.nanmax(A),
                                             depth_max_ref))
            if res < native_resolution[0]:
                # When subsampling to finer resolutions we expect a
                # close match
                assert numpy.allclose(depth_max_ref, numpy.nanmax(A),
                                      rtol=1.0e-10, atol=1.0e-8), msg
            elif res < native_resolution[0] * 10:
                # When upsampling to coarser resolutions we expect
                # ballpark match (~20%)
                assert numpy.allclose(depth_max_ref, numpy.nanmax(A),
                                      rtol=0.17, atol=0.0), msg
            else:
                # Upsampling to very coarse resolutions, just want sanity
                assert 0 < numpy.nanmax(A) <= depth_max_ref

    @numpy.testing.dec.skipif(True, 'Re-enable after talking to Ole')
    def test_raster_scaling(self):
        """Raster layers can be scaled when resampled

        This is a test for ticket #168

        Native test .asc data has

        ncols         5525
        nrows         2050
        cellsize      0.0083333333333333

        Scaling is necessary for raster data that represents density
        such as population per km^2
        """

        for test_filename in ['jakarta_flood_design.tif']:

            raster_filename = os.path.join(UNITDATA, 'hazard', test_filename)

            # Get reference values
            R = read_layer(raster_filename)
            R_min_ref, R_max_ref = R.get_extrema()
            native_resolution = R.get_resolution()

            # Upload to internal geonode
            raster_layer = save_to_geonode(raster_filename, user=self.user)
            raster_name = '%s:%s' % (raster_layer.workspace,
                                     raster_layer.name)

            # Test for a range of resolutions
            for res in [0.02, 0.01, 0.005, 0.002, 0.001, 0.0005,  # Coarser
                        0.0002]:                                  # Finer

                bbox = get_bounding_box_string(raster_filename)

                R = download(INTERNAL_SERVER_URL, raster_name,
                             bbox, resolution=res)
                A_native = R.get_data(scaling=False)
                A_scaled = R.get_data(scaling=True)

                sigma = (R.get_resolution()[0] / native_resolution[0]) ** 2

                # Compare extrema
                expected_scaled_max = sigma * numpy.nanmax(A_native)
                msg = ('Resampled raster was not rescaled correctly: '
                       'max(A_scaled) was %f but expected %f'
                       % (numpy.nanmax(A_scaled), expected_scaled_max))

                assert numpy.allclose(expected_scaled_max,
                                      numpy.nanmax(A_scaled),
                                      rtol=1.0e-8, atol=1.0e-8), msg

                expected_scaled_min = sigma * numpy.nanmin(A_native)
                msg = ('Resampled raster was not rescaled correctly: '
                       'min(A_scaled) was %f but expected %f'
                       % (numpy.nanmin(A_scaled), expected_scaled_min))
                assert numpy.allclose(expected_scaled_min,
                                      numpy.nanmin(A_scaled),
                                      rtol=1.0e-8, atol=1.0e-12), msg

                # Compare elementwise
                msg = 'Resampled raster was not rescaled correctly'
                assert nanallclose(A_native * sigma, A_scaled,
                                   rtol=1.0e-8, atol=1.0e-8), msg

                # Check that it also works with manual scaling
                A_manual = R.get_data(scaling=sigma)
                msg = 'Resampled raster was not rescaled correctly'
                assert nanallclose(A_manual, A_scaled,
                                   rtol=1.0e-8, atol=1.0e-8), msg

                # Check that an exception is raised for bad arguments
                try:
                    R.get_data(scaling='bad')
                except:
                    pass
                else:
                    msg = 'String argument should have raised exception'
                    raise Exception(msg)

                try:
                    R.get_data(scaling='(1, 3)')
                except:
                    pass
                else:
                    msg = 'Tuple argument should have raised exception'
                    raise Exception(msg)

                # Check None option without existence of density keyword
                A_none = R.get_data(scaling=None)
                msg = 'Data should not have changed'
                assert nanallclose(A_native, A_none,
                                   rtol=1.0e-12, atol=1.0e-12), msg

                # Try with None and density keyword
                R.keywords['density'] = 'true'
                A_none = R.get_data(scaling=None)
                msg = 'Resampled raster was not rescaled correctly'
                assert nanallclose(A_scaled, A_none,
                                   rtol=1.0e-12, atol=1.0e-12), msg

                R.keywords['density'] = 'Yes'
                A_none = R.get_data(scaling=None)
                msg = 'Resampled raster was not rescaled correctly'
                assert nanallclose(A_scaled, A_none,
                                   rtol=1.0e-12, atol=1.0e-12), msg

                R.keywords['density'] = 'False'
                A_none = R.get_data(scaling=None)
                msg = 'Data should not have changed'
                assert nanallclose(A_native, A_none,
                                   rtol=1.0e-12, atol=1.0e-12), msg

                R.keywords['density'] = 'no'
                A_none = R.get_data(scaling=None)
                msg = 'Data should not have changed'
                assert nanallclose(A_native, A_none,
                                   rtol=1.0e-12, atol=1.0e-12), msg

    def test_keywords_download(self):
        """Keywords are downloaded from GeoServer along with layer data
        """

        # Upload test data
        filenames = ['padang_tsunami_mw8.tif',]
        filenames = ['jakarta_flood_design.tif',]
        layers = []
        paths = []
        for filename in filenames:
            basename, ext = os.path.splitext(filename)

            path = os.path.join(UNITDATA, 'hazard', filename)

            # Upload to GeoNode
            layer = save_to_geonode(path, user=self.user, overwrite=True)

            # Record layer and file
            layers.append(layer)
            paths.append(path)

        # Check integrity
        for i, layer in enumerate(layers):

            # Get reference keyword dictionary from file
            L = read_layer(paths[i])
            ref_keywords = L.get_keywords()

            # Get keywords metadata from GeoServer
            layer_name = '%s:%s' % (layer.workspace, layer.name)
            metadata = get_metadata(INTERNAL_SERVER_URL,
                                    layer_name)
            assert 'keywords' in metadata
            geo_keywords = metadata['keywords']
            msg = ('Uploaded keywords were not as expected: I got %s '
                   'but expected %s' % (geo_keywords, ref_keywords))
            for kw in ref_keywords:
                # Check that all keywords were uploaded
                # It is OK for new automatic keywords to have appeared
                #  (e.g. resolution) - see issue #171
                assert kw in geo_keywords, msg
                assert ref_keywords[kw] == geo_keywords[kw], msg

            # Download data
            bbox = get_bounding_box_string(paths[i])
            H = download(INTERNAL_SERVER_URL, layer_name, bbox)

            dwn_keywords = H.get_keywords()
            msg = ('Downloaded keywords were not as expected: I got %s '
                   'but expected %s' % (dwn_keywords, geo_keywords))
            assert geo_keywords == dwn_keywords, msg

            # Check that the layer and its .keyword file is there.
            msg = 'Downloaded layer %s was not found' % H.filename
            assert os.path.isfile(H.filename), msg

            kw_filename = os.path.splitext(H.filename)[0] + '.keywords'
            msg = 'Downloaded keywords file %s was not found' % kw_filename
            assert os.path.isfile(kw_filename), msg

            # Check that keywords are OK when reading downloaded file
            L = read_layer(H.filename)
            read_keywords = L.get_keywords()
            msg = ('Keywords in downloaded file %s were not as expected: '
                   'I got %s but expected %s'
                   % (kw_filename, read_keywords, geo_keywords))
            assert read_keywords == geo_keywords, msg


    def test_metadata_available_after_upload(self):
        """Test metadata is available after upload
        """
        # Upload hazard data for this test
        name = 'jakarta_flood_design.tif'
        exposure_filename = os.path.join(UNITDATA, 'hazard', name)
        exposure_layer = save_to_geonode(exposure_filename,
                                         user=self.user, overwrite=True)
        layer_name = exposure_layer.typename
        server_url = settings.GEOSERVER_BASE_URL + '/ows'
        wcs = WebCoverageService(server_url, version='1.0.0')
        layer_appears_immediately = layer_name in wcs.contents

        wait_time = 0.5
        time.sleep(wait_time)

        wcs2 = WebCoverageService(server_url, version='1.0.0')
        layer_appears_afterwards = layer_name in wcs2.contents

        msg = ('Layer %s was not found after %s seconds in WxS contents '
               'on server %s.\n'
               'WCS contents: %s\n' % (layer_name,
                                       wait_time,
                                       server_url,
                                       wcs.contents))

        assert layer_appears_afterwards, msg

        msg = ('Layer %s was not found in WxS contents on server %s.\n'
               'WCS contents: %s\n' % (layer_name, server_url, wcs.contents))

        assert layer_appears_immediately, msg


    def test_geotransform_from_geonode(self):
        """Geotransforms of GeoNode layers can be correctly determined
        """

        for filename in ['lembang_mmi_hazmap.asc',
                         'test_grid.asc']:

            # Upload file to GeoNode
            f = os.path.join(TESTDATA, filename)
            layer = save_to_geonode(f, user=self.user)

            # Read raster file and obtain reference resolution
            R = read_layer(f)
            ref_geotransform = R.get_geotransform()

            # Get geotransform from GeoNode
            layer_name = layer.typename
            metadata = get_metadata(INTERNAL_SERVER_URL, layer_name)

            geotransform_name = 'geotransform'
            msg = ('Could not find attribute "%s" in metadata. '
                   'Values are: %s' % (geotransform_name, metadata.keys()))
            assert geotransform_name in metadata, msg

            gn_geotransform = metadata[geotransform_name]
            msg = ('Geotransform obtained from GeoNode for layer %s '
                   'was not correct. I got %s but expected %s'
                   '' % (layer_name, gn_geotransform, ref_geotransform))
            assert numpy.allclose(ref_geotransform, gn_geotransform), msg


    @numpy.testing.dec.skipif(True, 'Re-enable after talking to Ole')
    def test_data_resampling_example(self):
        """Raster data is unchanged when going through geonode

        """

        # Name file names for hazard level, exposure and expected fatalities
        hazard_filename = os.path.join(TESTDATA, '..', 'hazard', 'maumere_aos_depth_20m_land_wgs84.asc')
        exposure_filename = os.path.join(TESTDATA, 'maumere_pop_prj.shp')

        #------------
        # Hazard data
        #------------
        # Read hazard input data for reference
        H_ref = read_layer(hazard_filename)

        A_ref = H_ref.get_data()
        depth_min_ref, depth_max_ref = H_ref.get_extrema()

        # Upload to internal geonode
        hazard_layer = save_to_geonode(hazard_filename, user=self.user)
        hazard_name = '%s:%s' % (hazard_layer.workspace, hazard_layer.name)

        # Download data again
        bbox = get_bounding_box_string(hazard_filename)  # The biggest
        H = download(INTERNAL_SERVER_URL, hazard_name, bbox)

        A = H.get_data()
        depth_min, depth_max = H.get_extrema()

        # FIXME (Ole): The layer read from file is single precision only:
        # Issue #17
        # Here's the explanation why interpolation below produce slightly
        # different results (but why?)
        # The layer read from file is single precision which may be due to
        # the way it is converted from ASC to TIF. In other words the
        # problem may be in raster.write_to_file. Float64 is
        # specified there, so this is a mystery.
        #print 'A', A.dtype          # Double precision
        #print 'A_ref', A_ref.dtype  # Single precision

        # Compare extrema to values from numpy array
        assert numpy.allclose(depth_max, numpy.nanmax(A),
                              rtol=1.0e-12, atol=1.0e-12)

        assert numpy.allclose(depth_max_ref, numpy.nanmax(A_ref),
                              rtol=1.0e-12, atol=1.0e-12)

        # Compare to reference
        assert numpy.allclose([depth_min, depth_max],
                              [depth_min_ref, depth_max_ref],
                              rtol=1.0e-12, atol=1.0e-12)

        # Compare extrema to values read off QGIS for this layer
        assert numpy.allclose([depth_min, depth_max], [0.0, 16.68],
                              rtol=1.0e-6, atol=1.0e-10)

        # Investigate difference visually
        #from matplotlib.pyplot import matshow, show
        #matshow(A)
        #matshow(A_ref)
        #matshow(A - A_ref)
        #show()

        #print
        for i in range(A.shape[0]):
            for j in range(A.shape[1]):
                if not numpy.isnan(A[i, j]):
                    err = abs(A[i, j] - A_ref[i, j])
                    if err > 0:
                        msg = ('%i, %i: %.15f, %.15f, %.15f'
                               % (i, j, A[i, j], A_ref[i, j], err))
                        raise Exception(msg)
                    #if A[i,j] > 16:
                    #    print i, j, A[i, j], A_ref[i, j]

        # Compare elements (nan & numbers)
        id_nan = numpy.isnan(A)
        id_nan_ref = numpy.isnan(A_ref)
        assert numpy.all(id_nan == id_nan_ref)
        assert numpy.allclose(A[-id_nan], A_ref[-id_nan],
                              rtol=1.0e-15, atol=1.0e-15)

        #print 'MAX', A[245, 283], A_ref[245, 283]
        #print 'MAX: %.15f %.15f %.15f' %(A[245, 283], A_ref[245, 283])
        assert numpy.allclose(A[245, 283], A_ref[245, 283],
                              rtol=1.0e-15, atol=1.0e-15)

        #--------------
        # Exposure data
        #--------------
        # Read exposure input data for reference
        E_ref = read_layer(exposure_filename)

        # Upload to internal geonode
        exposure_layer = save_to_geonode(exposure_filename, user=self.user)
        exposure_name = '%s:%s' % (exposure_layer.workspace,
                                   exposure_layer.name)

        # Download data again
        E = download(INTERNAL_SERVER_URL, exposure_name, bbox)

        # Check exposure data against reference
        coordinates = E.get_geometry()
        coordinates_ref = E_ref.get_geometry()
        assert numpy.allclose(coordinates, coordinates_ref,
                              rtol=1.0e-12, atol=1.0e-12)

        attributes = E.get_data()
        attributes_ref = E_ref.get_data()
        for i, att in enumerate(attributes):
            att_ref = attributes_ref[i]
            for key in att:
                assert att[key] == att_ref[key]

        # Test riab's interpolation function
        I = H.interpolate(E, name='depth')
        icoordinates = I.get_geometry()

        I_ref = H_ref.interpolate(E_ref, name='depth')
        icoordinates_ref = I_ref.get_geometry()

        assert numpy.allclose(coordinates,
                              icoordinates,
                              rtol=1.0e-12, atol=1.0e-12)
        assert numpy.allclose(coordinates,
                              icoordinates_ref,
                              rtol=1.0e-12, atol=1.0e-12)

        iattributes = I.get_data()
        assert numpy.allclose(icoordinates, coordinates)

        N = len(icoordinates)
        assert N == 891

        # Set tolerance for single precision until issue #17 has been fixed
        # It appears that the single precision leads to larger interpolation
        # errors
        rtol_issue17 = 2.0e-3
        atol_issue17 = 1.0e-4

        # Verify interpolated values with test result
        for i in range(N):

            interpolated_depth_ref = I_ref.get_data()[i]['depth']
            interpolated_depth = iattributes[i]['depth']

            assert nanallclose(interpolated_depth,
                               interpolated_depth_ref,
                               rtol=rtol_issue17, atol=atol_issue17)

            pointid = attributes[i]['POINTID']

            if pointid == 263:

                #print i, pointid, attributes[i],
                #print interpolated_depth, coordinates[i]

                # Check that location is correct
                assert numpy.allclose(coordinates[i],
                                      [122.20367299, -8.61300358],
                                      rtol=1.0e-7, atol=1.0e-12)

                # This is known to be outside inundation area so should
                # near zero
                assert numpy.allclose(interpolated_depth, 0.0,
                                      rtol=1.0e-12, atol=1.0e-12)

            if pointid == 148:
                # Check that location is correct
                #print coordinates[i]
                assert numpy.allclose(coordinates[i],
                                      [122.2045912, -8.608483265],
                                      rtol=1.0e-7, atol=1.0e-12)

                # This is in an inundated area with a surrounding depths of
                # 4.531, 3.911
                # 2.675, 2.583
                assert interpolated_depth < 4.531
                assert interpolated_depth < 3.911
                assert interpolated_depth > 2.583
                assert interpolated_depth > 2.675

                #print interpolated_depth
                # This is a characterisation test for bilinear interpolation
                assert numpy.allclose(interpolated_depth, 3.62477215491,
                                      rtol=rtol_issue17, atol=1.0e-12)

            # Check that interpolated points are within range
            msg = ('Interpolated depth %f at point %i was outside extrema: '
                   '[%f, %f]. ' % (interpolated_depth, i,
                                   depth_min, depth_max))

            if not numpy.isnan(interpolated_depth):
                assert depth_min <= interpolated_depth <= depth_max, msg


