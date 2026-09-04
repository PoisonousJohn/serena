from serena.dotnet.assembly_symbol import AssemblySymbol, AssemblySymbolKind
from solidlsp.ls_types import SymbolKind


def make_type(name: str = "JsonConvert", namespace: str | None = "Newtonsoft.Json") -> AssemblySymbol:
    return AssemblySymbol(
        name=name,
        kind=AssemblySymbolKind.TYPE,
        namespace=namespace,
        declaring_type_name_path=None,
        assembly_path="/pkg/Newtonsoft.Json.dll",
    )


def make_method(name: str = "SerializeObject", overload_idx: int | None = None) -> AssemblySymbol:
    return AssemblySymbol(
        name=name,
        kind=AssemblySymbolKind.METHOD,
        namespace="Newtonsoft.Json",
        declaring_type_name_path="JsonConvert",
        assembly_path="/pkg/Newtonsoft.Json.dll",
        overload_idx=overload_idx,
    )


class TestNamePath:
    def test_type_name_path_is_the_type_name(self):
        assert make_type().get_name_path() == "JsonConvert"

    def test_member_name_path_is_nested_under_its_type(self):
        assert make_method().get_name_path() == "JsonConvert/SerializeObject"

    def test_reversed_components_are_leaf_first(self):
        components = list(make_method().iter_name_path_components_reversed())
        assert [c.name for c in components] == ["SerializeObject", "JsonConvert"]

    def test_overload_index_is_carried_on_the_leaf_component(self):
        components = list(make_method(overload_idx=1).iter_name_path_components_reversed())
        assert components[0].overload_idx == 1
        assert components[1].overload_idx is None


class TestKindMapping:
    def test_type_maps_to_class(self):
        assert AssemblySymbolKind.TYPE.to_lsp_symbol_kind() == SymbolKind.Class

    def test_method_maps_to_method(self):
        assert AssemblySymbolKind.METHOD.to_lsp_symbol_kind() == SymbolKind.Method

    def test_field_maps_to_field(self):
        assert AssemblySymbolKind.FIELD.to_lsp_symbol_kind() == SymbolKind.Field
