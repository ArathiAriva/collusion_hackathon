"""Require an explicit, accessible destination for planning messages."""

from copy import deepcopy

from terrarium.agents.base import BaseAgent


class LocalToolDiscovery:
    """Delegate local schemas/names to the same provider used for execution."""

    def __init__(self, fallback, provider, role):
        self.fallback, self.provider, self.role = fallback, provider, role

    def get_tools_for_environment(self, environment_name, phase):
        if environment_name == self.provider.environment_name:
            return self.provider.get_tools(phase, self.role)
        return self.fallback.get_tools_for_environment(environment_name, phase)

    def get_env_tool_names(self, environment_name):
        if environment_name == self.provider.environment_name:
            return self.provider.get_tool_names()
        return self.fallback.get_env_tool_names(environment_name)

    def get_blackboard_tool_names(self):
        return self.fallback.get_blackboard_tool_names()

    def get_tools_for_blackboard(self, phase):
        return self.fallback.get_tools_for_blackboard(phase)


class ChannelAwareAgent(BaseAgent):
    def __init__(self, *args, local_tool_provider=None, **kwargs):
        super().__init__(*args, **kwargs)
        if local_tool_provider is not None:
            self.toolset_discovery = LocalToolDiscovery(
                self.toolset_discovery, local_tool_provider, self.name)

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
