from solidlsp.language_servers.csharp_language_server import resolve_workspace_configuration_sections


class TestDecompilationOptions:
    def test_decompiled_sources_navigation_is_enabled(self):
        """Decompilation must be on; it is what resolves definitions into source-less assemblies."""
        assert resolve_workspace_configuration_sections(["csharp_navigate_to_decompiled_sources"]) == [True]

    def test_source_link_navigation_is_enabled(self):
        assert resolve_workspace_configuration_sections(["csharp_navigate_to_source_link_and_embedded_sources"]) == [True]

    def test_other_navigate_options_stay_disabled(self):
        """Regression guard: only the decompilation options are exempt from the generic rule."""
        assert resolve_workspace_configuration_sections(["csharp_navigate_to_generated_code"]) == [False]

    def test_unrelated_sections_keep_their_defaults(self):
        assert resolve_workspace_configuration_sections(["tab_width", "insert_final_newline"]) == [4, True]

    def test_section_order_is_preserved(self):
        sections = ["tab_width", "csharp_navigate_to_decompiled_sources", "csharp_enable_foo"]
        assert resolve_workspace_configuration_sections(sections) == [4, True, False]
