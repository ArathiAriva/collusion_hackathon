import unittest
from pathlib import Path

import yaml
from terrarium.networks.factory import build_communication_network

from experiments.common.channel_aware_agent import ChannelAwareAgent
from experiments.common.local_protocol import LocalCommunicationProtocol


class ChannelRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_conditions_schema_delivery_and_privacy(self):
        directory = Path(__file__).resolve().parents[1] / "collusion/configs"
        names = ["P", "Q", "R", "S", "T", "U"]
        for path in sorted(directory.glob("hackathon_2_1_*.yaml")):
            config = yaml.safe_load(path.read_text())
            protocol = LocalCommunicationProtocol(config=config, require_explicit_board_id=True)
            for group in build_communication_network(names, config).channel_groups():
                protocol.megaboard.add_blackboard(group)
            sweep = config["experiment"]["sweeps"][0]
            if sweep["secret_channel_enabled"][0]:
                members = (names if config["experiment"]["collusion"].get("extra_channel_members") == "all"
                           else [names[0], names[-1]])
                protocol.megaboard.add_blackboard(members)
            for name in names:
                with self.subTest(config=path.name, agent=name):
                    allowed = [int(i) for i in protocol.megaboard.get_agent_blackboards(name)]
                    agent = ChannelAwareAgent(None, name, generation_params={"max_tokens": 1500})
                    agent.communication_protocol = protocol
                    agent.current_agent_name = name
                    original = agent.toolset_discovery.get_tools_for_blackboard("planning")
                    params = agent._build_generation_params(original)
                    schema = params["tools"][0]["function"]["parameters"]
                    self.assertIn("blackboard_id", schema["required"])
                    self.assertEqual(schema["properties"]["blackboard_id"]["enum"], allowed)
                    self.assertNotIn("blackboard_id", original[0]["function"]["parameters"]["required"])
                    counts = [len(b.logs) for b in protocol.megaboard.blackboards]
                    missing = await protocol.blackboard_handle_tool_call(
                        "post_message", name, {"message": "Do not misroute me"}, phase="planning")
                    self.assertIn("error", missing)
                    self.assertEqual(missing["available_blackboard_ids"], allowed)
                    self.assertEqual(counts, [len(b.logs) for b in protocol.megaboard.blackboards])
                    for board_id in allowed:
                        before = [len(b.logs) for b in protocol.megaboard.blackboards]
                        result = await protocol.blackboard_handle_tool_call(
                            "post_message", name, {"message": "Explicit destination", "blackboard_id": board_id},
                            phase="planning")
                        self.assertNotIn("error", result)
                        after = [len(b.logs) for b in protocol.megaboard.blackboards]
                        self.assertEqual(after, [n + (i == board_id) for i, n in enumerate(before)])
                    for board_id, board in enumerate(protocol.megaboard.blackboards):
                        if name in board.agents:
                            continue
                        denied = await protocol.blackboard_handle_tool_call(
                            "post_message", name, {"message": "Denied", "blackboard_id": board_id},
                            phase="planning")
                        self.assertIn("error", denied)
                        with self.assertRaises(ValueError):
                            protocol.megaboard.get(board_id, name)

    async def test_legacy_protocol_default_unchanged(self):
        protocol = LocalCommunicationProtocol(config={})
        protocol.megaboard.add_blackboard(["P", "Q"])
        result = await protocol.blackboard_handle_tool_call(
            "post_message", "P", {"message": "Legacy default"}, phase="planning")
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
