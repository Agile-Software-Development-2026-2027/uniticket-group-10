from django.conf import settings
from django.test import SimpleTestCase
from django.urls import get_resolver


class EnvironmentTests(SimpleTestCase):
    """uniTicket starts with our settings and loads all its URLs and views."""

    def test_uniticket_is_installed(self):
        self.assertIn("uni_ticket", settings.INSTALLED_APPS)
        
    def test_urls_load(self):
        self.assertTrue(get_resolver().url_patterns)
