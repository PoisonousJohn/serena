from serena.dotnet.assembly_symbol import AssemblySymbol, AssemblySymbolKind
from serena.dotnet.assembly_symbol_index import AssemblySymbolIndex

ASSEMBLY = "/pkg/Newtonsoft.Json.dll"


class StubReader:
    """An in-memory stand-in for the PE reader, so search is testable without a DLL."""

    def __init__(self, symbols_by_assembly: dict[str, list[AssemblySymbol]]) -> None:
        self._symbols_by_assembly = symbols_by_assembly
        self.read_count = 0

    def read_symbols(self, assembly_path: str) -> list[AssemblySymbol]:
        self.read_count += 1
        return self._symbols_by_assembly.get(assembly_path, [])


def type_symbol(name: str) -> AssemblySymbol:
    return AssemblySymbol(
        name=name,
        kind=AssemblySymbolKind.TYPE,
        namespace="Newtonsoft.Json",
        declaring_type_name_path=None,
        assembly_path=ASSEMBLY,
    )


def method_symbol(name: str, declaring_type: str = "JsonConvert", overload_idx: int | None = None) -> AssemblySymbol:
    return AssemblySymbol(
        name=name,
        kind=AssemblySymbolKind.METHOD,
        namespace="Newtonsoft.Json",
        declaring_type_name_path=declaring_type,
        assembly_path=ASSEMBLY,
        overload_idx=overload_idx,
    )


def make_index(symbols: list[AssemblySymbol], reader: StubReader | None = None) -> AssemblySymbolIndex:
    reader = reader or StubReader({ASSEMBLY: symbols})
    return AssemblySymbolIndex([ASSEMBLY], reader)


class TestFind:
    def test_finds_type_by_simple_name(self):
        index = make_index([type_symbol("JsonConvert"), type_symbol("JsonReader")])

        assert [s.name for s in index.find("JsonConvert")] == ["JsonConvert"]

    def test_finds_member_by_qualified_name_path(self):
        index = make_index([type_symbol("JsonConvert"), method_symbol("SerializeObject")])

        assert [s.get_name_path() for s in index.find("JsonConvert/SerializeObject")] == ["JsonConvert/SerializeObject"]

    def test_unknown_name_yields_no_results(self):
        index = make_index([type_symbol("JsonConvert")])

        assert index.find("DoesNotExist") == []

    def test_substring_matching_matches_partial_leaf_name(self):
        index = make_index([method_symbol("SerializeObject"), method_symbol("DeserializeObject")])

        found = {s.name for s in index.find("Serialize", substring_matching=True)}

        assert found == {"SerializeObject"}

    def test_exact_matching_does_not_match_partial_name(self):
        index = make_index([method_symbol("SerializeObject")])

        assert index.find("Serialize") == []

    def test_overloads_are_distinguishable_by_index(self):
        index = make_index([method_symbol("SerializeObject", overload_idx=0), method_symbol("SerializeObject", overload_idx=1)])

        found = index.find("JsonConvert/SerializeObject[1]")

        assert [s.overload_idx for s in found] == [1]

    def test_first_overload_is_addressable_as_index_zero(self):
        """`NamePathMatcher` compares indices exactly, so the first overload must carry 0, not None."""
        index = make_index([method_symbol("SerializeObject", overload_idx=0), method_symbol("SerializeObject", overload_idx=1)])

        assert [s.overload_idx for s in index.find("JsonConvert/SerializeObject[0]")] == [0]

    def test_unique_method_name_carries_no_overload_index(self):
        """A name occurring once must stay unindexed, matching SolidLanguageServer's convention."""
        index = make_index([method_symbol("OnlyOnce")])

        assert [s.overload_idx for s in index.find("JsonConvert/OnlyOnce")] == [None]

    def test_absolute_pattern_requires_full_name_path(self):
        index = make_index([method_symbol("SerializeObject")])

        assert index.find("/SerializeObject") == []
        assert [s.name for s in index.find("/JsonConvert/SerializeObject")] == ["SerializeObject"]


class TestReading:
    def test_assemblies_are_read_only_once_across_searches(self):
        reader = StubReader({ASSEMBLY: [type_symbol("JsonConvert")]})
        index = make_index([], reader=reader)

        index.find("JsonConvert")
        index.find("JsonConvert")

        assert reader.read_count == 1

    def test_unreadable_assembly_does_not_break_the_search(self):
        class FailingReader:
            def read_symbols(self, assembly_path: str) -> list[AssemblySymbol]:
                raise OSError("not a PE file")

        index = AssemblySymbolIndex([ASSEMBLY], FailingReader())

        assert index.find("JsonConvert") == []
