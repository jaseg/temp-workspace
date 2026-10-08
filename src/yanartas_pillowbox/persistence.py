"""Load/save the last-used configuration (``./yanartas-pillowbox.json``)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError

log = logging.getLogger(__name__)

SETTINGS_FILENAME = "yanartas-pillowbox.json"


def default_settings_path() -> Path:
    return Path.cwd() / SETTINGS_FILENAME


def load_config(path: Path) -> Config:
    """Load the saved config. Never raises: anything unusable falls back to the defaults."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config.defaults()
    except OSError as exc:
        log.warning("Could not read %s (%s); using defaults.", path, exc)
        return Config.defaults()
    try:
        return Config.from_dict(json.loads(text), require_version=True)
    except json.JSONDecodeError as exc:
        log.warning("%s is corrupt (%s); using defaults.", path, exc)
    except SchemaVersionError as exc:
        log.warning("%s is from an incompatible version (%s); using defaults.", path, exc)
    except ConfigError as exc:
        log.warning("%s contains an invalid configuration (%s); using defaults.", path, exc)
    return Config.defaults()


def save_config(path: Path, cfg: Config) -> None:
    """Atomically write the config (write to a temp file, then rename over the target)."""
    data = json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".yanartas-pillowbox.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
