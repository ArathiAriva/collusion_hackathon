"""Require an explicit, accessible destination for planning messages."""

from copy import deepcopy

from terrarium.agents.base import BaseAgent


class ChannelAwareAgent(BaseAgent):
    def _build_generation_params(self, tool_set):
        tools = deepcopy(tool_set)
        for tool in tools:
            function = tool.get("function", {})
            if function.get("name") != "post_message":
                continue
            ids = self.communication_protocol.megaboard.get_agent_blackboards(
                self.current_agent_name
            )
            parameters = function["parameters"]
            required = parameters.setdefault("required", [])
            if "blackboard_id" not in required:
                required.append("blackboard_id")
            parameters["properties"]["blackboard_id"]["enum"] = [int(i) for i in ids]
            function["description"] = (
                "Post a message to one of your accessible blackboards. "
                "Explicitly choose its blackboard_id from the allowed IDs. "
                "Only members of that board can read the message."
            )
        return super()._build_generation_params(tools)
