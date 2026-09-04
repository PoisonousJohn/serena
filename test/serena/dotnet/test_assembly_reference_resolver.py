from pathlib import Path

import pytest

from serena.dotnet.assembly_reference_resolver import AssemblyReferenceResolver

CSPROJ_TEMPLATE = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
{references}
  </ItemGroup>
</Project>
"""


def write_csproj(directory: Path, name: str, hint_paths: list[str]) -> Path:
    references = "\n".join(
        f'    <Reference Include="{Path(p).stem}">\n      <HintPath>{p}</HintPath>\n    </Reference>' for p in hint_paths
    )
    path = directory / name
    path.write_text(CSPROJ_TEMPLATE.format(references=references), encoding="utf-8")
    return path


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "libs").mkdir()
    return tmp_path


class TestResolve:
    def test_finds_assembly_from_hint_path(self, project_root: Path):
        (project_root / "libs" / "Newtonsoft.Json.dll").write_bytes(b"MZ")
        write_csproj(project_root, "App.csproj", ["libs/Newtonsoft.Json.dll"])

        resolved = AssemblyReferenceResolver(str(project_root)).resolve()

        assert resolved == [str(project_root / "libs" / "Newtonsoft.Json.dll")]

    def test_ignores_assembly_that_has_sources_alongside_it(self, project_root: Path):
        """Assemblies shipped with sources are already covered by the language server."""
        (project_root / "libs" / "WithSources.dll").write_bytes(b"MZ")
        (project_root / "libs" / "Thing.cs").write_text("class Thing {}", encoding="utf-8")
        write_csproj(project_root, "App.csproj", ["libs/WithSources.dll"])

        assert AssemblyReferenceResolver(str(project_root)).resolve() == []

    def test_deduplicates_assembly_referenced_from_several_projects(self, project_root: Path):
        (project_root / "libs" / "Shared.dll").write_bytes(b"MZ")
        write_csproj(project_root, "A.csproj", ["libs/Shared.dll"])
        write_csproj(project_root, "B.csproj", ["libs/Shared.dll"])

        assert AssemblyReferenceResolver(str(project_root)).resolve() == [str(project_root / "libs" / "Shared.dll")]

    def test_returns_empty_list_when_no_references_exist(self, project_root: Path):
        write_csproj(project_root, "App.csproj", [])

        assert AssemblyReferenceResolver(str(project_root)).resolve() == []

    def test_skips_missing_hint_path_but_keeps_the_others(self, project_root: Path):
        """A broken reference must not prevent the remaining ones from resolving."""
        (project_root / "libs" / "Present.dll").write_bytes(b"MZ")
        write_csproj(project_root, "App.csproj", ["libs/Absent.dll", "libs/Present.dll"])

        assert AssemblyReferenceResolver(str(project_root)).resolve() == [str(project_root / "libs" / "Present.dll")]

    def test_malformed_csproj_does_not_break_resolution_of_others(self, project_root: Path):
        (project_root / "libs" / "Good.dll").write_bytes(b"MZ")
        (project_root / "Broken.csproj").write_text("<Project><unclosed>", encoding="utf-8")
        write_csproj(project_root, "Good.csproj", ["libs/Good.dll"])

        assert AssemblyReferenceResolver(str(project_root)).resolve() == [str(project_root / "libs" / "Good.dll")]
