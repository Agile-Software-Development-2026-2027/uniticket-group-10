"""Ricerca semantica delle categorie proponibili all'utente dell'assistente."""

import logging

from api_rest.authorizations import AuthorizationToken
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView


from ticket_events.orchestrator import index_repository, provider

from .catalog import AvailableCategorySerializer, available_categories


logger=logging.getLogger(__name__)



class CategorySearchSerializer(serializers.Serializer):
    query=serializers.CharField(max_length=500)
    top_k=serializers.IntegerField(min_value=1,max_value=100,default=50)
    excluded_category_ids=serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)
    structure_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)

class CategorySearchView(APIView):
    authentication_classes=[AuthorizationToken, SessionAuthentication]
    permission_classes=[IsAuthenticated]

    def get(self,request):
        params=CategorySearchSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)

        query=params.validated_data["query"]
        top_k=params.validated_data["top_k"]
        categories = {
            category.id: category
            for category in available_categories(
                request.user,
                excluded_category_ids=params.validated_data["excluded_category_ids"],
                structure_ids=params.validated_data["structure_ids"],
            )
        }

        
        if not categories:
            return Response([])

        try:
            vector=provider.embed_query(query)
            ranked_ids=index_repository.search(vector,top_k,list(categories))
        except Exception:
            logger.exception("Category search failed")
            return Response({"detail": "Search unavailable"}, status=503)

        ranked = [categories[category_id] for category_id in ranked_ids if category_id in categories]

        return Response(AvailableCategorySerializer(ranked,many=True).data)

        

