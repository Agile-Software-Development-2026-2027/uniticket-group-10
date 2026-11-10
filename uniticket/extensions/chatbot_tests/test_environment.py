from django.conf import settings
from django.test import SimpleTestCase
from django.urls import URLResolver, get_resolver


class EnvironmentTests(SimpleTestCase):
    """uniTicket starts with our settings and loads all its URLs and views."""

    def test_uniticket_is_installed(self):
        self.assertIn("uni_ticket", settings.INSTALLED_APPS)

    def test_urls_and_views_load(self):
        def assert_views_load(patterns):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    assert_views_load(pattern.url_patterns)
                else:
                    self.assertTrue(callable(pattern.callback), str(pattern))

        patterns = get_resolver().url_patterns
        self.assertTrue(patterns)
        assert_views_load(patterns)
