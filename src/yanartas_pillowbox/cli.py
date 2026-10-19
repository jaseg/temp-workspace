"""Command-line entry point: ``serve`` (default), ``generate`` and ``pcb``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import webbrowser
from pathlib import Path

from yanartas_pillowbox import __version__
from yanartas_pillowbox.config import Config, ConfigError, SchemaVersionError, parse_cli_value
from yanartas_pillowbox.persistence import default_settings_path
from yanartas_pillowbox.svg import SvgImportError, extract_config, render_svg

log = logging.getLogger("yanartas_pillowbox")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yanartas-pillowbox",
        description="Generate laser-ready SVG folding patterns for pillow boxes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web UI (default)")
    _add_serve_args(serve)

    gen = sub.add_parser("generate", help="generate an SVG without the UI")
    _add_config_args(gen)
    gen.add_argument(
        "-o", "--output", required=True, metavar="OUT.svg", help="output file, or - for stdout"
    )

    pcb = sub.add_parser(
        "pcb", help="lay the box out as a flex PCB with a security mesh (KiCad, Gerber, SVG)"
    )
    _add_config_args(pcb)
    pcb.add_argument("-o", "--output", required=True, metavar="DIR", help="output directory")
    pcb.add_argument("--name", default="pillowbox", help="base name of the files written")
    return parser


def _add_config_args(p: argparse.ArgumentParser) -> None:
    src = p.add_mutually_exclusive_group()
    src.add_argument("--config", type=Path, metavar="FILE", help="JSON config file")
    src.add_argument(
        "--from-svg",
        type=Path,
        metavar="FILE",
        help="take the config embedded in a previously generated SVG",
    )
    p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override one parameter (repeatable), e.g. --set width=80",
    )


def _add_serve_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port", type=int, default=0, help="port to listen on (default: a free one)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser window")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # no per-request log lines
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    # Bare invocation (optionally with serve flags) means "serve".
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version")):
        argv = ["serve", *argv]
    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "pcb":
        return cmd_pcb(args)
    return cmd_serve(args)


def _load_config(args: argparse.Namespace) -> Config | None:
    """The config the arguments give, or None (errors printed)."""
    try:
        cfg = Config.defaults()
        if args.config is not None:
            cfg = Config.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
        elif args.from_svg is not None:
            cfg = extract_config(args.from_svg.read_bytes())
        overrides = {}
        for item in args.set:
            key, sep, value = item.partition("=")
            if not sep:
                raise ConfigError({item: "expected KEY=VALUE"})
            overrides[key.strip()] = parse_cli_value(key.strip(), value)
        if overrides:
            cfg = Config.from_dict({**cfg.to_dict(), **overrides})
    except ConfigError as exc:
        for key, msg in exc.errors.items():
            print(f"error: {key}: {msg}", file=sys.stderr)
        return None
    except (SchemaVersionError, SvgImportError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    return cfg


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    if cfg is None:
        return 2
    svg = render_svg(cfg)
    if args.output == "-":
        sys.stdout.write(svg)
    else:
        Path(args.output).write_text(svg, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


def cmd_pcb(args: argparse.Namespace) -> int:
    from yanartas_pillowbox import pcb

    cfg = _load_config(args)
    if cfg is None:
        return 2
    try:
        layout = pcb.layout(cfg)
    except pcb.PcbError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for side, m in layout.meshes.items():
        missed = f", {m.unreached} out of reach" if m.unreached else ""
        print(f"{side}: mesh over {m.cells} cells of {m.cell:g} mm{missed}", file=sys.stderr)
    net, length = layout.longest_trace()
    print(f"longest trace: {net}, {length / 1000:.2f} m", file=sys.stderr)
    for path in pcb.export(layout, args.output, args.name):
        print(f"wrote {path}", file=sys.stderr)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from werkzeug.serving import make_server

    from yanartas_pillowbox.server import create_app

    settings = default_settings_path()
    app = create_app(settings)
    try:
        server = make_server("127.0.0.1", args.port, app, threaded=True)
    except OSError as exc:
        print(f"error: cannot listen on 127.0.0.1:{args.port}: {exc}", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"yanartas-pillowbox running at {url}  (settings: {settings})", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
