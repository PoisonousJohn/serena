import logging

from serena.config.serena_config import SerenaConfig
from serena.mcp import SerenaMCPFactory
from serena.tools.tools_base import ToolRegistry


def get_exposed_tool_names(included_optional_tools: tuple[str, ...]) -> set[str]:
    """
    :param included_optional_tools: the names of the optional tools to enable
    :return: the names of the tools an MCP client is offered under that configuration
    """
    cfg = SerenaConfig(log_level=logging.ERROR).with_headless_mode_overrides()
    cfg.included_optional_tools = included_optional_tools
    factory = SerenaMCPFactory(transport="stdio", context="agent")
    factory.agent = factory._create_serena_agent(cfg)
    return {tool.get_name() for tool in factory._iter_tools()}


class TestToolAvailability:
    def test_tool_is_offered_to_clients_when_enabled(self):
        """
        The behaviour that matters: a client actually sees the tool. Asserting the marker class
        instead would pass even while the tool reaches no client.
        """
        assert "find_dll_symbol_usages" in get_exposed_tool_names(("find_dll_symbol_usages",))

    def test_tool_is_absent_unless_enabled(self):
        """It is opt-in, since it applies only to projects referencing .NET assemblies."""
        assert "find_dll_symbol_usages" not in get_exposed_tool_names(())

    def test_tool_name_is_stable(self):
        """The name is the client-facing address of the tool and must not drift."""
        from serena.tools import FindDllSymbolUsagesTool

        assert FindDllSymbolUsagesTool.get_name_from_cls() == "find_dll_symbol_usages"

    def test_enabling_it_is_possible_by_name(self):
        """A user configures the tool by name, so the registry has to know it as an optional one."""
        assert "find_dll_symbol_usages" in ToolRegistry().get_tool_names_optional()


class TestFindSymbolAnswersOnlyAboutProjectSources:
    def test_find_symbol_has_no_search_deps_parameter(self):
        """Dependency search moved to its own tool; two answers to one question would confuse."""
        import inspect

        from serena.tools.symbol_tools import FindSymbolTool

        assert "search_deps" not in inspect.signature(FindSymbolTool.apply).parameters
