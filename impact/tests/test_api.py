import unittest
import os
from django.test.client import Client
from django.utils import simplejson as json
from django.conf import settings

# FIXME (Ole): Not sure it is good to rely on GeoNode inside
#              the impact module. It might be better to move
#              these tests to risiko/tests

from geonode.maps.utils import check_geonode_is_up
from geonode.maps.models import Layer

# Use the local GeoServer url inside GeoNode
# The ows bit at the end if VERY important because
# that is the endpoint of the OGC services.
INTERNAL_SERVER_URL = os.path.join(settings.GEOSERVER_BASE_URL, 'ows')

TEST_DATA = os.path.join(os.environ['RIAB_HOME'],
                         'riab_data', 'risiko_test_data')


class Test_HTTP(unittest.TestCase):

    def setUp(self):
        check_geonode_is_up()

    def test_functions(self):
        """Functions can be retrieved from the HTTP Rest API
        """

        c = Client()
        rv = c.get('/api/v1/functions/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)

        msg = ('The api should return a dictionary with at least one item. '
               'The key of that item should be "functions"')
        assert 'functions' in data, msg
        functions = data['functions']

        msg = ('No functions were found in the functions list, '
               'not even the built-in ones')
        assert len(functions) > 0, msg

    def test_layers(self):
        """Layers can be retrieved from the HTTP Rest API
        """

        c = Client()
        rv = c.get('/api/v1/layers/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)

    def test_calculate_fatality(self):
        """Earthquake fatalities calculation via the HTTP Rest API is correct
        """

        c = Client()
        rv = c.post('/api/v1/calculate/', dict(
                   hazard_server=INTERNAL_SERVER_URL,
                   hazard='geonode:earthquake_ground_shaking',
                   exposure='geonode:population_2010_clip',
                   exposure_server=INTERNAL_SERVER_URL,
                   bbox='99.36,-2.199,102.237,0.00',
                   impact_function='Earthquake Fatality Function',
                   impact_level=10,
                   keywords='test,earthquake,fatality',
            ))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)
        assert 'hazard_layer' in data.keys()
        assert 'exposure_layer' in data.keys()
        assert 'run_duration' in data.keys()
        assert 'run_date' in data.keys()
        assert 'layer' in data.keys()
        assert 'bbox' in data.keys()
        assert 'impact_function' in data.keys()

        layer_uri = data['layer']
        #FIXME: This is not a good way to access the layer name
        typename = layer_uri.split('/')[4]
        name = typename.split(':')[1]
        # Check the autogenerated styles were correctly uploaded
        layer = Layer.objects.get(name=name)

        msg = ('A new style should have been created for layer [%s] '
               'got [%s] style instead.' % (name, layer.default_style.name))
        assert layer.default_style.name == name, msg

    def test_calculate_school_damage(self):
        """Earthquake school damage calculation works via the HTTP REST API
        """
        c = Client()

        rv = c.post('/api/v1/calculate/', data=dict(
                   hazard_server=INTERNAL_SERVER_URL,
                   hazard='geonode:lembang_mmi_hazmap',
                   exposure_server=INTERNAL_SERVER_URL,
                   exposure='geonode:lembang_schools',
                   bbox='105.592,-7.809,110.159,-5.647',
                   impact_function='Earthquake School Damage Function',
                   impact_level=10,
                   keywords="test,schools,lembang",
        ))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)
        assert 'hazard_layer' in data.keys()
        assert 'exposure_layer' in data.keys()
        assert 'run_duration' in data.keys()
        assert 'run_date' in data.keys()
        assert 'layer' in data.keys()

        # FIXME (Ole): Download result and check.


if __name__ == '__main__':
    import logging

    # Set up logging
    for _module in ['geonode.maps.utils', 'risiko']:
        _logger = logging.getLogger(_module)
        _logger.addHandler(logging.StreamHandler())
        # available levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
        _logger.setLevel(logging.CRITICAL)

    suite = unittest.makeSuite(Test_HTTP, 'test')
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
