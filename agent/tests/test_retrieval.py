from app.contracts import Category
from app.retrieval import filter_categories


def make_category(category_id, structure_id=1, hidden=False):
    return Category(id=category_id, name=f"Categoria {category_id}", structure_id=structure_id,
                    url=f"/tickets/{category_id}", hidden=hidden)


def ids(categories):
    return [category.id for category in categories]


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
