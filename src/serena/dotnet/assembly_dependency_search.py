from typing import TYPE_CHECKING, Any, cast

from serena.dependency_search import DependencySymbolSearch
from serena.dotnet.assembly_file_proxy import AssemblyExternalPath
from serena.dotnet.assembly_reference_resolver import AssemblyReferenceResolver
from serena.dotnet.assembly_symbol import AssemblySymbol
from serena.dotnet.assembly_symbol_index import AssemblySymbolIndex, DnFileMetadataReader
from serena.symbol import LanguageServerSymbol
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import UnifiedSymbolInformation

if TYPE_CHECKING:
    from serena.project import Project


class AssemblyDependencySearch(DependencySymbolSearch):
    """
    Searches the .NET assemblies referenced by a project for symbols that are not available in
    source form (and are therefore invisible to the language server).
    """

    def supports(self, language_server_id: LanguageServerId) -> bool:
        return language_server_id in (LanguageServerId.CSHARP, LanguageServerId.CSHARP_OMNISHARP)

    def find(self, project: "Project", name_path_pattern: str, substring_matching: bool) -> list[LanguageServerSymbol]:
        assembly_paths = AssemblyReferenceResolver(project.project_root).resolve()
        if not assembly_paths:
            return []
        index = AssemblySymbolIndex(assembly_paths, DnFileMetadataReader())
        return [self._to_language_server_symbol(s) for s in index.find(name_path_pattern, substring_matching=substring_matching)]

    @staticmethod
    def _to_language_server_symbol(symbol: AssemblySymbol) -> LanguageServerSymbol:
        """
        :param symbol: the symbol read from assembly metadata
        :return: the symbol in the representation used throughout Serena, located by an encoded
            external path; it has no line/column, because metadata records declarations rather
            than source positions (a position only exists once the type has been decompiled)
        """
        type_name_path = symbol.declaring_type_name_path or symbol.name
        external_path = AssemblyExternalPath(
            assembly_path=symbol.assembly_path,
            type_name_path=type_name_path,
            decompiled_file_path="",
        )
        symbol_info: dict[str, Any] = {
            "name": symbol.name,
            "kind": symbol.kind.to_lsp_symbol_kind(),
            "children": [],
            "location": {"relativePath": external_path.to_token()},
        }
        if symbol.overload_idx is not None:
            symbol_info["overload_idx"] = symbol.overload_idx
        return LanguageServerSymbol(cast(UnifiedSymbolInformation, symbol_info))


DEPENDENCY_SEARCHES = (AssemblyDependencySearch(),)
"""
The dependency searches which this language provides (read by `DependencySearchRegistry`).
"""
