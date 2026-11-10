from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import AssistantThread


class CreateThreadView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        thread = AssistantThread.objects.create(
            user=request.user,
        )

        return Response(
            {"thread_id": str(thread.id)},
            status=status.HTTP_201_CREATED,
        )
