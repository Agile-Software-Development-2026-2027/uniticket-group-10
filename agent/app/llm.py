"""Ollama locale, raggiungibile dal container tramite l'host Docker."""
import os
from langchain_ollama import ChatOllama

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "qwen3.5:9b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
    temperature=0,
    client_kwargs={"timeout": 20},
)
