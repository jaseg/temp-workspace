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
    conf.write_text(json.dumps({"width": 80, "depth": 30}))
    out = tmp_path / "box.svg"
    rc = main(
        [
            "generate",
            "--config",
            str(conf),
            "--set",
            "thumb_notch=true",
            "--set",
            "label_text=a=b",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    cfg = extract_config(out.read_text())
    assert (cfg.width, cfg.depth, cfg.thumb_notch, cfg.label_text) == (80, 30, True, "a=b")


def test_generate_from_svg(tmp_path):
    first, second = tmp_path / "a.svg", tmp_path / "b.svg"
    assert main(["generate", "--set", "width=55", "-o", str(first)]) == 0
    assert (
        main(["generate", "--from-svg", str(first), "--set", "length=99", "-o", str(second)]) == 0
    )
    cfg = extract_config(second.read_text())
    assert (cfg.width, cfg.length) == (55, 99)


def test_generate_errors(tmp_path, capsys):
    out = tmp_path / "x.svg"
    assert main(["generate", "--set", "width=abc", "-o", str(out)]) == 2
    assert main(["generate", "--set", "nope=1", "-o", str(out)]) == 2
    assert main(["generate", "--set", "depth=100", "-o", str(out)]) == 2
    assert main(["generate", "--from-svg", str(tmp_path / "missing.svg"), "-o", str(out)]) == 2
    assert not out.exists()
    assert "depth" in capsys.readouterr().err
