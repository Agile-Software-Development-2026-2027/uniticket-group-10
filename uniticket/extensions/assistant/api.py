from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
    renderer_classes,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from . import retrieval_service
from .serializers import SearchRequest


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
@renderer_classes([JSONRenderer])
def search(request):
    serializer = SearchRequest(data=request.data)
    serializer.is_valid(raise_exception=True)
    results = retrieval_service.search(serializer.validated_data["query"])
    return Response({"tickets": results})
