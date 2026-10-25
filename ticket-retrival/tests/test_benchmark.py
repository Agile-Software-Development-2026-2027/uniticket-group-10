import unittest
from unittest.mock import patch
from benchmark import evaluate, load_prototype_class
from retrival.base import Prototype


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
