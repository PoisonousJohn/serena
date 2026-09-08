from pathlib import Path

from serena.dotnet.assembly_symbol import AssemblySymbol, AssemblySymbolKind
from serena.dotnet.assembly_symbol_provider import AssemblySymbolProvider

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <Reference Include="Lib">
      <HintPath>libs/Lib.dll</HintPath>
    </Reference>
  </ItemGroup>
</Project>
"""


class CountingReader:
    """Records how often each assembly is actually read, so caching is observable."""

    def __init__(self) -> None:
        self.read_paths: list[str] = []

    def read_symbols(self, assembly_path: str) -> list[AssemblySymbol]:
        self.read_paths.append(assembly_path)
        return [
            AssemblySymbol(
                name="Widget",
                kind=AssemblySymbolKind.TYPE,
                namespace="Lib",
                declaring_type_name_path=None,
                assembly_path=assembly_path,
            )
        ]


def make_project(root: Path) -> Path:
    (root / "libs").mkdir()
    (root / "libs" / "Lib.dll").write_bytes(b"MZ")
    (root / "App.csproj").write_text(CSPROJ, encoding="utf-8")
    return root


class TestFind:
    def test_symbol_of_a_referenced_assembly_is_found(self, tmp_path: Path):
        root = make_project(tmp_path)
        provider = AssemblySymbolProvider(str(root), str(tmp_path / "cache.pickle.gz"), CountingReader())

        assert [s.name for s in provider.find("Widget")] == ["Widget"]

    def test_unknown_symbol_yields_nothing(self, tmp_path: Path):
        root = make_project(tmp_path)
        provider = AssemblySymbolProvider(str(root), str(tmp_path / "cache.pickle.gz"), CountingReader())

        assert provider.find("DoesNotExist") == []

    def test_project_without_references_yields_nothing(self, tmp_path: Path):
        (tmp_path / "Bare.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk" />', encoding="utf-8")
        provider = AssemblySymbolProvider(str(tmp_path), str(tmp_path / "cache.pickle.gz"), CountingReader())

        assert provider.find("Widget") == []


class TestReadingIsDoneOnce:
    def test_repeated_searches_read_each_assembly_once(self, tmp_path: Path):
        root = make_project(tmp_path)
        reader = CountingReader()
        provider = AssemblySymbolProvider(str(root), str(tmp_path / "cache.pickle.gz"), reader)

        provider.find("Widget")
        provider.find("Widget")

        assert len(reader.read_paths) == 1

    def test_a_new_provider_reads_nothing_when_the_cache_is_warm(self, tmp_path: Path):
        """This is the behaviour that turns a 68s first search into a fast one in later sessions."""
        root = make_project(tmp_path)
        cache_file = str(tmp_path / "cache.pickle.gz")
        AssemblySymbolProvider(str(root), cache_file, CountingReader()).warm_up()

        second_reader = CountingReader()
        second_provider = AssemblySymbolProvider(str(root), cache_file, second_reader)

        assert [s.name for s in second_provider.find("Widget")] == ["Widget"]
        assert second_reader.read_paths == []

    def test_a_rebuilt_assembly_is_read_again(self, tmp_path: Path):
        root = make_project(tmp_path)
        cache_file = str(tmp_path / "cache.pickle.gz")
        AssemblySymbolProvider(str(root), cache_file, CountingReader()).warm_up()

        (root / "libs" / "Lib.dll").write_bytes(b"MZ-rebuilt-and-longer")

        reader = CountingReader()
        AssemblySymbolProvider(str(root), cache_file, reader).find("Widget")

        assert len(reader.read_paths) == 1

    def test_warm_up_is_idempotent(self, tmp_path: Path):
        root = make_project(tmp_path)
        reader = CountingReader()
        provider = AssemblySymbolProvider(str(root), str(tmp_path / "cache.pickle.gz"), reader)

        provider.warm_up()
        provider.warm_up()

        assert len(reader.read_paths) == 1
