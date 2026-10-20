import json

from yanartas_pillowbox.cli import main
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.svg import extract_config


def test_generate_defaults(tmp_path):
    out = tmp_path / "box.svg"
    assert main(["generate", "-o", str(out)]) == 0
    assert extract_config(out.read_text()) == Config.defaults()


def test_generate_with_overrides_and_config(tmp_path):
    conf = tmp_path / "c.json"
    conf.write_text(json.dumps({"width": 80, "height": 30, "fpc_cable": "none"}))
    out = tmp_path / "box.svg"
    rc = main(
        [
            "generate",
            "--config",
            str(conf),
            "--set",
            "glue_tab_width=15",
            "--set",
            "thickness=0.5",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    cfg = extract_config(out.read_text())
    assert (cfg.width, cfg.height, cfg.glue_tab_width, cfg.thickness) == (80, 30, 15, 0.5)


def test_generate_from_svg(tmp_path):
    first, second = tmp_path / "a.svg", tmp_path / "b.svg"
    assert main(["generate", "--set", "width=120", "-o", str(first)]) == 0
    assert (
        main(["generate", "--from-svg", str(first), "--set", "length=99", "-o", str(second)]) == 0
    )
    cfg = extract_config(second.read_text())
    assert (cfg.width, cfg.length) == (120, 99)


def test_generate_errors(tmp_path, capsys):
    out = tmp_path / "x.svg"
    assert main(["generate", "--set", "width=abc", "-o", str(out)]) == 2
    assert main(["generate", "--set", "nope=1", "-o", str(out)]) == 2
    assert main(["generate", "--set", "height=100", "-o", str(out)]) == 2
    assert main(["generate", "--from-svg", str(tmp_path / "missing.svg"), "-o", str(out)]) == 2
    assert not out.exists()
    assert "height" in capsys.readouterr().err


def test_progress_lines_name_stage_phase_step_and_figures():
    import io

    from yanartas_pillowbox import progress
    from yanartas_pillowbox.cli import _Progress

    out = io.StringIO()
    bar = _Progress(out)
    with progress.listening(bar), progress.stage("F.Cu", 1, 2):
        progress.report("settle", 3, 40, vertices=1_500_000, moved=420, apart=[9.0, 9.0])
        progress.report("match", 2, 20, vertices=1_500_000, apart=[1.25, 0.5])
    bar.close()
    lines = out.getvalue().splitlines()
    assert lines == [
        "F.Cu: settle 3/40 (1.50 M vertices, 420 moved)",
        "F.Cu: match 2/20 (1.50 M vertices, skew 1.2/0.5 mm)",
    ]
    events = []
    with progress.listening(events.append), progress.stage("B.Cu", 1, 2):
        progress.report("match", 20, 20)
    assert events[0]["done"] == 1.0
    progress.report("graph")  # (no one listening: nothing happens)


def test_side_by_side_runs_both_and_merges_progress():
    from yanartas_pillowbox import progress

    events = []

    def job(name):
        def run():
            progress.report("settle", 1, 2)
            return name

        return run

    with progress.listening(events.append):
        out = progress.side_by_side([("F.Cu", job("front")), ("B.Cu", job("back"))])
    assert out == ["front", "back"]
    assert {e["stage"] for e in events} == {"F.Cu", "B.Cu"}
    assert max(e["done"] for e in events) < 1  # (each side half way: the mean too)
