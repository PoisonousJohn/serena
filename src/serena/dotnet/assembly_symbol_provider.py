import logging
import time

from serena.dotnet.assembly_reference_resolver import AssemblyReferenceResolver
from serena.dotnet.assembly_symbol import AssemblySymbol
from serena.dotnet.assembly_symbol_cache import AssemblySymbolCache
from serena.dotnet.assembly_symbol_index import AssemblyMetadataReader, AssemblySymbolIndex, DnFileMetadataReader

log = logging.getLogger(__name__)


class AssemblySymbolProvider:
    """
    Owns a project's index of .NET assembly symbols, reading each referenced assembly at most
    once per version and persisting the result, so that the cost is paid once rather than on
    every search.

    Instances are not thread-safe; a project holds one and warms it up in the background.
    """

    _NEVER_MATCHING_PATTERN = "\x00never-matches"
    """
    A name path pattern that no symbol can bear, used to force the index to obtain its symbols
    without paying for a real match.
    """

    def __init__(self, project_root: str, cache_file_path: str, reader: AssemblyMetadataReader | None = None) -> None:
        """
        :param project_root: the root directory of the project whose dependencies to index
        :param cache_file_path: the path of the file in which to persist the read symbols
        :param reader: the reader to obtain symbols with; defaults to reading PE metadata
        """
        self._project_root = project_root
        self._cache = AssemblySymbolCache(cache_file_path)
        self._reader = reader if reader is not None else DnFileMetadataReader()
        self._index: AssemblySymbolIndex | None = None

    def warm_up(self) -> None:
        """
        Builds the index if it has not been built yet, so that a later search does not have to.
        Intended to be called in the background; failures are logged rather than raised.
        """
        try:
            self._get_index()
        except Exception:
            log.warning("Failed to build the .NET assembly symbol index", exc_info=True)

    def find(self, name_path_pattern: str, substring_matching: bool = False) -> list[AssemblySymbol]:
        """
        :param name_path_pattern: the name path pattern to match (see :class:`NamePathMatcher`)
        :param substring_matching: whether to match the last pattern component as a substring
        :return: the matching symbols declared in the project's referenced assemblies
        """
        return self._get_index().find(name_path_pattern, substring_matching=substring_matching)

    def _get_index(self) -> AssemblySymbolIndex:
        """
        :return: the index, building it (and persisting what it read) on first access
        """
        if self._index is not None:
            return self._index

        started_at = time.monotonic()
        self._cache.load()
        assembly_paths = AssemblyReferenceResolver(self._project_root).resolve()
        index = AssemblySymbolIndex(assembly_paths, self._reader, cache=self._cache)
        # force the reading now, so that the cost and the cache write happen here rather than
        # inside the first search
        index.find(self._NEVER_MATCHING_PATTERN)
        self._cache.save()
        self._index = index
        log.info("Built the .NET assembly symbol index in %.2fs", time.monotonic() - started_at)
        return index
