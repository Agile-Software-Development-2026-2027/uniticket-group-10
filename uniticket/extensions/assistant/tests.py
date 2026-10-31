import json
from types import SimpleNamespace
from unittest.mock import patch

from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch, resolve, reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from .api import search
from .views.demo_page import workspace
from .middleware import HtmxRedirectMiddleware
from .retrieval_service import search as retrieve_tickets


class SearchTests(SimpleTestCase):
    def post(self, body, *, authenticated=True, content_type="application/json"):
        request = APIRequestFactory().post("/api/search", body, content_type=content_type)
        if authenticated:
            force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return search(request)

    def test_requires_login(self):
        self.assertEqual(self.post(b'{}', authenticated=False).status_code, 403)

    def test_requires_json(self):
        self.assertEqual(self.post(b'{}', content_type="text/plain").status_code, 415)

    def test_rejects_invalid_payloads(self):
        payloads = [b'{', b'\xff', b'[]', b'{}']
        payloads += [json.dumps({"query": value}).encode() for value in (
            None, 123, 1.5, True, [], {}, "", "   ", "x" * 501,
        )]
        with patch("assistant.api.retrieval_service.search") as retrieve:
            for body in payloads:
                with self.subTest(body=body):
                    response = self.post(body)
                    self.assertEqual(response.status_code, 400)
                    self.assertTrue(response.data)
            retrieve.assert_not_called()

    def test_searches_with_trimmed_query(self):
        tickets = [{"ticket_id": 316}]
        with patch("assistant.api.retrieval_service.search", return_value=tickets) as retrieve:
            response = self.post(b'{"query": "  certificato  "}')
        retrieve.assert_called_once_with("certificato")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"tickets": tickets})

    def test_accepts_maximum_length(self):
        with patch("assistant.api.retrieval_service.search", return_value=[]):
            response = self.post(json.dumps({"query": "x" * 500}).encode())
        self.assertEqual(response.status_code, 200)

    def test_requires_post(self):
        request = APIRequestFactory().get("/api/search")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        self.assertEqual(search(request).status_code, 405)

    def test_accepts_json_with_charset(self):
        with patch("assistant.api.retrieval_service.search", return_value=[]):
            response = self.post(b'{"query": "certificato"}',
                                 content_type="application/json; charset=utf-8")
        self.assertEqual(response.status_code, 200)

    def test_enforces_session_csrf(self):
        # CSRF (Cross-Site Request Forgery): un sito malevolo può indurre il browser
        # a inviare richieste usando i cookie di sessione di un utente autenticato.
        # Django richiede un token CSRF valido per le richieste POST autenticate
        # tramite sessione. Questo test verifica il rifiuto senza token (403)
        # e l'accettazione con cookie e header X-CSRFToken corrispondenti (200),
        # senza usare force_authenticate, che bypasserebbe il controllo di sessione.
        factory = APIRequestFactory(enforce_csrf_checks=True)
        user = SimpleNamespace(is_authenticated=True, is_active=True)
        with patch("assistant.api.retrieval_service.search", return_value=[]) as retrieve:
            request = factory.post("/api/search", {"query": "certificato"}, format="json")
            request.user = user
            self.assertEqual(search(request).status_code, 403)
            retrieve.assert_not_called()

            token = "a" * 32
            request = factory.post("/api/search", {"query": "certificato"},
                                   format="json", HTTP_X_CSRFTOKEN=token)
            request.COOKIES["csrftoken"] = token
            request.user = user
            self.assertEqual(search(request).status_code, 200)
            retrieve.assert_called_once_with("certificato")


