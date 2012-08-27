import os

from django.core.management import call_command
from django.test import TestCase
from safe.common.testing import UNITDATA

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
        layer = os.path.join(UNITDATA, 'hazard', 'does-not-exist')
        args = [layer]
        opts = {'verbosity': 3}
        call_command('safeimportlayers', *args, **opts)
