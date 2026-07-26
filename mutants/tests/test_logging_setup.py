import json
import logging
import os
import tempfile

from services.logging_setup import JSONFormatter, setup_logging


def test_json_formatter():
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    out = fmt.format(record)
    parsed = json.loads(out)
    assert parsed["lvl"] == "INFO"
    assert parsed["mod"] == "test"
    assert parsed["msg"] == "hello world"
    assert "t" in parsed
    assert "exc" not in parsed


def test_json_formatter_with_exception():
    fmt = JSONFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys
        exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
    out = fmt.format(record)
    parsed = json.loads(out)
    assert parsed["lvl"] == "ERROR"
    assert "exc" in parsed
    assert "ValueError" in parsed["exc"]


def test_setup_logging(tmp_path):
    log = setup_logging(str(tmp_path))
    assert log is not None
    assert log.name == "MainHandler"
    log.info("test message")

    log_file = os.path.join(str(tmp_path), "bot_debug.log")
    assert os.path.exists(log_file), f"Log file not found at {log_file}"
    with open(log_file) as f:
        content = f.read()
    assert "test message" in content


def test_json_formatter_empty_msg():
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="", level=logging.WARNING, pathname="", lineno=0,
        msg="", args=(), exc_info=None,
    )
    out = fmt.format(record)
    parsed = json.loads(out)
    assert parsed["lvl"] == "WARNING"
    assert parsed["msg"] == ""
