import logging
import os
from pathlib import Path
from xml.etree import ElementTree

log = logging.getLogger(__name__)


class AssemblyReferenceResolver:
    """
    Determines which .NET assemblies a project references, restricted to assemblies that
    ship without sources (assemblies with sources alongside them are served by the language
    server already and need no metadata reading).
    """

    _SOURCE_FILE_SUFFIX = ".cs"

    def __init__(self, project_root: str) -> None:
        """
        :param project_root: the root directory of the project to inspect
        """
        self._project_root = Path(project_root)

    def resolve(self) -> list[str]:
        """
        :return: absolute paths of the referenced source-less assemblies, deduplicated and sorted
        """
        assembly_paths: set[Path] = set()
        for project_file in self._project_root.rglob("*.csproj"):
            assembly_paths.update(self._read_hint_paths(project_file))

        # keep only existing assemblies that ship without sources
        result = {p for p in assembly_paths if p.is_file() and not self._has_sources_alongside(p)}
        return sorted(str(p) for p in result)

    def _read_hint_paths(self, project_file: Path) -> list[Path]:
        """
        :param project_file: the .csproj file to read
        :return: the absolute assembly paths referenced by the given project file
        """
        try:
            tree = ElementTree.parse(project_file)
        except ElementTree.ParseError as e:
            log.warning("Ignoring malformed project file %s: %s", project_file, e)
            return []

        paths = []
        for hint_path_element in tree.iter():
            if not hint_path_element.tag.endswith("HintPath") or not hint_path_element.text:
                continue
            # HintPath is relative to the project file and uses Windows separators
            hint_path = hint_path_element.text.strip().replace("\\", os.path.sep)
            paths.append((project_file.parent / hint_path).resolve())
        return paths

    def _has_sources_alongside(self, assembly_path: Path) -> bool:
        """
        :param assembly_path: the path of the assembly to check
        :return: whether source files are present in the assembly's directory
        """
        return any(assembly_path.parent.glob(f"*{self._SOURCE_FILE_SUFFIX}"))
