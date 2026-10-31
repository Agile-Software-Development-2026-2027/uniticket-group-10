from django.apps import apps
from django.test import SimpleTestCase


class DjangoSetupSmokeTest(SimpleTestCase):
    def test_django_apps_are_ready(self):
        self.assertTrue(apps.ready)
