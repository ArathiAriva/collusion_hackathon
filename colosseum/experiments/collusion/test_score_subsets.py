import unittest

from experiments.collusion.score_subsets import best, score_subsets


class SubsetScoringTests(unittest.TestCase):
    def setUp(self):
        self.agents = [
            {"agent_name": n, "reward": r, "regret": g,
             "role": "colluder" if n in ("A", "B") else "normal"}
            for n, r, g in zip("ABCD", [12, 6, 4, 0], [3, 1, 0, 4])
        ]

    def test_all_proper_subsets_and_pair_scores(self):
        rows = score_subsets(self.agents)
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(r["size"] == 2 for r in rows), 6)
        assigned = next(r for r in rows if r["is_designated_pair_or_group"])
        self.assertEqual(assigned["members"], ["A", "B"])
        self.assertEqual(assigned["reward_gap"], 7)
        self.assertEqual(assigned["regret_gap"], 0)
        self.assertEqual(best(rows, "reward_gap")["members"], ["A"])
        self.assertEqual(best(rows, "regret_gap")["members"], ["B", "C"])
        for row in rows:
            complement = next(r for r in rows if r["members"] == row["complement"])
            self.assertAlmostEqual(row["reward_gap"], -complement["reward_gap"])
            self.assertAlmostEqual(row["regret_gap"], -complement["regret_gap"])

    def test_missing_regrets_do_not_become_zero(self):
        self.agents[0]["regret"] = None
        rows = score_subsets(self.agents)
        self.assertTrue(all(r["regret_gap"] is None for r in rows))
        self.assertIsNone(best(rows, "regret_gap"))

    def test_no_designated_group_and_ties(self):
        for a in self.agents:
            a.update(role="normal", reward=1, regret=0)
        rows = score_subsets(self.agents)
        self.assertFalse(any(r["is_designated_pair_or_group"] for r in rows))
        self.assertTrue(all(r["reward_gap"] == r["regret_gap"] == 0 for r in rows))

    def test_invalid_agents_rejected(self):
        with self.assertRaises(ValueError):
            score_subsets(self.agents[:1])
        self.agents[1]["agent_name"] = "A"
        with self.assertRaises(ValueError):
            score_subsets(self.agents)


if __name__ == "__main__":
    unittest.main()
