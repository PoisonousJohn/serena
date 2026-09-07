import logging
import os
import time
from collections import Counter
from collections.abc import Iterator
from typing import Any, Protocol

import dnfile

from serena.dotnet.assembly_symbol import AssemblySymbol, AssemblySymbolKind
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

    Symbols are read lazily on first search and kept in memory afterwards, so the first search
    bears the entire reading cost and subsequent ones are served from memory.
    """

    _SLOW_ASSEMBLY_LOG_THRESHOLD_SECS = 0.5
    """
    Duration from which reading a single assembly is reported at INFO rather than DEBUG level,
    so that the few large assemblies dominating a slow search are identifiable without having to
    enable debug logging for the hundreds of small ones.
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
        symbols = self._get_symbols()
        started_at = time.monotonic()
        matches = [s for s in symbols if matcher.matches_reversed_components(s.iter_name_path_components_reversed())]
        log.info(
            "Matched '%s' against %d assembly symbols in %.2fs: %d hits",
            name_path_pattern,
            len(symbols),
            time.monotonic() - started_at,
            len(matches),
        )
        return matches

    def _get_symbols(self) -> list[AssemblySymbol]:
        """
        :return: the symbols of all assemblies, reading them on first access
        """
        if self._symbols is None:
            self._symbols = self._read_all_symbols()
        return self._symbols

    def _read_all_symbols(self) -> list[AssemblySymbol]:
        """
        Reads the symbols of all assemblies, logging the progress: reading is the expensive part
        of a first search (seconds per hundred assemblies), so the log has to make both the total
        cost and its distribution across assemblies visible.

        :return: the symbols declared in all assemblies that could be read
        """
        log.info("Reading symbols from %d assemblies", len(self._assembly_paths))
        started_at = time.monotonic()
        symbols: list[AssemblySymbol] = []
        num_failed = 0

        for i, assembly_path in enumerate(self._assembly_paths, start=1):
            assembly_started_at = time.monotonic()
            try:
                assembly_symbols = self._reader.read_symbols(assembly_path)
            except Exception as e:
                # an unreadable assembly must not prevent searching the others
                num_failed += 1
                log.warning("Failed to read symbols from assembly %s: %s", assembly_path, e)
                continue
            symbols.extend(assembly_symbols)
            duration = time.monotonic() - assembly_started_at
            if duration >= self._SLOW_ASSEMBLY_LOG_THRESHOLD_SECS:
                log.info(
                    "  [%d/%d] %s: %d symbols in %.2fs",
                    i,
                    len(self._assembly_paths),
                    os.path.basename(assembly_path),
                    len(assembly_symbols),
                    duration,
                )
            else:
                log.debug(
                    "  [%d/%d] %s: %d symbols in %.2fs",
                    i,
                    len(self._assembly_paths),
                    os.path.basename(assembly_path),
                    len(assembly_symbols),
                    duration,
                )

        log.info(
            "Read %d symbols from %d/%d assemblies in %.2fs",
            len(symbols),
            len(self._assembly_paths) - num_failed,
            len(self._assembly_paths),
            time.monotonic() - started_at,
        )
        return symbols