class WorkspaceTests(SimpleTestCase):
    def request(self, method="get", url="/assistant"):
        request = getattr(RequestFactory(), method)(url)
        request.user = SimpleNamespace(is_authenticated=True)
        return request

    def test_renders_only_the_chat_layout_without_building_a_ticket_form(self):
        with patch("assistant.views.demo_page.get_object_or_404") as category, \
             patch("assistant.views.demo_page.base_context", side_effect=lambda value: value), \
             patch("assistant.views.demo_page.render", return_value=HttpResponse()) as render:
            response = workspace(self.request(url="/assistant?ticket_id=999"))
        self.assertEqual(response.status_code, 200)
        category.assert_not_called()
        self.assertEqual(render.call_args.args[1], "demo_page/workspace.html")
        self.assertEqual(render.call_args.args[2], {"initial_module_url": ""})

    def test_category_bookmark_only_provides_the_original_form_url(self):
        category = SimpleNamespace(slug="certificate", organizational_structure=SimpleNamespace(slug="dibest"))
        with patch("assistant.views.demo_page.get_object_or_404", return_value=category) as select, \
             patch("assistant.views.demo_page.base_context", side_effect=lambda value: value), \
             patch("assistant.views.demo_page.render", return_value=HttpResponse()) as render:
            response = workspace(self.request(), ticket_id=316)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(select.call_args.kwargs, {"pk": 316})
        self.assertEqual(render.call_args.args[2], {"initial_module_url": reverse("uni_ticket:add_new_ticket", kwargs={
            "structure_slug": "dibest", "category_slug": "certificate",
        })})

    def test_invalid_category_is_not_rendered(self):
        with patch("assistant.views.demo_page.get_object_or_404", side_effect=Http404):
            with self.assertRaises(Http404):
                workspace(self.request(), ticket_id=999)

    def test_category_bookmark_route_is_preserved(self):
        url = reverse("assistant_workspace_category", kwargs={"ticket_id": 316})
        self.assertEqual(url, "/assistant/316")
        self.assertEqual(resolve(url).kwargs, {"ticket_id": 316})

    def test_ticket_posts_are_not_handled_by_the_demo(self):
        response = workspace(self.request(method="post"))
        self.assertEqual(response.status_code, 405)

    def test_requires_login_on_normal_page_navigation(self):
        request = self.request()
        request.user = SimpleNamespace(is_authenticated=False)
        response = workspace(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)


class DirectWidgetNavigationTests(SimpleTestCase):
    def test_search_returns_the_original_uniticket_url(self):
        category = SimpleNamespace(slug="certificate", organizational_structure=SimpleNamespace(slug="dibest"))
        with patch("assistant.retrieval_service.TicketCategory.objects.select_related") as categories:
            categories.return_value.in_bulk.return_value = {316: category}
            results = retrieve_tickets("certificato")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticket_id"], 316)
        self.assertEqual(results[0]["url"], reverse("uni_ticket:add_new_ticket", kwargs={
            "structure_slug": "dibest", "category_slug": "certificate",
        }))
        self.assertEqual(resolve(results[0]["url"]).view_name, "uni_ticket:add_new_ticket")

    def test_no_results_does_not_query_categories(self):
        with patch("assistant.retrieval_service.TicketCategory.objects.select_related") as categories:
            self.assertEqual(retrieve_tickets("nessun risultato"), [])
        categories.assert_not_called()

    def test_deleted_categories_are_not_returned(self):
        with patch("assistant.retrieval_service.TicketCategory.objects.select_related") as categories:
            categories.return_value.in_bulk.return_value = {}
            self.assertEqual(retrieve_tickets("certificato"), [])

    def test_widget_endpoint_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("assistant_open")


class HtmxRedirectTests(SimpleTestCase):
    def test_native_redirects_are_preserved(self):
        response = HttpResponseRedirect("/local/login/?next=/tickets/new/")
        middleware = HtmxRedirectMiddleware(lambda request: response)
        self.assertIs(middleware(RequestFactory().get("/tickets/new/")), response)

    def test_htmx_redirect_navigates_the_whole_page(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                middleware = HtmxRedirectMiddleware(lambda request: HttpResponse(status=status, headers={
                    "Location": "/local/login/?next=/tickets/new/",
                }))
                response = middleware(RequestFactory().get("/tickets/new/", HTTP_HX_REQUEST="true"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["HX-Redirect"], "/local/login/?next=/tickets/new/")

    def test_html_and_error_responses_are_not_replaced(self):
        for status in (200, 403, 404, 500):
            response = HttpResponse("original", status=status)
            middleware = HtmxRedirectMiddleware(lambda request: response)
            self.assertIs(middleware(RequestFactory().get("/tickets/new/", HTTP_HX_REQUEST="true")), response)
