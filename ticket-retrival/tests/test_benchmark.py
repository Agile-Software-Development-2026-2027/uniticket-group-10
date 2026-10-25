import unittest
import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
from benchmark import evaluate, load_prototype_class
from prototypes.base import Prototype


class Fake(Prototype):
    def search(self, query, k=5):
        if query == 'error':
            raise RuntimeError('do not publish this')
        return {'correct': [(1, 1)], 'second': [(2, 1), (1, .5)], 'empty': [],
                'invalid': [(999, 1)], 'duplicate': [(1, 1), (1, .5)]}[query]


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.prototype = Fake([{'ticket_category_id': 1}, {'ticket_category_id': 2}])

    def test_metrics_and_clock(self):
        data = [{'ticket_category_id': 1, 'queries': {'direct': ['correct', 'second', 'empty', 'error']}}]
        with patch('benchmark.perf_counter', side_effect=[0, .01, 1, 1.02, 2, 2.03, 3, 3.04]):
            result = evaluate(self.prototype, data)
        overall = result['overall']
        self.assertEqual(overall['top1_accuracy'], .25)
        self.assertEqual(overall['hit@1'], .25)
        self.assertEqual(overall['recall@5'], .5)
        self.assertEqual(overall['mrr@5'], .375)
        self.assertEqual(overall['errors'], 1)
        self.assertEqual(overall['abstentions'], 1)
        self.assertAlmostEqual(overall['latency_ms']['mean'], 25)
        self.assertAlmostEqual(overall['latency_ms']['median'], 25)
        self.assertAlmostEqual(overall['latency_ms']['p95'], 40)
        self.assertEqual(overall, result['by_query_type']['direct'])
        self.assertEqual(result['coverage']['uncovered_category_ids'], [2])

    def test_invalid_predictions_are_errors(self):
        result = evaluate(self.prototype, [{'ticket_category_id': 1, 'queries': {'direct': ['invalid', 'duplicate']}}])
        self.assertEqual(result['overall']['errors'], 2)
        self.assertEqual(result['overall']['hit@1'], 0)

    def test_unknown_ground_truth_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.prototype, [{'ticket_category_id': 8, 'queries': {'direct': ['correct']}}])

    def test_empty_set_has_no_fake_metrics(self):
        result = evaluate(self.prototype, [])
        self.assertIsNone(result['overall']['top1_accuracy'])
        self.assertIsNone(result['overall']['latency_ms']['mean'])


class LayoutRegressionTests(unittest.TestCase):
    def test_relocated_personal_prototype_loads(self):
        root = Path(__file__).resolve().parents[1]
        prototype = load_prototype_class(root / 'prototypes/experiments/perfetti-LLMDiretto/prototype.py')
        self.assertTrue(issubclass(prototype, Prototype))
        with self.assertRaises(NotImplementedError):
            prototype(tickets=[])


class DatasetGroundTruthTests(unittest.TestCase):
    def test_original_dataset_has_catalog_coverage_and_review_history(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / 'evaluation_dataset.json').read_text(encoding='utf-8'))
        catalog = json.loads((root / 'tickets.json').read_text(encoding='utf-8'))
        ids = [row['ticket_category_id'] for row in data]
        counts = defaultdict(lambda: defaultdict(int))
        self.assertEqual(set(ids), {row['ticket_category_id'] for row in catalog})
        queries = []
        for row in data:
            self.assertEqual(set(row['queries']), {'direct', 'paraphrase', 'indirect'})
            for query_type, group in row['queries'].items():
                counts[row["ticket_category_id"]][query_type] += len(group)
                self.assertTrue(all(isinstance(q, str) and q.strip() for q in group))
                queries.extend(' '.join(q.casefold().split()) for q in group)
        self.assertTrue(all(set(v.values()) == {3} for v in counts.values()))
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(any(row.get('original_duplicate_queries') for row in data))

    def test_audit_fields_are_not_scored_as_extra_requests(self):
        class Empty(Prototype):
            def search(self, query, k=5):
                return []
        data = [{'ticket_category_id': 1, 'queries': {'direct': ['request']},
                 'original_duplicate_queries': [{'query': 'historical request'}],
                 'gt_review': {'status': 'pending_human_review'}}]
        report = evaluate(Empty([{'ticket_category_id': 1}]), data)
        self.assertEqual(report['overall']['count'], 1)
        self.assertEqual(report['overall']['abstentions'], 1)


class AlternativeGroundTruthTests(unittest.TestCase):
    def setUp(self):
        self.model = Fake([{'ticket_category_id': 1}, {'ticket_category_id': 2}, {'ticket_category_id': 3}])

    def ambiguous(self, targets, queries):
        return {'ticket_category_id': 1, 'review_group': 'ambiguous_gt',
                'ambiguity_group': 'example', 'target_category_ids': targets,
                'queries': {'direct': queries}}

    def test_alternative_top1_is_separate_from_single_target_score(self):
        rows = [{'ticket_category_id': 1, 'queries': {'direct': ['second']}},
                self.ambiguous([1, 2], ['second', 'empty', 'error'])]
        report = evaluate(self.model, rows)
        self.assertEqual(report['overall']['count'], 1)
        self.assertEqual(report['overall']['top1_accuracy'], 0)
        alt = report['ambiguous']['overall']
        self.assertEqual(alt['count'], 3)
        self.assertEqual(alt['any_target_top1_accuracy'], 1 / 3)
        self.assertEqual(alt['errors'], 1)
        self.assertEqual(alt['abstentions'], 1)
        self.assertNotIn('recall@5', alt)
        self.assertEqual(report['ambiguous']['by_group']['example'], alt)
        self.assertEqual(report['dataset_counts']['total'], 4)

    def test_any_target_at_rank_two_and_candidate_miss(self):
        hit = evaluate(self.model, [self.ambiguous([1, 3], ['second'])])['ambiguous']['overall']
        self.assertEqual(hit['any_target_top1_accuracy'], 0)
        self.assertEqual(hit['any_target_hit@5'], 1)
        self.assertEqual(hit['first_candidate_mrr@5'], .5)
        miss = evaluate(self.model, [self.ambiguous([2, 3], ['correct'])])['ambiguous']['overall']
        self.assertEqual(miss['any_target_hit@10'], 0)

    def test_invalid_alternative_targets_are_rejected(self):
        for targets in ([], [1], [1, 1], [1, 999], [True, 2], '1,2'):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                evaluate(self.model, [self.ambiguous(targets, ['correct'])])

    def test_complete_dataset_preserves_query_count_and_ambiguous_tail(self):
        root = Path(__file__).resolve().parents[1]
        rows = json.loads((root / 'evaluation_dataset.json').read_text(encoding='utf-8'))
        start = next(i for i, r in enumerate(rows) if r.get('review_group') == 'ambiguous_gt')
        self.assertTrue(all(r.get('review_group') == 'ambiguous_gt' for r in rows[start:]))
        self.assertEqual(sum(len(qs) for r in rows[start:] for qs in r['queries'].values()), 47)
        self.assertEqual(sum(len(qs) for r in rows for qs in r['queries'].values()), 2061)
