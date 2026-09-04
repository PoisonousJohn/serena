import logging
from typing import Protocol

from serena.dotnet.assembly_symbol import AssemblySymbol
from serena.symbol import NamePathMatcher

log = logging.getLogger(__name__)


class AssemblyMetadataReader(Protocol):
    """Reads the symbols declared in a .NET assembly's metadata."""

    def read_symbols(self, assembly_path: str) -> list[AssemblySymbol]:
        """
        :param assembly_path: the absolute path of the assembly to read
        :return: the symbols declared in the assembly
        """
        ...


class AssemblySymbolIndex:
    """
    Searches the symbols declared in a set of .NET assemblies by name path.

    Symbols are read lazily on first search and kept in memory afterwards.
    """

    def __init__(self, assembly_paths: list[str], reader: AssemblyMetadataReader) -> None:
        """
        :param assembly_paths: absolute paths of the assemblies to search
        :param reader: the reader used to obtain symbols from an assembly
        """
        self._assembly_paths = assembly_paths
        self._reader = reader
        self._symbols: list[AssemblySymbol] | None = None

    def find(self, name_path_pattern: str, substring_matching: bool = False) -> list[AssemblySymbol]:
        """
        Finds the symbols matching the given name path pattern.

        :param name_path_pattern: the name path pattern to match (see :class:`NamePathMatcher`)
        :param substring_matching: whether to match the last pattern component as a substring
        :return: the matching symbols
        """
        matcher = NamePathMatcher(name_path_pattern, substring_matching=substring_matching)
        return [s for s in self._get_symbols() if matcher.matches_reversed_components(s.iter_name_path_components_reversed())]

    def _get_symbols(self) -> list[AssemblySymbol]:
        """
        :return: the symbols of all assemblies, reading them on first access
        """
        if self._symbols is None:
            symbols: list[AssemblySymbol] = []
            for assembly_path in self._assembly_paths:
                try:
                    symbols.extend(self._reader.read_symbols(assembly_path))
                except Exception as e:
                    # an unreadable assembly must not prevent searching the others
                    log.warning("Failed to read symbols from assembly %s: %s", assembly_path, e)
            self._symbols = symbols
        return self._symbols
