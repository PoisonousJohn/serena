import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from serena.symbol import (
    LanguageServerSymbolLocation,
    LanguageServerSymbolRetriever,
    ReferenceInLanguageServerSymbol,
)

if TYPE_CHECKING:
    from serena.project import Project

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DllSymbolUsages:
    """
    The places in a project that use a symbol declared in an assembly without sources.
    """

    symbol_name_path: str
    """the name path of the symbol within its assembly"""
    assembly_path: str
    """the path of the assembly declaring the symbol"""
    references: list[ReferenceInLanguageServerSymbol]
    """the project symbols referencing it, as reported by the language server"""
    use_site: LanguageServerSymbolLocation | None
    """
    the location from which the references were resolved, or None if the project contains no use
    of the symbol (in which case `references` is empty)
    """


class DllUsageSearch:
    """
    Finds the usages of a symbol that is declared in a .NET assembly without sources.

    Metadata cannot answer this: it records declarations, not positions, and holds no reverse
    references. The language server can, but only from a position inside the workspace, so the
    search establishes the symbol's existence from assembly metadata and then locates a use of it
    in the project's sources, from which the language server resolves the references.

    The use site is located through the language server's semantic tokens. Its symbol tree cannot
    serve: Roslyn was measured to report an externally declared member in neither its workspace
    symbols (a query for `BeginDraw` yields nothing) nor its document symbols, which hold only the
    project's own declarations. Once a use site is known, `textDocument/references` from it returns
    every genuine use and no occurrence in a comment or a string literal.
    """

    _SOURCE_FILE_EXTENSIONS = (".cs",)
    """
    The extensions of the source files that can use a .NET assembly symbol; restricting the scan
    keeps it from tokenising files of unrelated languages in a mixed-language project.
    """
    _TOKEN_ENCODING_LENGTH = 5
    """
    The number of integers encoding one semantic token (delta line, delta start, length, type,
    modifiers), as specified for `textDocument/semanticTokens/full`.
    """

    def __init__(self, project: "Project") -> None:
        """
        :param project: the project whose sources and dependencies to search
        """
        self.project = project
        self._retriever = LanguageServerSymbolRetriever(project)

    def find_usages(self, name_path_pattern: str) -> DllSymbolUsages | None:
        """
        :param name_path_pattern: the name path of the symbol to find usages of, as declared in
            the assembly (e.g. "GraphicsApi/BeginDraw")
        :return: the usages, or None if no referenced assembly declares such a symbol
        """
        assembly_symbols = self.project.get_assembly_symbol_provider().find(name_path_pattern)
        if not assembly_symbols:
            log.info("No referenced assembly declares '%s'", name_path_pattern)
            return None
        assembly_symbol = assembly_symbols[0]

        use_site = self._find_use_site(assembly_symbol.name)
        if use_site is None:
            log.info("'%s' is declared in %s but is not used in the project", name_path_pattern, assembly_symbol.assembly_path)
            return DllSymbolUsages(
                symbol_name_path=assembly_symbol.get_name_path(),
                assembly_path=assembly_symbol.assembly_path,
                references=[],
                use_site=None,
            )

        references = self._retriever.find_referencing_symbols_by_location(use_site)
        return DllSymbolUsages(
            symbol_name_path=assembly_symbol.get_name_path(),
            assembly_path=assembly_symbol.assembly_path,
            references=references,
            use_site=use_site,
        )

    def _find_use_site(self, symbol_name: str) -> LanguageServerSymbolLocation | None:
        """
        Locates a use of the given external symbol among the tokens the language server reports
        for the project's source files.

        Semantic tokens are used rather than a text search because the language server has already
        parsed the file: a comment or a string literal is reported as a single token, so its
        content cannot be mistaken for an identifier, and every candidate is confirmed by
        resolving its definition into the declaring assembly.

        The language server's symbol tree is deliberately not consulted: it holds the project's
        own declarations, and an externally declared member appears in neither its document nor
        its workspace symbols (measured on Roslyn), so querying it costs a full symbol scan and
        can never yield a use site.

        :param symbol_name: the (unqualified) name of the external symbol
        :return: the location of a use, or None if the project contains none
        """
        for relative_path in self._iter_source_file_paths():
            for line, column in self._iter_token_positions_of(relative_path, symbol_name):
                location = LanguageServerSymbolLocation(relative_path=relative_path, line=line, column=column)
                if self._resolves_outside_project(location):
                    return location
        return None

    def _iter_source_file_paths(self) -> Iterator[str]:
        """
        :return: an iterator over the relative paths of the project's source files that may
            contain a use of an external symbol
        """
        for relative_path in self.project.gather_source_files():
            if os.path.splitext(relative_path)[1].lower() in self._SOURCE_FILE_EXTENSIONS:
                yield relative_path

    def _iter_token_positions_of(self, relative_path: str, symbol_name: str) -> Iterator[tuple[int, int]]:
        """
        :param relative_path: the relative path of the source file to inspect
        :param symbol_name: the name the token must bear
        :return: an iterator over the (line, column) positions of the tokens whose text is exactly
            the given name
        """
        language_server = self.project.get_language_server_manager_or_raise().get_language_server(relative_path)
        try:
            with language_server.open_file(relative_path):
                uri = Path(language_server.repository_root_path, relative_path).as_uri()
                response = language_server.server.send_request("textDocument/semanticTokens/full", {"textDocument": {"uri": uri}})
        except Exception as e:
            # a file the language server cannot tokenise must not prevent searching the others
            log.debug("Could not obtain semantic tokens for %s: %s", relative_path, e)
            return
        if not isinstance(response, dict):
            return

        try:
            lines = Path(self.project.project_root, relative_path).read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        # semantic tokens are encoded as 5-tuples relative to the preceding token
        # (see the LSP specification of textDocument/semanticTokens/full)
        data = response.get("data") or []
        line = 0
        column = 0
        for i in range(0, len(data) - 4, self._TOKEN_ENCODING_LENGTH):
            delta_line, delta_column, length = data[i], data[i + 1], data[i + 2]
            line += delta_line
            column = delta_column if delta_line else column + delta_column
            if line >= len(lines):
                continue
            if lines[line][column : column + length] == symbol_name:
                yield line, column

    def _resolves_outside_project(self, location: LanguageServerSymbolLocation) -> bool:
        """
        :param location: the location of a candidate symbol occurrence
        :return: whether its definition lies outside the project, which identifies the occurrence
            as a use of an external symbol rather than a project declaration
        """
        assert location.relative_path is not None and location.line is not None and location.column is not None
        language_server = self.project.get_language_server_manager_or_raise().get_language_server(location.relative_path)
        for definition in language_server.request_definition(location.relative_path, location.line, location.column):
            definition_path = definition.get("relativePath")
            if definition_path is None or definition_path.startswith(".."):
                return True
        return False
