"""Adatta a HTMX i redirect emessi dalle viste originali, senza duplicarne i controlli di accesso."""

from django.http import HttpResponse


class HtmxRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.headers.get("HX-Request") == "true" and response.status_code in (301, 302, 303, 307, 308):
            # Login e altri redirect devono navigare tutta la pagina, non finire nell’area del modulo.
            return HttpResponse(headers={"HX-Redirect": response["Location"]})
        return response
