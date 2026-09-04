import importlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING

from solidlsp.ls_config import LanguageServerId

if TYPE_CHECKING:
    from serena.project import Project
    from serena.symbol import LanguageServerSymbol

log = logging.getLogger(__name__)


class DependencySymbolSearch(ABC):
    """
    Searches for symbols in a project's dependencies, i.e. in libraries that are referenced by
    the project but whose sources are not part of it (and which the language server therefore
    does not index).

    One implementation exists per language ecosystem, so that the language-agnostic symbol
    retrieval layer needs no knowledge of any particular language.
    """

    @abstractmethod
    def supports(self, language_server_id: LanguageServerId) -> bool:
        """
        :param language_server_id: the identifier of a language server used by the project
        :return: whether this search applies to the respective language
        """

    @abstractmethod
    def find(self, project: "Project", name_path_pattern: str, substring_matching: bool) -> list["LanguageServerSymbol"]:
        """
        :param project: the project whose dependencies shall be searched
        :param name_path_pattern: the name path pattern to match
        :param substring_matching: whether to match the last pattern component as a substring
        :return: the matching symbols, whose locations are encoded external paths
        """


class DependencySearchRegistry:
    """
    Registry of the dependency searches available in the current process.

    A registry created with ``load_languages=True`` (as :data:`DEPENDENCY_SEARCH_REGISTRY` is)
    obtains the languages' searches by importing the modules named in
    :attr:`_LANGUAGE_SEARCH_MODULES` and reading their module-level ``DEPENDENCY_SEARCHES``
    tuple. Loading happens when the registry is first queried rather than at construction, and
    the result therefore does not depend on which modules an application happened to import
    beforehand. A registry created without it holds exactly what is passed to :meth:`register`.
    """

    _LANGUAGE_SEARCH_MODULES = ("serena.dotnet.assembly_dependency_search",)

    def __init__(self, load_languages: bool = False) -> None:
        """
        :param load_languages: whether to add the searches provided by the supported languages
        """
        self._searches: list[DependencySymbolSearch] = []
        self._are_languages_loaded = not load_languages

    def register(self, search: DependencySymbolSearch) -> None:
        """
        :param search: the search to add
        """
        self._searches.append(search)

    def _load_languages(self) -> None:
        """
        Adds the searches of all language modules, importing any module that is not yet loaded
        """
        if self._are_languages_loaded:
            return
        self._are_languages_loaded = True

        for module_name in self._LANGUAGE_SEARCH_MODULES:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                log.warning(f"Failed to load dependency search module '{module_name}'", exc_info=True)
                continue
            for search in module.DEPENDENCY_SEARCHES:
                self.register(search)

    def find_all_for(self, language_server_ids: Iterable[LanguageServerId]) -> list[DependencySymbolSearch]:
        """
        :param language_server_ids: the language servers used by the project
        :return: the searches applicable to any of the given languages, each at most once
        """
        self._load_languages()
        ids = set(language_server_ids)
        return [s for s in self._searches if any(s.supports(i) for i in ids)]


DEPENDENCY_SEARCH_REGISTRY = DependencySearchRegistry(load_languages=True)
"""
The registry of dependency searches used to search a project's libraries for symbols.
"""
