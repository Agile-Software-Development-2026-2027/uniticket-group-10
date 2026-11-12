import pytest

from app.retrieval import Retriever, filter_categories
from helpers import KeywordEmbedder, ids, make_category


def test_hidden_categories_are_never_returned():
    catalog = [make_category(1), make_category(2, hidden=True)]

    assert ids(filter_categories(catalog)) == [1]


def test_excluded_categories_are_never_returned():
    catalog = [make_category(1), make_category(2), make_category(3)]

    assert ids(filter_categories(catalog, exclude=[2])) == [1, 3]


def test_only_categories_of_the_given_structures_are_returned():
    catalog = [make_category(1, structure_id=10), make_category(2, structure_id=20),
               make_category(3, structure_id=30)]

    assert ids(filter_categories(catalog, structure_ids=[10, 30])) == [1, 3]


def test_structure_ids_and_exclude_work_together():
    catalog = [make_category(1, structure_id=10), make_category(2, structure_id=10),
               make_category(3, structure_id=20)]

    assert ids(filter_categories(catalog, exclude=[1], structure_ids=[10])) == [2]


def test_omitted_or_empty_structure_ids_apply_no_filter():
    catalog = [make_category(1, structure_id=10), make_category(2, structure_id=20)]

    assert ids(filter_categories(catalog)) == [1, 2]
    assert ids(filter_categories(catalog, structure_ids=[])) == [1, 2]


def test_categories_are_ranked_by_similarity_to_the_query():
    catalog = [make_category(1, "Pagamento tasse"), make_category(2, "Certificato di laurea"),
               make_category(3, "Laurea e tasse")]

    results = Retriever(KeywordEmbedder()).search("certificato di laurea", catalog, top_k=3)

    assert ids(results) == [2, 3, 1]


def test_results_respect_top_k():
    catalog = [make_category(category_id, "Certificato di laurea") for category_id in range(1, 6)]

    results = Retriever(KeywordEmbedder()).search("laurea", catalog, top_k=2)

    assert len(results) == 2


def test_filters_are_applied_before_top_k():
    catalog = [make_category(1, "Certificato di laurea", structure_id=10),
               make_category(2, "Laurea e tasse", structure_id=20)]

    results = Retriever(KeywordEmbedder()).search("laurea", catalog, top_k=1, structure_ids=[20])

    assert ids(results) == [2]


def test_category_vectors_are_computed_only_once():
    embedder = KeywordEmbedder()
    retriever = Retriever(embedder)
    catalog = [make_category(1, "Certificato di laurea"), make_category(2, "Pagamento tasse")]

    retriever.search("laurea", catalog, top_k=1)
    retriever.search("tasse", catalog, top_k=1)

    assert sorted(embedder.documents) == ["Certificato di laurea", "Pagamento tasse"]


def test_top_k_must_be_at_least_one():
    with pytest.raises(ValueError):
        Retriever(KeywordEmbedder()).search("laurea", [make_category(1)], top_k=0)
