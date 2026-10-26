"""Check ranking ties, top-set ties, and combinatorial inclusion denominators."""
import itertools
import unittest
from statistics import mean
from derive_subset_metrics import pair_metrics, percentile, size_metrics


class DerivedMetricsTests(unittest.TestCase):
    def test_percentile_endpoints_and_ties(self):
        self.assertEqual(pair_metrics(list(range(15)),14)['reference_pair_percentile'],100)
        self.assertEqual(pair_metrics(list(range(15)),0)['reference_pair_percentile'],0)
        self.assertEqual(pair_metrics([0]*15,0)['reference_pair_percentile'],50)
        self.assertEqual(pair_metrics([0]*15,0)['reference_pair_rank'],1)

    def test_interpolated_quantile(self):
        self.assertAlmostEqual(percentile([0,10,20,30],.9),27)

    def test_all_tied_top_sets_include_every_tie(self):
        agents=list('abcdef');reference=set('ab')
        for k in range(2,6):
            rows=[dict(size=k,members=t,regret_gap=0) for t in itertools.combinations(agents,k)]
            metrics,selected=size_metrics(rows,reference,6,.1)
            self.assertEqual(len(selected),len(rows))
            self.assertAlmostEqual(metrics['top_both_excess_pp'],0)
            self.assertAlmostEqual(metrics['top_one_excess_pp'],0)
            self.assertAlmostEqual(metrics['top_neither_excess_pp'],0)

    def test_best_subset_uses_lowest_regret_agents(self):
        regrets=dict(zip('abcdef',[0,1,2,3,4,5]))
        for k in range(2,6):
            rows=[]
            for members in itertools.combinations(regrets,k):
                gap=mean(v for a,v in regrets.items() if a not in members)-mean(regrets[a] for a in members)
                rows.append(dict(size=k,members=members,regret_gap=gap))
            metrics,selected=size_metrics(rows,set('ab'),6,.1)
            self.assertAlmostEqual(metrics['mean_gap'],0)
            self.assertEqual(max(rows,key=lambda r:r['regret_gap'])['members'],tuple('abcdef'[:k]))
            self.assertTrue(all(r['regret_gap']>=metrics['top_cutoff']-1e-9 for r in selected))


if __name__=='__main__':unittest.main()
