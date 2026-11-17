"""Ricerca semantica delle categorie proponibili all'utente dell'assistente."""

import logging

from api_rest.authorizations import AuthorizationToken
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

# qdrant e embedder snowflake
from ticket_events.orchestrator import index_repository, provider
# formato nel quale bisogna restituire le categorie, e le categorie che puo vedere l'utente
from .catalog import AvailableCategorySerializer, available_categories


logger=logging.getLogger(__name__)


# permette di controllare l'URL se è formattato bene. qui dichiari solo le regole
# mette i dati validati in validated_data
class CategorySearchSerializer(serializers.Serializer):
    # obbligatorio non vuoto massimo di 500 caratteri
    query=serializers.CharField(max_length=500)
    top_k=serializers.IntegerField(min_value=1,max_value=100,default=50)
    # categorie già scartate
    excluded_category_ids=serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)
    # per limitare la ricerca a certe strutture
    structure_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)

class CategorySearchView(APIView):
    # autenticazione con cookie di sessione
    authentication_classes=[AuthorizationToken, SessionAuthentication]
    permission_classes=[IsAuthenticated]

    def get(self,request):
        # parametri dopo il ?
        params=CategorySearchSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)

        # validated_data contiene già i valori controllati e convertiti
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

        # se dopo i filtri non resta niente, restituisce subito una lista vuota così non chiama ollama
        if not categories:
            return Response([])

        try:
            # embedda la query tramite snowflake
            vector=provider.embed_query(query)
            # search torna gli id delle 50 categorie piu simili
            ranked_ids=index_repository.search(vector,top_k,list(categories))
        except Exception:
            logger.exception("Category search failed")
            return Response({"detail": "Search unavailable"}, status=503)

        ranked = [categories[category_id] for category_id in ranked_ids if category_id in categories]

        # AvailableCategorySerializer trasforma ogni categoria in JSON con gli stessi campi di angelo
        # many=True vuol dire che è una lista di categorie, non una sola
        # il risultato è la lista ordinata che il client dell'agente legge come Catalog
        return Response(AvailableCategorySerializer(ranked,many=True).data)

        

