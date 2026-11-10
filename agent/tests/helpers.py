"""Dati e modelli finti condivisi dai test."""

from langchain_core.embeddings import Embeddings

from app.contracts import Category


def make_category(category_id, name="", structure_id=1, hidden=False):
    return Category(id=category_id, name=name or f"Categoria {category_id}", structure_id=structure_id,
                    url=f"/tickets/{category_id}", hidden=hidden)


def ids(categories):
    return [category.id for category in categories]


class KeywordEmbedder(Embeddings):
    """Embedder finto: ogni numero del vettore conta quante volte compare una parola chiave."""

    KEYWORDS = ["laurea", "tasse", "biblioteca"]

    def __init__(self):
        self.documents = []

    def embed_documents(self, texts):
        self.documents.extend(texts)
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [text.lower().count(keyword) for keyword in self.KEYWORDS]
