"""
End-to-end test of finding usages of a symbol declared in a source-less assembly.

The library assembly is compiled on the fly and its sources are then discarded, so the consumer
project references a genuinely source-less DLL, and no binary fixture is committed. The shared
fixture `test/resources/repos/csharp/test_repo` is deliberately not used: it does not compile.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.csharp

_LIBRARY_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <AssemblyName>RenderLib</AssemblyName>
    <Nullable>disable</Nullable>
  </PropertyGroup>
</Project>
"""

_LIBRARY_SOURCE = """namespace RenderLib
{
    public static class GraphicsApi
    {
        public static void BeginDraw(int mode) { }
        public static void EndDraw() { }
    }
}
"""

_CONSUMER_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>disable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="RenderLib">
      <HintPath>libs/RenderLib.dll</HintPath>
    </Reference>
  </ItemGroup>
</Project>
"""

_CONSUMER_USES = """using RenderLib;

namespace App
{
    public class Renderer
    {
        public void DrawFrame()
        {
            GraphicsApi.BeginDraw(1);
            GraphicsApi.EndDraw();
        }

        public void DrawOverlay()
        {
            GraphicsApi.BeginDraw(2);
            // GraphicsApi.BeginDraw(999);  <- commented out: must NOT be reported
        }
    }
}
"""

_CONSUMER_UNRELATED = """namespace App
{
    public class Notes
    {
        // "GraphicsApi.BeginDraw" appears here only inside a string and a comment
        public string Text = "GraphicsApi.BeginDraw(1)";
    }
}
"""


def _build(project_dir: Path, project_file: str) -> None:
    try:
        subprocess.run(["dotnet", "build", project_file, "-c", "Debug"], cwd=project_dir, check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"dotnet build unavailable: {e}")


@pytest.fixture(scope="module")
def consumer_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    :return: the root of a project that references a compiled, source-less assembly and uses it
    """
    library_dir = tmp_path_factory.mktemp("render_lib")
    (library_dir / "RenderLib.csproj").write_text(_LIBRARY_PROJECT, encoding="utf-8")
    (library_dir / "GraphicsApi.cs").write_text(_LIBRARY_SOURCE, encoding="utf-8")
    _build(library_dir, "RenderLib.csproj")
    built = sorted(library_dir.glob("bin/Debug/*/RenderLib.dll"))
    if not built:
        pytest.skip("library assembly not found")

    consumer = tmp_path_factory.mktemp("consumer")
    (consumer / "Consumer.csproj").write_text(_CONSUMER_PROJECT, encoding="utf-8")
    (consumer / "libs").mkdir()
    shutil.copy(built[0], consumer / "libs" / "RenderLib.dll")
    (consumer / "Renderer.cs").write_text(_CONSUMER_USES, encoding="utf-8")
    (consumer / "Notes.cs").write_text(_CONSUMER_UNRELATED, encoding="utf-8")
    return consumer


@pytest.fixture
def search(consumer_project: Path):
    from serena.config.serena_config import SerenaConfig
    from serena.dotnet.dll_usage_search import DllUsageSearch
    from serena.project import Project

    project = Project.load(str(consumer_project), SerenaConfig(gui_log_window=False, web_dashboard=False))
    project.create_language_server_manager()
    try:
        yield DllUsageSearch(project)
    finally:
        project.shutdown(timeout=5)


class TestFindUsages:
    def test_usages_of_a_dll_method_are_found(self, search):
        result = search.find_usages("GraphicsApi/BeginDraw")

        assert result is not None
        referencing_files = {r.symbol.location.relative_path for r in result.references}
        assert "Renderer.cs" in referencing_files

    def test_the_declaring_assembly_is_reported(self, search):
        result = search.find_usages("GraphicsApi/BeginDraw")

        assert result is not None
        assert result.assembly_path.endswith("RenderLib.dll")

    def test_commented_out_and_quoted_occurrences_are_not_reported(self, search):
        """The whole point of searching symbolically rather than textually."""
        result = search.find_usages("GraphicsApi/BeginDraw")

        assert result is not None
        assert "Notes.cs" not in {r.symbol.location.relative_path for r in result.references}
        reported_lines = {(r.symbol.location.relative_path, r.line) for r in result.references}
        # the commented-out call sits on the line after the DrawOverlay call
        assert not any(path == "Renderer.cs" and "999" in _line_text(search, path, line) for path, line in reported_lines)

    def test_symbol_absent_from_all_assemblies_yields_none(self, search):
        assert search.find_usages("NoSuchType/NoSuchMethod") is None

    def test_symbol_present_but_unused_reports_no_references(self, search):
        """A correct answer, not an error: the symbol exists but nothing in the project calls it."""
        result = search.find_usages("GraphicsApi/EndDraw")

        assert result is not None
        assert "Renderer.cs" in {r.symbol.location.relative_path for r in result.references}


def _line_text(search, relative_path: str, line: int) -> str:
    return (Path(search.project.project_root) / relative_path).read_text(encoding="utf-8").splitlines()[line]
