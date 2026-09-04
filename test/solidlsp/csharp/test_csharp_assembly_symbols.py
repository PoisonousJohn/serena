"""
Tests reading symbols from a real .NET assembly.

The assembly is compiled on the fly from sources written to a temporary directory, rather than
taken from `test/resources/repos/csharp/test_repo`: that fixture intentionally does not compile
(`DiagnosticsSample.cs` contains the unresolved identifiers which the diagnostics tests assert
on). Compiling here also keeps the assembly out of the repository, as no binary fixtures are
committed.
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from serena.dotnet.assembly_dependency_search import AssemblyDependencySearch
from serena.dotnet.assembly_file_proxy import AssemblyFileProxy
from serena.dotnet.assembly_symbol import AssemblySymbolKind
from serena.dotnet.assembly_symbol_index import AssemblySymbolIndex, DnFileMetadataReader

if TYPE_CHECKING:
    from serena.project import Project

pytestmark = pytest.mark.csharp

_PROJECT_FILE = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <AssemblyName>AssemblySymbolFixture</AssemblyName>
    <Nullable>disable</Nullable>
  </PropertyGroup>
</Project>
"""

_SOURCES = {
    "Models/Person.cs": """namespace Fixture.Models
{
    public class Person
    {
        public string Name { get; set; }
        public Person(string name) { Name = name; }
        public string Describe() { return Name; }
        public string Describe(int times) { return Name + times; }
    }
}
""",
    "Services/ConsoleGreeter.cs": """namespace Fixture.Services
{
    public class ConsoleGreeter
    {
        public const string Salutation = "Hello";
        public string FormatGreeting(string name) { return Salutation + ", " + name; }
        private string Hidden() { return "hidden"; }
    }
}
""",
}


@pytest.fixture(scope="module")
def built_assembly(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    :return: the path of an assembly compiled from the fixture sources
    """
    project_dir = tmp_path_factory.mktemp("assembly_symbol_fixture")
    (project_dir / "Fixture.csproj").write_text(_PROJECT_FILE, encoding="utf-8")
    for relative_path, source in _SOURCES.items():
        source_path = project_dir / relative_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source, encoding="utf-8")

    try:
        subprocess.run(
            ["dotnet", "build", "Fixture.csproj", "-c", "Debug"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"dotnet build unavailable: {e}")

    assemblies = sorted(project_dir.glob("bin/Debug/*/AssemblySymbolFixture.dll"))
    if not assemblies:
        pytest.skip("built assembly not found")
    return assemblies[0]


@pytest.fixture
def index(built_assembly: Path) -> AssemblySymbolIndex:
    return AssemblySymbolIndex([str(built_assembly)], DnFileMetadataReader())


class TestReadRealAssembly:
    def test_declared_type_is_found(self, index: AssemblySymbolIndex):
        assert [s.name for s in index.find("Person")] == ["Person"]

    def test_namespace_is_recorded_on_the_symbol(self, index: AssemblySymbolIndex):
        person = index.find("Person")[0]

        assert person.namespace is not None and "Models" in person.namespace

    def test_public_method_of_a_type_is_found(self, index: AssemblySymbolIndex):
        found = index.find("ConsoleGreeter/FormatGreeting")

        assert [s.kind for s in found] == [AssemblySymbolKind.METHOD]

    def test_public_field_of_a_type_is_found(self, index: AssemblySymbolIndex):
        found = index.find("ConsoleGreeter/Salutation")

        assert [s.kind for s in found] == [AssemblySymbolKind.FIELD]

    def test_private_member_is_not_reported(self, index: AssemblySymbolIndex):
        assert index.find("ConsoleGreeter/Hidden") == []

    def test_compiler_generated_types_are_not_reported(self, index: AssemblySymbolIndex):
        assert index.find("<Module>") == []

    def test_overloads_are_addressable_by_index(self, index: AssemblySymbolIndex):
        assert [s.overload_idx for s in index.find("Person/Describe")] == [0, 1]
        assert [s.overload_idx for s in index.find("Person/Describe[1]")] == [1]


_CONSUMER_PROJECT_FILE = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>disable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="AssemblySymbolFixture">
      <HintPath>libs\\AssemblySymbolFixture.dll</HintPath>
    </Reference>
  </ItemGroup>
</Project>
"""


@pytest.fixture(scope="module")
def consumer_project_root(built_assembly: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    :return: the root of a project referencing the fixture assembly, with no sources for it
    """
    root = tmp_path_factory.mktemp("assembly_consumer")
    (root / "Consumer.csproj").write_text(_CONSUMER_PROJECT_FILE, encoding="utf-8")
    libs = root / "libs"
    libs.mkdir()
    (libs / "AssemblySymbolFixture.dll").write_bytes(built_assembly.read_bytes())
    (root / "Program.cs").write_text("public class Program { public static void Main() { } }", encoding="utf-8")
    return root


class TestDependencySearchEndToEnd:
    """
    The full dependency-search path: resolving the reference from the project file, reading the
    assembly's metadata, and reporting the symbols with encoded external paths.
    """

    def test_dependency_symbol_is_found(self, consumer_project_root: Path):
        search = AssemblyDependencySearch()
        project = SimpleNamespace(project_root=str(consumer_project_root))

        found = search.find(cast("Project", project), "ConsoleGreeter", substring_matching=False)

        assert [s.name for s in found] == ["ConsoleGreeter"]

    def test_dependency_symbol_is_located_by_an_external_path(self, consumer_project_root: Path):
        search = AssemblyDependencySearch()
        project = SimpleNamespace(project_root=str(consumer_project_root))

        symbol = search.find(cast("Project", project), "ConsoleGreeter", substring_matching=False)[0]

        assert symbol.relative_path is not None
        assert AssemblyFileProxy.matches(symbol.relative_path)
        assert not symbol.location.has_position_in_file()

    def test_symbol_of_the_consumer_project_is_not_reported(self, consumer_project_root: Path):
        """Only dependencies are searched; the project's own sources are the language server's job."""
        search = AssemblyDependencySearch()
        project = SimpleNamespace(project_root=str(consumer_project_root))

        assert search.find(cast("Project", project), "Program", substring_matching=False) == []

    def test_project_without_references_yields_nothing(self, tmp_path: Path):
        (tmp_path / "Bare.csproj").write_text(_PROJECT_FILE, encoding="utf-8")
        search = AssemblyDependencySearch()
        project = SimpleNamespace(project_root=str(tmp_path))

        assert search.find(cast("Project", project), "ConsoleGreeter", substring_matching=False) == []
