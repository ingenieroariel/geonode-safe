import os

from django.core.management import call_command
from django.test import TestCase
from safe.common.testing import UNITDATA
from gisdata import BAD_DATA
from geonode_safe import get_version

class CommandsTestCase(TestCase):
    def test_safeimportlayers(self):
        "Test safeimportlayers with good data."
        layer = os.path.join(UNITDATA, 'hazard', 'jakarta_flood_design.tif')
        args = [layer]
        opts = {}
        call_command('safeimportlayers', *args, **opts)

        # FIXME(Ariel): Implement some asserts

    def test_error_safeimportlayers(self):
        "Test safeimportlayers with bad data."
        args = [BAD_DATA]
        opts = {'verbosity': 3, 'ignore_errors': True}
        call_command('safeimportlayers', *args, **opts)

    def test_version(self):
        "Test version can be obtained programatically."
        version = get_version()
