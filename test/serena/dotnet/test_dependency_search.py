from serena.dependency_search import DependencySearchRegistry, DependencySymbolSearch
from solidlsp.ls_config import LanguageServerId


class StubSearch(DependencySymbolSearch):
    def __init__(self, language_server_id: LanguageServerId) -> None:
        self._language_server_id = language_server_id

    def supports(self, language_server_id: LanguageServerId) -> bool:
        return language_server_id == self._language_server_id

    def find(self, project, name_path_pattern: str, substring_matching: bool) -> list:
        return []


class TestRegistry:
    def test_search_is_returned_for_the_language_it_supports(self):
        registry = DependencySearchRegistry()
        search = StubSearch(LanguageServerId.CSHARP)
        registry.register(search)

        assert registry.find_all_for([LanguageServerId.CSHARP]) == [search]

    def test_search_is_not_returned_for_other_languages(self):
        registry = DependencySearchRegistry()
        registry.register(StubSearch(LanguageServerId.CSHARP))

        assert registry.find_all_for([LanguageServerId.PYTHON]) == []

    def test_each_search_is_returned_once_for_multiple_matching_languages(self):
        """A project may run several language servers; a search must not be applied twice."""
        registry = DependencySearchRegistry()
        search = StubSearch(LanguageServerId.CSHARP)
        registry.register(search)

        assert registry.find_all_for([LanguageServerId.CSHARP, LanguageServerId.CSHARP]) == [search]

    def test_empty_registry_returns_nothing(self):
        assert DependencySearchRegistry().find_all_for([LanguageServerId.CSHARP]) == []


class TestDotNetRegistration:
    """
    The language's search must be found without depending on the import order of unrelated
    modules, so a freshly created loading registry is used rather than the shared singleton.
    """

    def test_dotnet_search_is_available_for_csharp(self):
        assert DependencySearchRegistry(load_languages=True).find_all_for([LanguageServerId.CSHARP])

    def test_dotnet_search_does_not_claim_unrelated_languages(self):
        assert DependencySearchRegistry(load_languages=True).find_all_for([LanguageServerId.PYTHON]) == []


class TestSymbolToolsIsLanguageAgnostic:
    def test_symbol_tools_module_names_no_language_package(self):
        """Guards the seam: the shared tool must not import a language-specific package."""
        from pathlib import Path

        import serena.tools.symbol_tools as module

        source = Path(module.__file__).read_text(encoding="utf-8")

        assert "dotnet" not in source.lower() and "assembly" not in source.lower()
