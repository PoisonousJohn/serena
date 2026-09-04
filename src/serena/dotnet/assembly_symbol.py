from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from serena.symbol import NAME_PATH_SEP, NamePathComponent
from solidlsp.ls_types import SymbolKind


class AssemblySymbolKind(Enum):
    """The kind of a symbol declared in assembly metadata."""

    TYPE = "type"
    METHOD = "method"
    FIELD = "field"

    def to_lsp_symbol_kind(self) -> SymbolKind:
        """:return: the LSP symbol kind corresponding to this kind."""
        match self:
            case AssemblySymbolKind.TYPE:
                return SymbolKind.Class
            case AssemblySymbolKind.METHOD:
                return SymbolKind.Method
            case AssemblySymbolKind.FIELD:
                return SymbolKind.Field


@dataclass(frozen=True)
class AssemblySymbol:
    """
    A symbol declared in the metadata of a .NET assembly.

    Unlike a language server symbol, it has no position: assembly metadata records declarations,
    not source locations. A position only exists once the type is decompiled.
    """

    name: str
    kind: AssemblySymbolKind
    namespace: str | None
    declaring_type_name_path: str | None
    """the name path of the declaring type, or None if this symbol is itself a type"""
    assembly_path: str
    overload_idx: int | None = None

    def get_name_path(self) -> str:
        """:return: the name path of the symbol within its assembly (e.g. "JsonConvert/SerializeObject")."""
        if self.declaring_type_name_path is None:
            return self.name
        return f"{self.declaring_type_name_path}{NAME_PATH_SEP}{self.name}"

    def iter_name_path_components_reversed(self) -> Iterator[NamePathComponent]:
        """:return: an iterator over the name path components, starting from this symbol and going up."""
        yield NamePathComponent(name=self.name, overload_idx=self.overload_idx)
        if self.declaring_type_name_path is not None:
            for component_name in reversed(self.declaring_type_name_path.split(NAME_PATH_SEP)):
                yield NamePathComponent(name=component_name)
