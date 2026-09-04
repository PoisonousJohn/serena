from typing import TYPE_CHECKING, Self

from serena.util.external_path import ExternalFileProxy, ExternalFileProxyRegistry
from serena.util.file_proxy import FileProxy

if TYPE_CHECKING:
    from serena.project import Project


class StubExternalFileProxy(ExternalFileProxy):
    @classmethod
    def matches(cls, relative_path: str) -> bool:
        return relative_path.startswith("<stub:")

    @classmethod
    def from_relative_path(cls, relative_path: str, project: "Project") -> Self:
        return cls()

    def get_contents(self) -> str:
        return "stub contents"

    def get_relative_path(self) -> str:
        return "<stub:x>"

    def is_glob_supported(self) -> bool:
        return False


class TestRegistry:
    def test_registered_type_is_found_for_its_paths(self):
        registry = ExternalFileProxyRegistry()
        registry.register(StubExternalFileProxy)

        assert registry.find("<stub:x>") is StubExternalFileProxy

    def test_ordinary_project_path_matches_no_type(self):
        registry = ExternalFileProxyRegistry()
        registry.register(StubExternalFileProxy)

        assert registry.find("src/serena/agent.py") is None

    def test_unregistered_prefix_matches_no_type(self):
        assert ExternalFileProxyRegistry().find("<stub:x>") is None


class TestBackendSelfRegistration:
    """
    The registry must find the backends' proxy types without depending on the
    import order of unrelated modules.
    """

    def test_jetbrains_type_is_available_in_a_fresh_registry(self):
        proxy_type = ExternalFileProxyRegistry().find("<ext:FileUtil.class|472e0a13>")

        assert proxy_type is not None
        assert proxy_type.__name__ == "JetBrainsFileProxy"

    def test_project_path_matches_no_backend(self):
        assert ExternalFileProxyRegistry().find("src/serena/agent.py") is None


class TestFileProxyUsesRegistry:
    def test_jetbrains_paths_are_still_recognised_as_external(self):
        """The JetBrains proxy type must register itself, keeping existing behaviour."""
        assert FileProxy.is_external_path("<ext:FileUtil.class|472e0a13>")

    def test_project_paths_are_not_external(self):
        assert not FileProxy.is_external_path("src/serena/agent.py")

    def test_registry_is_consulted_by_file_proxy(self, monkeypatch):
        """`FileProxy` must answer from the registry, not from any built-in knowledge."""
        registry = ExternalFileProxyRegistry()
        registry.register(StubExternalFileProxy)
        monkeypatch.setattr("serena.util.external_path.EXTERNAL_FILE_PROXY_REGISTRY", registry)

        assert FileProxy.is_external_path("<stub:x>")
        assert not FileProxy.is_external_path("src/serena/agent.py")

    def test_file_proxy_module_names_no_specific_backend(self):
        """Guards the inversion: the general abstraction must not import a backend."""
        from pathlib import Path

        import serena.util.file_proxy as module

        source = Path(module.__file__).read_text(encoding="utf-8")

        assert "jetbrains" not in source.lower()
        assert "dotnet" not in source.lower() and "assembly" not in source.lower()
