import requests
import os


class SnowflakeEmbedder:
    model_name="snowflake-arctic-embed2"
    dimension=1024

    def __init__(self, base_url: str | None=None):
        base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        self.url=f"{base_url}/api/embed"


    def _finalEmbed(self, texts: list[str]) -> list[list[float]]:
        response=requests.post(
            self.url,
            json={"model": self.model_name, "input": texts},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["embeddings"]


    def embed(self, text: str) -> list[float]:
        return self._finalEmbed([text])[0]

    
    def embed_query(self, text: str) -> list[float]:
        return self._finalEmbed([f"query: {text}"])[0]
