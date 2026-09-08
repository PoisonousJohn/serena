import gzip
import logging
import os
import pickle
from dataclasses import dataclass

from serena.dotnet.assembly_symbol import AssemblySymbol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AssemblyFingerprint:
    """
    The identity of an assembly file's content, used to detect that a cached entry is stale.

    Modification time and size are used rather than a content hash, because hashing 55 MB of
    assemblies would cost a large fraction of the reading time the cache exists to avoid.
    """

    mtime_ns: int
    size: int

    @classmethod
    def of(cls, assembly_path: str) -> "_AssemblyFingerprint | None":
        """
        :param assembly_path: the path of the assembly to fingerprint
        :return: the fingerprint, or None if the file cannot be inspected (e.g. it was deleted)
        """
        try:
            stat = os.stat(assembly_path)
        except OSError:
            return None
        return cls(mtime_ns=stat.st_mtime_ns, size=stat.st_size)


@dataclass(frozen=True)
class _CacheEntry:
    fingerprint: _AssemblyFingerprint
    symbols: list[AssemblySymbol]


class AssemblySymbolCache:
    """
    Persists the symbols read from .NET assemblies, so that the expensive metadata reading is
    performed once per assembly version rather than once per search.

    Entries are invalidated individually: a rebuilt library invalidates its own entry only, which
    matters because a project's assemblies are dominated by unchanging third-party ones.
    """

    _FORMAT_VERSION = 1
    """
    Version of the persisted structure; a mismatch discards the file rather than risking an
    incompatible unpickling after the symbol representation changes.
    """

    def __init__(self, cache_file_path: str) -> None:
        """
        :param cache_file_path: the path of the file in which to persist the cache
        """
        self._cache_file_path = cache_file_path
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, assembly_path: str) -> list[AssemblySymbol] | None:
        """
        :param assembly_path: the path of the assembly whose symbols are requested
        :return: the cached symbols, or None if there is no valid entry for the assembly's
            current content
        """
        entry = self._entries.get(assembly_path)
        if entry is None:
            return None
        if entry.fingerprint != _AssemblyFingerprint.of(assembly_path):
            return None
        return entry.symbols

    def put(self, assembly_path: str, symbols: list[AssemblySymbol]) -> None:
        """
        :param assembly_path: the path of the assembly the symbols were read from
        :param symbols: the symbols that were read
        """
        fingerprint = _AssemblyFingerprint.of(assembly_path)
        if fingerprint is None:
            return
        self._entries[assembly_path] = _CacheEntry(fingerprint=fingerprint, symbols=symbols)

    def load(self) -> None:
        """
        Reads the persisted entries, treating an absent, unreadable or outdated file as an empty
        cache: the cache is an optimisation, so a failure to read it must only cost time.
        """
        try:
            with gzip.open(self._cache_file_path, "rb") as f:
                payload = pickle.load(f)
        except FileNotFoundError:
            return
        except Exception:
            log.warning(f"Discarding unreadable assembly symbol cache '{self._cache_file_path}'", exc_info=True)
            return

        if not isinstance(payload, dict) or payload.get("version") != self._FORMAT_VERSION:
            log.info("Discarding assembly symbol cache written in an incompatible format")
            return
        self._entries = payload["entries"]

    def save(self) -> None:
        """
        Writes the entries, logging (rather than raising) a failure, since being unable to persist
        the cache must not fail the search that populated it.
        """
        try:
            os.makedirs(os.path.dirname(self._cache_file_path) or ".", exist_ok=True)
            payload = {"version": self._FORMAT_VERSION, "entries": self._entries}
            # compression level 1: it shrinks the payload ~5x at negligible cost
            with gzip.open(self._cache_file_path, "wb", compresslevel=1) as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            log.warning(f"Failed to persist assembly symbol cache '{self._cache_file_path}'", exc_info=True)
