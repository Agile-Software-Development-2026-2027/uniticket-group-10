"""Modello di embedding per la ricerca delle categorie: bge-m3 servito da Ollama.

L'indirizzo si sceglie con EMBEDDING_BASE_URL: l'Ollama locale oppure quello
sul server Unical, raggiunto tramite il tunnel SSH.
"""
import os

from langchain_ollama import OllamaEmbeddings

embedder = OllamaEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "bge-m3"),
    base_url=os.getenv("EMBEDDING_BASE_URL", "http://host.docker.internal:11434"),
    client_kwargs={"timeout": 120},
)
