from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from serena.util.external_path import ExternalFileProxy

if TYPE_CHECKING:
    from serena.project import Project

ASSEMBLY_EXTERNAL_PATH_PREFIX = "<ext:asm:"
"""
Prefix of the encoded relative paths of symbols defined in .NET assemblies rather than in project
sources. The `<ext:` stem is shared with the JetBrains backend's external paths, so that external
locations look alike to consumers regardless of the backend that produced them.
"""

_TOKEN_FIELD_SEP = "|"


@dataclass(frozen=True)
class AssemblyExternalPath:
    """
    The encoded location of a type defined in a .NET assembly.

    Holds the path of the decompiled source file in addition to the token, because navigation
    features need a real file and position, while Serena's tool interface needs the token.
    """

    assembly_path: str
    """the path of the assembly declaring the type"""
    type_name_path: str
    """the name path of the type within the assembly"""
    decompiled_file_path: str
    """the path of the decompiled source file; empty until the type has been decompiled"""

    @staticmethod
    def is_assembly_token(relative_path: str) -> bool:
        """
        :param relative_path: the relative path to inspect
        :return: whether it is an encoded assembly path
        """
        return relative_path.startswith(ASSEMBLY_EXTERNAL_PATH_PREFIX)

    def to_token(self) -> str:
        """:return: the encoded relative path representing this location."""
        fields = _TOKEN_FIELD_SEP.join((self.type_name_path, self.assembly_path, self.decompiled_file_path))
        return f"{ASSEMBLY_EXTERNAL_PATH_PREFIX}{fields}>"

    @classmethod
    def from_token(cls, token: str) -> "AssemblyExternalPath":
        """
        :param token: an encoded relative path previously produced by :meth:`to_token`
        :return: the decoded location
        """
        if not cls.is_assembly_token(token):
            raise ValueError(f"Not an assembly external path: {token}")
        payload = token[len(ASSEMBLY_EXTERNAL_PATH_PREFIX) : -1]
        type_name_path, assembly_path, decompiled_file_path = payload.split(_TOKEN_FIELD_SEP, 2)
        return cls(assembly_path=assembly_path, type_name_path=type_name_path, decompiled_file_path=decompiled_file_path)


class AssemblyFileProxy(ExternalFileProxy):
    """
    Provides the contents of a type defined in a .NET assembly by reading the decompiled source
    file that the language server generated for it.
    """

    def __init__(self, external_path: AssemblyExternalPath, encoding: str = "utf-8") -> None:
        """
        :param external_path: the location of the type
        :param encoding: the encoding of the decompiled source file
        """
        self._external_path = external_path
        self._encoding = encoding

    @classmethod
    def matches(cls, relative_path: str) -> bool:
        return AssemblyExternalPath.is_assembly_token(relative_path)

    @classmethod
    def from_relative_path(cls, relative_path: str, project: "Project") -> Self:
        return cls(AssemblyExternalPath.from_token(relative_path), encoding=project.project_config.encoding)

    def get_contents(self) -> str:
        with open(self._external_path.decompiled_file_path, encoding=self._encoding) as f:
            return f.read()

    def get_relative_path(self) -> str:
        return self._external_path.to_token()

    def is_glob_supported(self) -> bool:
        return False


EXTERNAL_FILE_PROXY_TYPES = (AssemblyFileProxy,)
"""
The external file proxy types which this backend provides (read by `ExternalFileProxyRegistry`).
"""
