from pathlib import Path

import pefile
import pytest

from serena.dotnet.assembly_symbol_index import DnFileMetadataReader


class TestErrorHandling:
    """
    `AssemblySymbolIndex` relies on unreadable assemblies surfacing as exceptions, which it then
    logs and skips, so that one bad file cannot prevent the remaining ones from being searched.
    """

    def test_non_pe_file_raises(self, tmp_path: Path):
        not_an_assembly = tmp_path / "notes.txt"
        not_an_assembly.write_text("hello", encoding="utf-8")

        with pytest.raises(pefile.PEFormatError):
            DnFileMetadataReader().read_symbols(str(not_an_assembly))

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            DnFileMetadataReader().read_symbols(str(tmp_path / "absent.dll"))
