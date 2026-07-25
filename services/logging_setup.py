import sys
import json as json_mod
import logging.handlers
import os


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "t": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "mod": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exc"] = self.formatException(record.exc_info)
        return json_mod.dumps(log_entry, ensure_ascii=False)


def setup_logging(data_dir: str) -> logging.Logger:
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    _console_handler = logging.StreamHandler(sys.stdout)
    _console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    )
    logging.root.addHandler(_console_handler)

    _file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(data_dir, "bot_debug.log"),
        encoding="utf-8",
        maxBytes=10_485_760,
        backupCount=3,
    )
    _file_handler.setFormatter(JSONFormatter())
    logging.root.addHandler(_file_handler)

    logging.root.setLevel(logging.INFO)
    return logging.getLogger("MainHandler")
