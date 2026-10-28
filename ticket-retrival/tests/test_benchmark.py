import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from benchmark import _metrics, evaluate, load_prototype_class
from prototypes.base import Prototype
from prototypes.models import Ticket


class Fake(Prototype):
    def search(self, query, k=5):
        if query == 'error':
            raise RuntimeError('do not publish this')
        return {'correct': [(1, 1)], 'second': [(2, 1), (1, .5)], 'empty': [],
                'invalid': [(999, 1)], 'duplicate': [(1, 1), (1, .5)]}[query]


class BenchmarkTests(unittest.TestCase):
    def test_full_ranking_measures_p95_beyond_ten_and_preserves_hit_cutoffs(self):
        prototype = Mock(spec=Prototype)
        prototype.tickets = [Ticket(id=i, title=f"Ticket {i}") for i in range(1, 21)]
        prototype.search.side_effect = [
            [(ticket_id, 1.0) for ticket_id in [*range(2, rank + 1), 1, *range(rank + 1, 21)]]
            for rank in (1, 5, 10, 11, 20)
        ] + [[(i, 1.0) for i in range(2, 21)]]
        result = evaluate(prototype, [{"ticket_category_id": 1, "queries": {
            "direct": ["primo", "quinto", "decimo", "undicesimo", "ultimo"],
            "indirect": ["non trovato"],
        }}])
        self.assertEqual([case["rank"] for case in result["cases"]], [1, 5, 10, 11, 20, None])
        self.assertEqual(len(result["cases"][4]["predicted_ids"]), 20)
        self.assertEqual(result["by_query_type"]["direct"]["p95_rank"], 20)
        self.assertIsNone(result["overall"]["p95_rank"])
        self.assertAlmostEqual(result["overall"]["hit@1"], 1 / 6)
        self.assertAlmostEqual(result["overall"]["hit@5"], 2 / 6)
        self.assertAlmostEqual(result["overall"]["hit@10"], 3 / 6)
        self.assertAlmostEqual(result["overall"]["mrr@5"], (1 + 1 / 5) / 6)
        self.assertEqual(result["by_ticket"][1], {"count": 6, "hit@10": .5})
        for call in prototype.search.call_args_list:
            self.assertEqual(call.kwargs, {"k": 20})

    def test_p95_rank_includes_missing_results_in_the_tail(self):
        for ranks, expected in (
            ([], None), ([None], None), ([2, 1], 2),
            ([1] * 19 + [None], 1),
            ([1] * 18 + [10, None], 10),
            ([1] * 18 + [None, None], None),
        ):
            with self.subTest(ranks=ranks):
                self.assertEqual(_metrics(ranks)["p95_rank"], expected)

    def setUp(self):
        self.prototype = Fake([Ticket(id=1, title="Uno"), Ticket(id=2, title="Due")])

    def test_metrics_and_clock(self):
        data = [{'ticket_category_id': 1, 'queries': {'direct': ['correct', 'second', 'empty', 'error']}}]
        with patch('benchmark.perf_counter', side_effect=[0, .01, 1, 1.02, 2, 2.03, 3, 3.04]):
            result = evaluate(self.prototype, data)
        overall = result['overall']
        self.assertNotIn('top1_accuracy', overall)
        self.assertEqual(overall['hit@1'], .25)
        self.assertEqual(overall['hit@5'], .5)
        for k in (1, 5, 10):
            self.assertNotIn(f'recall@{k}', overall)
        self.assertEqual(overall['mrr@5'], .375)
        self.assertIsNone(overall['p95_rank'])
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

    def test_ticket_success_rates_group_rows_and_exclude_tickets_without_queries(self):
        self.prototype.tickets.append(Ticket(id=3, title="Tre"))
        result = evaluate(self.prototype, [
            {'ticket_category_id': 1, 'queries': {'direct': ['correct', 'error']}},
            {'ticket_category_id': 1, 'queries': {'indirect': ['empty', 'invalid']}},
            {'ticket_category_id': 2, 'queries': {'direct': ['correct', 'empty']}},
            {'ticket_category_id': 3, 'queries': {'direct': []}},
        ])
        self.assertEqual(result['by_ticket'], {
            1: {'count': 4, 'hit@10': .25},
            2: {'count': 2, 'hit@10': 0},
        })
        self.assertEqual(result['coverage']['tickets_without_hit@10'], 1)
        self.assertEqual(result['coverage']['ticket_ids_without_hit@10'], [2])
        self.assertEqual(result['coverage']['uncovered_category_ids'], [3])
        serialized = json.loads(json.dumps(result))
        self.assertEqual(serialized['by_ticket']['1']['hit@10'], .25)

    def test_unknown_ground_truth_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.prototype, [{'ticket_category_id': 8, 'queries': {'direct': ['correct']}}])

    def test_empty_set_has_no_fake_metrics(self):
        result = evaluate(self.prototype, [])
        self.assertIsNone(result['overall']['hit@1'])
        self.assertIsNone(result['overall']['p95_rank'])
        self.assertIsNone(result['overall']['latency_ms']['mean'])
        self.assertEqual(result['by_ticket'], {})
        self.assertEqual(result['coverage']['tickets_without_hit@10'], 0)
        self.assertEqual(result['coverage']['ticket_ids_without_hit@10'], [])


class LayoutRegressionTests(unittest.TestCase):
    def test_relocated_personal_prototype_loads(self):
        root = Path(__file__).resolve().parents[1]
        prototype = load_prototype_class(root / 'prototypes/experiments/perfetti-LLMDiretto/prototype.py')
        self.assertTrue(issubclass(prototype, Prototype))
        with self.assertRaises(NotImplementedError):
            prototype(tickets=[])

    
   # def test_duplicate_tail_remains_evaluated(self):
    #    class Empty(Prototype):
     #       def search(self, query, k=5):
      #          return []
       # root = Path(__file__).resolve().parents[1]
        #data = json.loads((root / 'evaluation_dataset_a1.json').read_text(encoding='utf-8'))
        #catalog = json.loads((root / 'tickets.json').read_text(encoding='utf-8'))
        #tail_start = next(i for i, row in enumerate(data) if row.get('review_group'))
        #self.assertTrue(all(row.get('review_group') == 'duplicate_queries_pending_review' for row in data[tail_start:]))
        #expected = sum(len(qs) for row in data for qs in row['queries'].values())
        #regular_count = sum(len(qs) for row in data[:tail_start] for qs in row['queries'].values())
        #report = evaluate(Empty(catalog), data)
        #self.assertEqual(report['overall']['count'], expected)
        #self.assertGreater(expected, regular_count)
        #self.assertEqual(report['overall']['abstentions'], expected)
        #self.assertEqual(report['coverage']['uncovered_category_ids'], [])
