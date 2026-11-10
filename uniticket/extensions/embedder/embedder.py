import requests


class SnowflakeEmbedder:
    model_name="snowflake-arctic-embed2"
    dimension=1024

    def __init__(self, base_url: str="http://host.docker.internal:11434"):
        self.url=f"{base_url}/api/embed"

    #_ iniziale vuol dire che è una funzione interna da non chiamare fuori
    def _finalEmbed(self, texts: list[str]) -> list[list[float]]:
        #manda a ollama la POST con nome del modello, i testi, e un timeout di 120 secondi dopo il quale da errore
        response=requests.post(
            self.url,
            json={"model": self.model_name, "input": texts},
            timeout=120,
        )
        response.raise_for_status()
        # dal json prende solo la parte embeddings ovvero la lista dei vettori
        return response.json()["embeddings"]

    #trasforma il testo di una categoria in un vettore, senza prefisso
    #[0] perchè è l'unico vettore restituito
    def embed(self, text: str) -> list[float]:
        return self._finalEmbed([text])[0]

    #trasforma il testo in un vettore, aggiungendo il prefisso per il modello
    #[0] perchè è l'unico vettore restituito
    def embed_query(self, text: str) -> list[float]:
        return self._finalEmbed([f"query: {text}"])[0]
