"""Toolbar actions.  KiCad starts each one as a separate process (see plugin.json)."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from kipy import KiCad
from kipy.errors import ApiError
from kipy.errors import ConnectionError as KiConnectionError

if TYPE_CHECKING:
    from kipy.schematic import Schematic

    from . import kicad_io

from . import config, textures

IDENTIFIER = "org.jaseg.factorio-poles"


def log(msg: str) -> None:
    print(msg, flush=True)


def connect(socket: str | None = None, open_path: str | None = None) -> tuple[KiCad, Schematic]:
    kicad = KiCad(socket_path=socket) if socket else KiCad()
    if open_path:
        # A headless server (kicad-cli api-server) starts without an open schematic.
        from kipy.proto.common.types import DocumentType

        try:
            kicad.open_document(str(Path(open_path).resolve()), DocumentType.DOCTYPE_SCHEMATIC)
        except ApiError as e:
            if "already open" not in str(e):
                raise
    return kicad, kicad.get_schematic()


def check_kipy() -> str | None:
    """The schematic API arrived in kicad-python 0.9 (KiCad 11)."""
    try:
        import kipy.schematic
    except ImportError:
        import kipy

        return (
            f"kicad-python {getattr(kipy, '__version__', '?')} has no schematic API; this plugin "
            "needs kicad-python 0.9 or newer (see tools/install-dev-plugin.sh for KiCad nightly)"
        )
    return None


def project_dir(sch: Schematic) -> str | None:
    path = sch.document.project.path
    return path or None


def make_pack(settings: config.Settings) -> textures.TexturePack:
    return textures.TexturePack(textures.search_path(settings.textures, settings.use_factorio_install))


def run_update(sch: Schematic, clear: bool = False) -> list[kicad_io.SheetResult]:
    from . import kicad_io  # needs kicad-python's schematic API, see check_kipy()

    settings = config.load(project_dir(sch))
    pack = None if clear else make_pack(settings)
    results = kicad_io.sync(sch, settings, pack, clear=clear)
    log(kicad_io.describe(results))
    if pack is not None:
        for w in dict.fromkeys(pack.warnings):
            log(f"texture warning: {w}")
    return results


# ---------------------------------------------------------------------------
# Live mode


def _pid_file(kicad: KiCad, sch: Schematic) -> Path:
    try:
        base = Path(kicad.get_plugin_settings_path(IDENTIFIER))
    except Exception:  # noqa: BLE001 - older KiCad or headless server
        base = Path(tempfile.gettempdir()) / IDENTIFIER
    base.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1((project_dir(sch) or "").encode()).hexdigest()[:12]
    return base / f"live-{tag}.pid"


def _alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def live(kicad: KiCad, sch: Schematic, max_runtime: float | None = None) -> None:
    """Keep the power lines up to date until stopped.

    Running the action a second time stops the first instance, so the toolbar button
    works as a toggle.
    """
    from . import kicad_io

    pid_file = _pid_file(kicad, sch)
    try:
        other = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        other = 0
    if _alive(other):
        os.kill(other, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        log("live power lines: stopped")
        return

    pid_file.write_text(str(os.getpid()))
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    settings = config.load(project_dir(sch))
    pack = make_pack(settings)
    last = None
    last_full = 0.0
    started = time.monotonic()
    log("live power lines: running (run the action again to stop)")
    try:
        while not stop:
            if max_runtime is not None and time.monotonic() - started > max_runtime:
                break
            try:
                fp = kicad_io.fingerprint(sch, settings)
                # Poles changed: redraw.  Otherwise still re-check the drawing now and then,
                # which repairs it after e.g. an undo of one of our own commits.
                if fp != last or time.monotonic() - last_full > settings.verify_interval:
                    results = kicad_io.sync(sch, settings, pack)
                    if any(r.changed for r in results):
                        log(kicad_io.describe(results))
                    last = fp
                    last_full = time.monotonic()
            except (KiConnectionError, ConnectionError):
                log("live power lines: lost connection to KiCad, exiting")
                break
            except ApiError as e:
                # KiCad is busy (e.g. a modal dialog or an interactive move); try again.
                log(f"live power lines: {e}")
            time.sleep(settings.poll_interval)
    finally:
        try:
            if pid_file.read_text().strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="factorio-poles", description=__doc__)
    ap.add_argument("action", choices=("update", "live", "clear"))
    ap.add_argument("--socket", help="KiCad API socket (default: from the environment KiCad sets)")
    ap.add_argument("--max-runtime", type=float, help="live mode: stop after this many seconds")
    ap.add_argument("--open", metavar="SCHEMATIC", help="open this .kicad_sch first (for headless use)")
    ap.add_argument("--save", action="store_true", help="save the schematic afterwards (for headless use)")
    args = ap.parse_args(argv)
    problem = check_kipy()
    if problem:
        log(problem)
        return 1
    try:
        kicad, sch = connect(args.socket, args.open)
    except Exception as e:  # noqa: BLE001
        log(f"could not connect to KiCad: {e}")
        return 1
    if args.action == "update":
        run_update(sch)
    elif args.action == "clear":
        run_update(sch, clear=True)
    else:
        live(kicad, sch, args.max_runtime)
    if args.save:
        sch.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
