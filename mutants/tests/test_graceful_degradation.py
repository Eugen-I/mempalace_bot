from services.graceful_degradation import DegradationLevel, DegradationManager


class TestDegradationManager:
    def test_initial_state_full(self):
        mgr = DegradationManager()
        assert mgr.level == DegradationLevel.FULL

    def test_palace_search_failure_downgrades_to_medium(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_search")
        assert mgr.level == DegradationLevel.MEDIUM

    def test_palace_mcp_failure_downgrades(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_mcp")
        assert mgr.level == DegradationLevel.MEDIUM

    def test_both_palace_down_is_medium_if_memory_ok(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        assert mgr.level == DegradationLevel.MEDIUM

    def test_memory_failure_downgrades_to_medium(self):
        mgr = DegradationManager()
        mgr.record_failure("memory")
        assert mgr.level == DegradationLevel.MEDIUM

    def test_palace_and_memory_down_is_basic(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        mgr.record_failure("memory")
        assert mgr.level == DegradationLevel.BASIC

    def test_recovery_to_full(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_search")
        mgr.record_failure("palace_mcp")
        mgr.record_failure("memory")
        assert mgr.level == DegradationLevel.BASIC
        mgr.record_success("memory")
        assert mgr.level == DegradationLevel.MEDIUM
        mgr.record_success("palace_search")
        assert mgr.level == DegradationLevel.MEDIUM
        mgr.record_success("palace_mcp")
        assert mgr.level == DegradationLevel.FULL

    def test_should_use_palace(self):
        mgr = DegradationManager()
        assert mgr.should_use_palace() is True
        mgr.record_failure("palace_search")
        mgr.record_failure("palace_mcp")
        mgr.record_failure("memory")
        assert mgr.should_use_palace() is False

    def test_should_use_memory(self):
        mgr = DegradationManager()
        assert mgr.should_use_memory() is True
        mgr.record_failure("palace_search")
        mgr.record_failure("palace_mcp")
        mgr.record_failure("memory")
        assert mgr.should_use_memory() is False

    def test_whisper_independent(self):
        mgr = DegradationManager()
        assert mgr.should_use_whisper() is True
        mgr.record_failure("whisper")
        assert mgr.should_use_whisper() is False

    def test_get_status_text(self):
        mgr = DegradationManager()
        assert "full" in mgr.get_status_text()
        mgr.record_failure("memory")
        assert "medium" in mgr.get_status_text()
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        assert "basic" in mgr.get_status_text()

    def test_get_available_features_full(self):
        mgr = DegradationManager()
        features = mgr.get_available_features()
        assert "AI" in features
        assert "Palace Search" in features
        assert "Knowledge Graph" in features
        assert "Memory" in features

    def test_get_available_features_medium(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_search")
        features = mgr.get_available_features()
        assert "Palace Search" not in features
        assert "Knowledge Graph" not in features
        assert "Memory" in features

    def test_get_available_features_basic(self):
        mgr = DegradationManager()
        mgr.record_failure("memory")
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        features = mgr.get_available_features()
        assert "Palace Search" not in features
        assert "Memory" not in features

    def test_unknown_component_does_not_raise(self):
        mgr = DegradationManager()
        mgr.record_failure("unknown")
        assert mgr.level == DegradationLevel.FULL
        mgr.record_success("unknown")
