import unittest

import numpy
import sys
import os
import unittest
import warnings


from geonode_safe.storage import get_layer_descriptors
from geonode_safe.storage import save_to_geonode, check_layer
from geonode_safe.storage import download
from geonode_safe.storage import read_layer

from safe.impact_functions.core import FunctionProvider
from safe.impact_functions.core import requirements_collect
from safe.impact_functions.core import requirement_check
from safe.impact_functions.core import get_admissible_plugins
from safe.impact_functions.core import compatible_layers
from safe.common.testing import UNITDATA

from geonode.layers.utils import get_valid_user
from geonode.layers.utils import upload, file_upload, GeoNodeException

from django.test.client import Client
from django.conf import settings
from django.utils import simplejson as json


DEFAULT_PLUGINS = ('Earthquake Fatality Function',)


# FIXME (Ole): Change H, E to layers.
class BasicFunction(FunctionProvider):
    """Risk plugin for testing

    :author Allen
    :rating 1
    :param requires category=="hazard"
    """

    @staticmethod
    def run(H, E,
            a=0.97429, b=11.037):

        return None


class Test_plugins(unittest.TestCase):
    """Tests of Risiko calculations
    """

    def setUp(self):
        """Create valid superuser
        """
        self.user = get_valid_user()

    def test_plugin_compatibility(self):
        """Default plugins perform as expected
        """

        # Upload a raster and a vector data set
        hazard_filename = os.path.join(UNITDATA, 'hazard',
                                       'jakarta_flood_design.tif')
        hazard_layer = save_to_geonode(hazard_filename)
        check_layer(hazard_layer, full=True)

        exposure_filename = os.path.join(UNITDATA, 'exposure',
                                         'buildings_osm_4326.shp')
        exposure_layer = save_to_geonode(exposure_filename)
        check_layer(exposure_layer, full=True)

        # Test
        plugin_list = get_admissible_plugins()
        assert len(plugin_list) > 0

        geoserver = {'url': settings.GEOSERVER_BASE_URL + 'ows',
                     'name': 'Local Geoserver',
                     'version': '1.0.0',
                     'id': 0}
        metadata = get_layer_descriptors(geoserver['url'])

        msg = 'There were no layers in test geoserver'
        assert len(metadata) > 0, msg

        # Characterisation test to preserve the behaviour of
        # get_layer_descriptors. FIXME: I think we should change this to be
        # a dictionary of metadata entries (ticket #126).
        reference = [['topp:buildings_osm_4326',
                      {'layer_type': 'vector',
                       'category': 'exposure',
                       'subcategory': 'building',
                       'title': 'buildings_osm_4326'}],
                     ['topp:jakarta_flood_design',
                      {'layer_type': 'raster',
                       'category': 'hazard',
                       'subcategory': 'flood',
                       'title': 'Jakarta_flood_like_2007_with_structural_improvements'}]]

        for entry in reference:
            name, mdblock = entry

            i = [x[0] for x in metadata].index(name)

            msg = 'Got name %s, expected %s' % (name, metadata[i][0])
            assert name == metadata[i][0], msg
            for key in entry[1]:
                refval = entry[1][key]
                val = metadata[i][1][key]
                msg = ('Got value "%s" for key "%s" '
                       'Expected "%s"' % (val, key, refval))
                assert refval == val, msg

        # Check plugins are returned
        annotated_plugins = [{'name': name,
                              'doc': f.__doc__,
                              'layers': compatible_layers(f, metadata)}
                             for name, f in plugin_list.items()]

        msg = 'No compatible layers returned'
        assert len(annotated_plugins) > 0, msg


    def test_django_plugins(self):
        """Django plugin functions can be retrieved correctly
        """

        c = Client()
        rv = c.get('/safe/api/functions/')

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)


    def test_plugin_selection(self):
        """Verify the plugins can recognize compatible layers.
        """
        # Upload a raster and a vector data set
        hazard_filename = os.path.join(UNITDATA, 'hazard',
                                       'jakarta_flood_design.tif')
        hazard_layer = save_to_geonode(hazard_filename,
                                       user=self.user,
                                       overwrite=True)
        check_layer(hazard_layer, full=True)

        msg = 'No keywords found in layer %s' % hazard_layer.name
        assert hazard_layer.keywords.count() > 0, msg

        exposure_filename = os.path.join(UNITDATA, 'exposure',
                                         'buildings_osm_4326.shp')
        exposure_layer = save_to_geonode(exposure_filename)
        check_layer(exposure_layer, full=True)
        msg = 'No keywords found in layer %s' % exposure_layer.name
        assert exposure_layer.keywords.count() > 0, msg

        c = Client()
        rv = c.get('/safe/api/functions/')

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)

        assert 'functions' in data

        functions = data['functions']

        # FIXME (Ariel): This test should implement an alternative function to
        # parse the requirements, but for now it will just take the buildings
        # damage one.
        for function in functions:
            if function['name'] == 'Earthquake Building Damage Function':
                layers = function['layers']

                msg_tmpl = 'Expected layer %s in list of compatible layers: %s'

                hazard_msg = msg_tmpl % (hazard_layer.typename, layers)
                assert hazard_layer.typename in layers, hazard_msg

                exposure_msg = msg_tmpl % (exposure_layer.typename, layers)
                assert exposure_layer.typename in layers, exposure_msg
