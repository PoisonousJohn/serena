from collections import defaultdict

from serena.tools.tools_base import Tool, ToolMarkerOptional, ToolMarkerSymbolicRead


class FindDllSymbolUsagesTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds usages of a symbol that is defined in a referenced .NET assembly without sources
    """

    def apply(self, name_path: str, max_answer_chars: int = -1) -> str:
        """
        Finds all places in the project that use a symbol which is defined in a referenced .NET
        assembly (a DLL shipped without sources), such as a Unity or NuGet library type or method.

        Use this instead of a text search when you need the usages of a library symbol: the result
        is resolved by the language server, so occurrences in comments, in string literals, and in
        similarly named but unrelated symbols are not reported.

        :param name_path: the name path of the symbol as declared in the assembly, e.g.
            "GL/Begin" for the method `Begin` of the type `GL`, or "GL" for the type itself.
        :param max_answer_chars: max result length; -1 for default
        :return: the declaring assembly and the project symbols using the given symbol
        """
        from serena.dotnet.dll_usage_search import DllUsageSearch

        usages = DllUsageSearch(self.project).find_usages(name_path)
        if usages is None:
            return self._to_json(
                {
                    "symbol": name_path,
                    "found": False,
                    "message": "No referenced assembly declares this symbol. Check the name path, "
                    "or use find_symbol if the symbol is defined in the project's own sources.",
                }
            )

        references_by_path: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for reference in usages.references:
            relative_path = reference.symbol.location.relative_path or "unknown"
            references_by_path[relative_path].append({"name_path": reference.symbol.get_name_path(), "line": reference.line})

        result = self._to_json(
            {
                "symbol": usages.symbol_name_path,
                "found": True,
                "assembly": usages.assembly_path,
                "num_usages": len(usages.references),
                "usages": dict(references_by_path),
            }
        )

        def create_short_result() -> str:
            """:return: the files and usage counts only, for the case where the full result is too long."""
            counts = {path: len(refs) for path, refs in references_by_path.items()}
            return f"Shortened result:\n{self._to_json({'symbol': usages.symbol_name_path, 'usages_per_file': counts})}"

        return self._limit_length(result, max_answer_chars, shortened_result_factories=[create_short_result])
