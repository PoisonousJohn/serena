class TestToolRegistration:
    def test_tool_is_registered_and_optional(self):
        """Optional, because it only applies to projects that reference .NET assemblies."""
        from serena.tools import FindDllSymbolUsagesTool
        from serena.tools.tools_base import ToolMarkerOptional

        assert issubclass(FindDllSymbolUsagesTool, ToolMarkerOptional)

    def test_tool_name_is_stable(self):
        from serena.tools import FindDllSymbolUsagesTool

        assert FindDllSymbolUsagesTool.get_name_from_cls() == "find_dll_symbol_usages"


class TestSearchDepsIsGone:
    def test_find_symbol_has_no_search_deps_parameter(self):
        """It was replaced by a dedicated tool; leaving it would offer two answers to one question."""
        import inspect

        from serena.tools.symbol_tools import FindSymbolTool

        assert "search_deps" not in inspect.signature(FindSymbolTool.apply).parameters

    def test_symbol_tools_module_names_no_language_package(self):
        from pathlib import Path

        import serena.tools.symbol_tools as module

        source = Path(module.__file__).read_text(encoding="utf-8")

        assert "dotnet" not in source.lower() and "assembly" not in source.lower()
