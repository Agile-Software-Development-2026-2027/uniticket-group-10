import httpx

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from uni_ticket.settings import (
    EMPLOYEE_ATTRIBUTE_NAME,
    USER_ATTRIBUTE_NAME,
)

def get_identifier(user):
    # Try getting the employee identifier.
    identifier = getattr(user, EMPLOYEE_ATTRIBUTE_NAME, None)
    if identifier:
        return (int(identifier), True)

    # Try getting the user identifier.
    identifier = getattr(user, USER_ATTRIBUTE_NAME, None)
    if identifier:
        return (int(identifier), False)

    raise Exception("Could not find user identifier")

class SetContextView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_identifier, user_is_employee = get_identifier(request.user)

        request_data = {
            "selected_form" : request.data["selected_form"],
            "user_first_name" : request.user.first_name,
            "user_last_name" : request.user.last_name,
            "user_email" : request.user.email,
            "user_identifier" : user_identifier,
            "user_is_employee" : user_is_employee
        }

        print("Sending request with data:")
        print(request_data)

        client = httpx.Client(
            timeout=httpx.Timeout(150.0, connect=10.0),
            follow_redirects=False,
        )

        try:
            upstream_request = client.build_request(
                "POST",
                settings.ASSISTANT_CONTEXT_URL,
                json=request_data,
                headers={
                    "Accept": "text/json",
                },
            )
            upstream = client.send(upstream_request)
        except httpx.RequestError:
            client.close()
            logger.exception("Agent context set failed")
            return Response({"detail": "Agent unavailable"}, status=503)

        return Response({}, status=200)
