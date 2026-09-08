from pathlib import Path

from serena.dotnet.assembly_symbol import AssemblySymbol, AssemblySymbolKind
from serena.dotnet.assembly_symbol_cache import AssemblySymbolCache


def make_symbol(name: str, assembly_path: str) -> AssemblySymbol:
    return AssemblySymbol(
        name=name,
        kind=AssemblySymbolKind.TYPE,
        namespace="Some.Namespace",
        declaring_type_name_path=None,
        assembly_path=assembly_path,
    )


def write_assembly(directory: Path, name: str = "Lib.dll", content: bytes = b"MZ-original") -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


class TestRoundTrip:
    def test_symbols_survive_save_and_load(self, tmp_path: Path):
        assembly = write_assembly(tmp_path)
        cache_file = tmp_path / "cache.pickle.gz"

        cache = AssemblySymbolCache(str(cache_file))
        cache.put(str(assembly), [make_symbol("Widget", str(assembly))])
        cache.save()

        reloaded = AssemblySymbolCache(str(cache_file))
        reloaded.load()

        assert [s.name for s in reloaded.get(str(assembly)) or []] == ["Widget"]

    def test_unknown_assembly_is_a_miss(self, tmp_path: Path):
        cache = AssemblySymbolCache(str(tmp_path / "cache.pickle.gz"))

        assert cache.get(str(tmp_path / "Absent.dll")) is None

    def test_empty_symbol_list_is_a_hit_not_a_miss(self, tmp_path: Path):
        """An assembly that genuinely declares nothing must not be re-read on every search."""
        assembly = write_assembly(tmp_path)
        cache = AssemblySymbolCache(str(tmp_path / "cache.pickle.gz"))

        cache.put(str(assembly), [])

        assert cache.get(str(assembly)) == []


class TestInvalidation:
    def test_modified_assembly_is_a_miss(self, tmp_path: Path):
        assembly = write_assembly(tmp_path)
        cache = AssemblySymbolCache(str(tmp_path / "cache.pickle.gz"))
        cache.put(str(assembly), [make_symbol("Widget", str(assembly))])

        # a rebuild changes size and mtime
        assembly.write_bytes(b"MZ-rebuilt-and-longer")

        assert cache.get(str(assembly)) is None

    def test_other_assemblies_stay_valid_when_one_changes(self, tmp_path: Path):
        """Invalidation is per assembly: one rebuilt library must not discard the rest."""
        changed = write_assembly(tmp_path, "Changed.dll")
        stable = write_assembly(tmp_path, "Stable.dll")
        cache = AssemblySymbolCache(str(tmp_path / "cache.pickle.gz"))
        cache.put(str(changed), [make_symbol("A", str(changed))])
        cache.put(str(stable), [make_symbol("B", str(stable))])

        changed.write_bytes(b"MZ-rebuilt-and-longer")

        assert cache.get(str(changed)) is None
        assert [s.name for s in cache.get(str(stable)) or []] == ["B"]

    def test_deleted_assembly_is_a_miss(self, tmp_path: Path):
        assembly = write_assembly(tmp_path)
        cache = AssemblySymbolCache(str(tmp_path / "cache.pickle.gz"))
        cache.put(str(assembly), [make_symbol("Widget", str(assembly))])

        assembly.unlink()

        assert cache.get(str(assembly)) is None


class TestCorruptedCacheFile:
    def test_unreadable_cache_file_behaves_as_empty(self, tmp_path: Path):
        """A corrupted cache must degrade to re-reading, never break the search."""
        cache_file = tmp_path / "cache.pickle.gz"
        cache_file.write_bytes(b"not a gzip stream")
        assembly = write_assembly(tmp_path)

        cache = AssemblySymbolCache(str(cache_file))
        cache.load()

        assert cache.get(str(assembly)) is None

    def test_missing_cache_file_behaves_as_empty(self, tmp_path: Path):
        cache = AssemblySymbolCache(str(tmp_path / "nested" / "cache.pickle.gz"))
        cache.load()

        assert cache.get(str(tmp_path / "Lib.dll")) is None

    def test_save_creates_missing_parent_directories(self, tmp_path: Path):
        cache_file = tmp_path / "nested" / "deeper" / "cache.pickle.gz"
        cache = AssemblySymbolCache(str(cache_file))

        cache.save()

        assert cache_file.is_file()
