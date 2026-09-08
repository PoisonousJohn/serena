import importlib
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

from serena.util.file_proxy import FileProxy

if TYPE_CHECKING:
    from serena.project import Project

log = logging.getLogger(__name__)


class ExternalFileProxy(FileProxy, ABC):
    """
    A file proxy for content that does not reside in the project (e.g. a symbol from a library),
    addressed by an encoded relative path ("external path") rather than an actual path.

    Recognising and constructing such paths is the responsibility of the proxy type itself,
    which allows the general file abstraction to remain free of any knowledge about particular
    language backends.
    """

    @classmethod
    @abstractmethod
    def matches(cls, relative_path: str) -> bool:
        """
        :param relative_path: the relative path to inspect
        :return: whether this proxy type is responsible for the given path
        """

    @classmethod
    @abstractmethod
    def from_relative_path(cls, relative_path: str, project: "Project") -> Self:
        """
        :param relative_path: a relative path for which :meth:`matches` returned True
        :param project: the project the path belongs to
        :return: the proxy providing access to the path's contents
        """


class ExternalFileProxyRegistry:
    """
    Registry of the external file proxy types which the language backends provide.

    A backend contributes its type via a module-level :func:`register_external_file_proxy_type`
    call in the module named in :attr:`_BACKEND_PROXY_MODULES`; the registry imports these
    modules when first queried, so its answers do not depend on which modules an application
    happened to import beforehand.
    """

    _BACKEND_PROXY_MODULES = ("serena.jetbrains.jetbrains_file_proxy",)

    def __init__(self) -> None:
        self._proxy_types: list[type[ExternalFileProxy]] = []
        self._are_backends_loaded = False

    def register(self, proxy_type: type[ExternalFileProxy]) -> None:
        """
        :param proxy_type: the proxy type to add
        """
        self._proxy_types.append(proxy_type)

    def _load_backends(self) -> None:
        """
        Adds the types of all backend modules, importing any module that is not yet loaded
        """
        if self._are_backends_loaded:
            return
        self._are_backends_loaded = True

        for module_name in self._BACKEND_PROXY_MODULES:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                log.warning(f"Failed to load external file proxy module '{module_name}'", exc_info=True)
                continue
            for proxy_type in module.EXTERNAL_FILE_PROXY_TYPES:
                self.register(proxy_type)

    def find(self, relative_path: str) -> type[ExternalFileProxy] | None:
        """
        :param relative_path: the relative path to look up
        :return: the proxy type responsible for the path, or None if it is not an external path
        """
        self._load_backends()
        for proxy_type in self._proxy_types:
            if proxy_type.matches(relative_path):
                return proxy_type
        return None


EXTERNAL_FILE_PROXY_REGISTRY = ExternalFileProxyRegistry()
"""
The registry of external file proxy types used to resolve external paths.
"""
