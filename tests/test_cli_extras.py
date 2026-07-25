import pytest

from cli_extras import cli_remind, cli_yt, cli_kgadd


class TestCliRemind:
    async def test_empty_text_returns_help(self):
        result = await cli_remind("/remind", 0)
        assert "Укажите" in result

    async def test_short_text_not_reminder(self):
        result = await cli_remind("/remind hello", 0)
        assert "Не похоже" in result or "не похоже" in result


class TestCliYt:
    async def test_no_url_returns_help(self):
        result = await cli_yt("", "video")
        assert "Укажите URL" in result

    async def test_bad_url_returns_help(self):
        result = await cli_yt("not_a_url", "video")
        assert "Укажите URL" in result


class TestCliTunnels:
    async def test_create_without_args_returns_help(self):
        from unittest.mock import AsyncMock, patch
        with patch("cli_extras.get_mcp") as mock_get:
            mcp_mock = AsyncMock()
            mcp_mock.call_tool.return_value = "[]"
            mock_get.return_value = mcp_mock
            from cli_extras import cli_tunnels
            result = await cli_tunnels("create")
            assert "create" in result or "list" in result

    async def test_delete_without_id_returns_help(self):
        from unittest.mock import AsyncMock, patch
        with patch("cli_extras.get_mcp") as mock_get:
            mcp_mock = AsyncMock()
            mock_get.return_value = mcp_mock
            from cli_extras import cli_tunnels
            result = await cli_tunnels("delete")
            assert "list" in result

    async def test_list_default(self):
        from unittest.mock import AsyncMock, patch
        with patch("cli_extras.get_mcp") as mock_get:
            mcp_mock = AsyncMock()
            mcp_mock.call_tool.return_value = "[]"
            mock_get.return_value = mcp_mock
            from cli_extras import cli_tunnels
            result = await cli_tunnels("")
            assert "Туннелей" in result


class TestCliKgadd:
    async def test_missing_args_returns_error(self):
        result = await cli_kgadd("")
        assert "субъект" in result

    async def test_two_args_returns_error(self):
        result = await cli_kgadd("subject predicate")
        assert "субъект" in result

    async def test_three_args_attempts_insert(self):
        from unittest.mock import AsyncMock, patch
        with patch("cli_extras.get_mcp") as mock_get:
            mcp_mock = AsyncMock()
            mcp_mock.call_tool.return_value = {"success": True}
            mock_get.return_value = mcp_mock
            result = await cli_kgadd("subject predicate object")
            assert "Факт" in result


class TestCliPalaceCmd:
    async def test_unknown_command(self):
        from cli_extras import cli_palace_cmd
        result = await cli_palace_cmd("nonexistent")
        assert result is None

    async def test_status_called(self):
        from unittest.mock import patch
        from cli_extras import cli_palace_cmd
        with patch("cli_extras.palace_status") as mock_status:
            mock_status.return_value = "mocked status"
            result = await cli_palace_cmd("status")
            assert result == "mocked status"

    async def test_repair_called(self):
        from unittest.mock import patch
        from cli_extras import cli_palace_cmd
        with patch("cli_extras.palace_repair") as mock_repair:
            mock_repair.return_value = "mocked repair"
            result = await cli_palace_cmd("repair")
            assert result == "mocked repair"

    async def test_compress_called(self):
        from unittest.mock import patch
        from cli_extras import cli_palace_cmd
        with patch("cli_extras.palace_compact") as mock_c:
            mock_c.return_value = "mocked compact"
            result = await cli_palace_cmd("compact")
            assert result == "mocked compact"

    async def test_wakeup_called(self):
        from unittest.mock import patch
        from cli_extras import cli_palace_cmd
        with patch("cli_extras.palace_wake_up") as mock_w:
            mock_w.return_value = "mocked wakeup"
            result = await cli_palace_cmd("wakeup")
            assert result == "mocked wakeup"
