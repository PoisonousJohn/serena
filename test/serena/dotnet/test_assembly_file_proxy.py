from pathlib import Path

from serena.dotnet.assembly_file_proxy import AssemblyExternalPath, AssemblyFileProxy
from serena.util.file_proxy import FileProxy


def make_external_path(decompiled_file_path: str = "/tmp/MetadataAsSource/abc/JsonConvert.cs") -> AssemblyExternalPath:
    return AssemblyExternalPath(
        assembly_path="/pkg/Newtonsoft.Json.dll",
        type_name_path="JsonConvert",
        decompiled_file_path=decompiled_file_path,
    )


class TestExternalPathToken:
    def test_token_is_recognised_as_an_external_path(self):
        """Recognition goes through the registry, which the dotnet package populates on import."""
        token = make_external_path().to_token()

        assert FileProxy.is_external_path(token)
        assert AssemblyFileProxy.matches(token)

    def test_ordinary_project_path_is_not_an_external_path(self):
        assert not FileProxy.is_external_path("src/serena/agent.py")
        assert not AssemblyFileProxy.matches("src/serena/agent.py")

    def test_jetbrains_token_is_not_claimed_by_the_assembly_proxy(self):
        assert not AssemblyFileProxy.matches("<ext:FileUtil.class|472e0a13>")

    def test_token_round_trips_through_parsing(self):
        original = make_external_path()

        restored = AssemblyExternalPath.from_token(original.to_token())

        assert restored.decompiled_file_path == original.decompiled_file_path
        assert restored.type_name_path == original.type_name_path
        assert restored.assembly_path == original.assembly_path


class TestFileProxyContract:
    def test_glob_filtering_is_not_supported(self):
        assert AssemblyFileProxy(make_external_path()).is_glob_supported() is False

    def test_relative_path_is_the_token(self):
        external_path = make_external_path()

        assert AssemblyFileProxy(external_path).get_relative_path() == external_path.to_token()

    def test_contents_are_read_from_the_decompiled_file(self, tmp_path: Path):
        decompiled = tmp_path / "JsonConvert.cs"
        decompiled.write_text("public static class JsonConvert { }", encoding="utf-8")

        proxy = AssemblyFileProxy(make_external_path(str(decompiled)))

        assert "JsonConvert" in proxy.get_contents()
