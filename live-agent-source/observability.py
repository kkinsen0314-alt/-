"""Agent 运行与重试日志。"""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Union


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event_name", record.getMessage()),
            "run_id": getattr(record, "run_id", ""),
            "payload": getattr(record, "event_payload", {}),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_path: Union[str, Path]) -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("live_agent")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path.resolve()
               for handler in logger.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, event: str, run_id: str, payload: Optional[dict[str, Any]] = None,
              level: int = logging.INFO) -> None:
    logger.log(level, event, extra={"event_name": event, "run_id": run_id, "event_payload": payload or {}})
