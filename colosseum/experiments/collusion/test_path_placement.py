"""Offline checks for moving the same coalition within the path."""
import random
import unittest
from pathlib import Path

import yaml
from terrarium.networks import build_communication_network

from experiments.collusion.run import _network_agent_order, _select_colluders


class PathPlacementTests(unittest.TestCase):
    def test_same_pair_more_neighbours_without_changing_turn_order(self):
        names = list("ABCDEF")
        before = names.copy()
        for seed in range(101, 106):
            orders = []
            for placement in ("original", "swap_endpoints_inward"):
                cfg = {"communication_network": {"topology": "path",
                       "consolidate_channels": True, "path_order": placement}}
                rng = random.Random(seed)
                pair = _select_colluders(agent_names=names, count=2,
                                         strategy="first_and_last", rng=rng)
                network_names = _network_agent_order(names, cfg)
                groups = [set(g) for g in build_communication_network(network_names, cfg).channel_groups()]
                self.assertEqual(pair, ["A", "F"])
                self.assertEqual(len(groups), 5)
                self.assertFalse(any(set(pair) <= g for g in groups))
                degree = 1 if placement == "original" else 2
                for name in pair:
                    self.assertEqual(sum(name in g for g in groups), degree)
                if placement != "original":
                    self.assertEqual(network_names, list("BACDFE"))
                turns = names.copy()
                rng.shuffle(turns)
                orders.append(turns)
            self.assertEqual(*orders)
        self.assertEqual(names, before)

    def test_followup_configs_only_change_placement_and_output_metadata(self):
        base = Path(__file__).parent / "configs"
        for followup in sorted((base / "interior_placement").glob("*.yaml")):
            original = yaml.safe_load((base / followup.name).read_text())
            changed = yaml.safe_load(followup.read_text())
            self.assertEqual(changed["communication_network"].pop("path_order"), "swap_endpoints_inward")
            self.assertEqual(changed["experiment"]["max_concurrent_runs"], 1)
            # Scheduling is serial to match the original batch wrapper's override.
            original["experiment"]["max_concurrent_runs"] = 1
            self.assertNotEqual(original["experiment"]["output_dir"], changed["experiment"]["output_dir"])
            for cfg in (original, changed):
                cfg["simulation"].pop("tags")
                cfg["experiment"].pop("tag")
                cfg["experiment"].pop("output_dir")
                cfg["experiment"]["sweeps"][0].pop("name")
            self.assertEqual(original, changed)

    def test_invalid_placement_fails_instead_of_silently_ignoring(self):
        for topology, order, count in [("complete", "swap_endpoints_inward", 6),
                                       ("path", "swap_endpoints_inward", 3),
                                       ("path", "typo", 6)]:
            cfg = {"communication_network": {"topology": topology, "path_order": order}}
            with self.assertRaises(ValueError):
                _network_agent_order(list("ABCDEF")[:count], cfg)


if __name__ == "__main__":
    unittest.main()
