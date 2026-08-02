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
        assert mgr.get_status_text() == "🟢 full"
        mgr.record_failure("memory")
        assert mgr.get_status_text() == "🟡 medium"
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        assert mgr.get_status_text() == "🟠 basic"
        mgr.level = DegradationLevel.EMERGENCY
        assert mgr.get_status_text() == "🔴 emergency"

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


class TestDegradationManagerMutants:
    def test_get_status_text_exact(self):
        mgr = DegradationManager()
        assert mgr.get_status_text() == "🟢 full"

    def test_features_full_exact(self):
        mgr = DegradationManager()
        assert mgr.get_available_features() == [
            "AI",
            "Palace Search",
            "Knowledge Graph",
            "Memory",
            "Code Mode",
            "Voice",
        ]

    def test_features_medium_exact(self):
        mgr = DegradationManager()
        mgr.record_failure("palace_search")
        assert mgr.get_available_features() == ["AI", "Memory", "Code Mode", "Voice"]

    def test_features_basic_exact(self):
        mgr = DegradationManager()
        mgr.record_failure("memory")
        mgr.record_failure("palace_mcp")
        mgr.record_failure("palace_search")
        assert mgr.get_available_features() == ["AI", "Voice (если доступен)"]

    def test_features_emergency_exact(self):
        mgr = DegradationManager()
        mgr.level = DegradationLevel.EMERGENCY
        assert mgr.get_available_features() == ["Emergency responses only"]

    def test_record_success_whisper(self):
        mgr = DegradationManager()
        mgr.record_failure("whisper")
        assert mgr.health.whisper is False
        mgr.record_success("whisper")
        assert mgr.health.whisper is True

    def test_memory_and_palace_search_down_is_medium(self):
        mgr = DegradationManager()
        mgr.record_failure("memory")
        mgr.record_failure("palace_search")
        assert mgr.level == DegradationLevel.MEDIUM

    def test_level_change_logs_exact_message(self, caplog):
        mgr = DegradationManager()
        with caplog.at_level("WARNING", logger="GracefulDegradation"):
            mgr.record_failure("memory")
        assert caplog.records[-1].getMessage() == (
            "Degradation level changed: full → medium"
        )
