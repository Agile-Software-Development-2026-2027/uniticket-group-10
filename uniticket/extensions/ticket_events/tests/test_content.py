"""Regressione del contratto dei dati e dell’anteprima testuale."""

from django.test import TestCase

from ..content import embedding_text, snapshot
from ..index_fields import INDEX_FIELDS
from .helpers import CategoryTestsSetup


class IndexContentTests(CategoryTestsSetup, TestCase):
    def test_snapshot_contains_exact_index_fields_and_preserves_null(self):
        category = self.create_category(description=None)
        data = snapshot(category.pk, "default")
        self.assertEqual(set(data), set(INDEX_FIELDS))
        self.assertIsNone(data["description"])
        self.assertIsNone(data["organizational_office_id"])

    def test_text_preview_excludes_metadata(self):
        category = self.create_category()
        data = snapshot(category.pk, "default")
        self.assertEqual(
            embedding_text(data),
            "Categoria CREATE test\nDescrizione di prova",
        )
