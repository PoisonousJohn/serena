from typing import TYPE_CHECKING, Self

from serena.jetbrains import jetbrains_types as jb
from serena.util.external_path import ExternalFileProxy

if TYPE_CHECKING:
    from serena.project import Project


class JetBrainsFileProxy(ExternalFileProxy):
    """
    Retrieves the contents of a file from the JetBrains plugin via the plugin client, given its relative path,
    which may be an external path (e.g., "<ext:FileUtil.class|472e0a13>")
    """

    def __init__(self, relative_path: str, project: "Project"):
        self._relative_path = relative_path
        self._project = project

    @classmethod
    def matches(cls, relative_path: str) -> bool:
        return jb.is_external_path(relative_path)

    @classmethod
    def from_relative_path(cls, relative_path: str, project: "Project") -> Self:
        return cls(relative_path, project)

    def get_contents(self) -> str:
        from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient

        client = JetBrainsPluginClient.from_project(self._project)
        return client.read_file(self._relative_path)

    def get_relative_path(self) -> str:
        return self._relative_path

    def is_glob_supported(self):
        return False


EXTERNAL_FILE_PROXY_TYPES = (JetBrainsFileProxy,)
"""
The external file proxy types which this backend provides (read by `ExternalFileProxyRegistry`).
"""