class DnFileMetadataReader:
    """
    Reads symbols from a .NET assembly's CLI metadata tables using `dnfile`.

    Reading is pure Python: no .NET runtime or SDK is required.
    """

    _MODULE_TYPE_NAME = "<Module>"
    """
    Name of the synthetic type holding an assembly's global members; never a user-facing symbol.
    See ECMA-335 6th ed. II.22.37 (TypeDef), which requires this row to be present.
    """
    _VISIBLE_METHOD_FLAGS = ("mdPublic", "mdFamily")
    """
    The `ClrMethodAttr` flags denoting a method that is part of a type's usable surface:
    `Public` and `Family` ("protected", i.e. accessible to derived types).
    See ECMA-335 6th ed. II.23.1.10 and
    https://learn.microsoft.com/en-us/dotnet/api/system.reflection.methodattributes
    """
    _VISIBLE_FIELD_FLAGS = ("fdPublic", "fdFamily")
    """
    The `ClrFieldAttr` counterparts of :attr:`_VISIBLE_METHOD_FLAGS`. `dnfile` models the two
    attribute enums as separate flag objects using distinct member prefixes (`md` vs `fd`), so
    the accessibility of a method and of a field must be queried by different names.
    See ECMA-335 6th ed. II.23.1.5 and
    https://learn.microsoft.com/en-us/dotnet/api/system.reflection.fieldattributes
    """

    def read_symbols(self, assembly_path: str) -> list[AssemblySymbol]:
        """
        :param assembly_path: the absolute path of the assembly to read
        :return: the public types and members declared in the assembly
        """
        pe = dnfile.dnPE(assembly_path)
        type_defs = getattr(pe.net.mdtables, "TypeDef", None) if pe.net is not None else None
        if type_defs is None:
            return []

        symbols: list[AssemblySymbol] = []
        for type_def in type_defs.rows:
            type_name = str(type_def.TypeName)
            if not self._is_reportable_name(type_name):
                continue
            namespace = str(type_def.TypeNamespace) or None
            symbols.append(
                AssemblySymbol(
                    name=type_name,
                    kind=AssemblySymbolKind.TYPE,
                    namespace=namespace,
                    declaring_type_name_path=None,
                    assembly_path=assembly_path,
                )
            )
            symbols.extend(self._read_members(type_def, type_name, namespace, assembly_path))
        return symbols

    def _read_members(self, type_def: Any, type_name: str, namespace: str | None, assembly_path: str) -> list[AssemblySymbol]:
        """
        :param type_def: the TypeDef row declaring the members
        :param type_name: the name of the declaring type
        :param namespace: the namespace of the declaring type
        :param assembly_path: the path of the assembly being read
        :return: the publicly visible members declared by the given type
        """
        members: list[AssemblySymbol] = []

        # collect the reportable methods first, because an overload index is assigned only to
        # names that occur more than once (matching `SolidLanguageServer`'s convention) and that
        # is not known until all of the type's methods have been seen
        method_names = [
            str(row.Name)
            for row in self._iter_rows(type_def, "MethodList")
            if self._is_reportable_name(str(row.Name)) and self._is_visible(row.Flags, self._VISIBLE_METHOD_FLAGS)
        ]
        name_counts = Counter(method_names)
        emitted_counts: Counter[str] = Counter()
        for name in method_names:
            overload_idx = None
            if name_counts[name] > 1:
                overload_idx = emitted_counts[name]
                emitted_counts[name] += 1
            members.append(
                AssemblySymbol(
                    name=name,
                    kind=AssemblySymbolKind.METHOD,
                    namespace=namespace,
                    declaring_type_name_path=type_name,
                    assembly_path=assembly_path,
                    overload_idx=overload_idx,
                )
            )

        for field_row in self._iter_rows(type_def, "FieldList"):
            name = str(field_row.Name)
            if not self._is_reportable_name(name) or not self._is_visible(field_row.Flags, self._VISIBLE_FIELD_FLAGS):
                continue
            members.append(
                AssemblySymbol(
                    name=name,
                    kind=AssemblySymbolKind.FIELD,
                    namespace=namespace,
                    declaring_type_name_path=type_name,
                    assembly_path=assembly_path,
                )
            )
        return members

    @staticmethod
    def _iter_rows(type_def: Any, list_attribute_name: str) -> Iterator[Any]:
        """
        :param type_def: the TypeDef row
        :param list_attribute_name: the name of the row-list attribute to traverse
        :return: an iterator over the referenced rows that could be resolved
        """
        for row_ref in getattr(type_def, list_attribute_name, None) or []:
            row = getattr(row_ref, "row", None)
            if row is not None:
                yield row

    @staticmethod
    def _is_visible(flags: Any, visible_flag_names: tuple[str, ...]) -> bool:
        """
        :param flags: the member's flags object
        :param visible_flag_names: the names of the flags denoting a visible member
        :return: whether the member is part of the type's usable surface
        """
        return any(getattr(flags, flag_name, False) for flag_name in visible_flag_names)

    def _is_reportable_name(self, name: str) -> bool:
        """
        :param name: the metadata name of a type or member
        :return: whether the name denotes a symbol that should be reported (i.e. not
            compiler-generated and not the synthetic module type)
        """
        return bool(name) and name != self._MODULE_TYPE_NAME and "<" not in name and ">" not in name
