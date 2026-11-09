from app.contracts import Category


def test_category_is_visible_by_default():
    category = Category(id=1, name="Certificato di laurea", structure_id=1, url="/tickets/1")

    assert category.hidden is False
