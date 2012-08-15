import unittest
import os
from django.test.client import Client
from django.utils import simplejson as json
from django.conf import settings

from geonode.layers.utils import check_geonode_is_up
from geonode.layers.models import Layer
from geonode.layers.utils import get_valid_user

from safe.engine.impact_functions_for_testing import unspecific_building_impact_model

from geonode_safe.storage import save_to_geonode, check_layer
from geonode_safe.tests.utilities import INTERNAL_SERVER_URL
from geonode_safe.tests.utilities import TESTDATA, DEMODATA


class Test_HTTP(unittest.TestCase):
    """Test suite for API
    """

    def setUp(self):
        """Check geonode and create valid superuser
        """
        check_geonode_is_up()
        self.user = get_valid_user()

    def tearDown(self):
        pass

    def test_functions(self):
        """Functions can be retrieved from the HTTP Rest API
        """

        c = Client()
        rv = c.get('/safe/api/functions/')
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
        rv = c.get('/safe/api/layers/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv['Content-Type'], 'application/json')
        data = json.loads(rv.content)

