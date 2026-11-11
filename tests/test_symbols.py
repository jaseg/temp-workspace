import importlib.util
import json
from pathlib import Path

from factorio_poles.prototypes import POLE_FIELD, POLE_TYPES

ROOT = Path(__file__).resolve().parent.parent


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_library_is_up_to_date():
    gen = load_tool("gen_symbols")
    assert (ROOT / "symbols" / "factorio_poles.kicad_sym").read_text() == gen.library(), "run tools/gen_symbols.py"


def test_every_pole_is_a_global_power_symbol_with_its_type_field():
    lib = (ROOT / "symbols" / "factorio_poles.kicad_sym").read_text()
    for pole in POLE_TYPES:
        start = lib.index(f'(symbol "{pole.symbol_name}"')
        body = lib[start : lib.find('\n\t(symbol "', start + 1)]
        assert "(power global)" in body
        assert f'(property "{POLE_FIELD}" "{pole.name}"' in body
        assert "(pin power_in line" in body


def test_plugin_manifest_entrypoints_exist():
    manifest = json.loads((ROOT / "plugin" / "plugin.json").read_text())
    for action in manifest["actions"]:
        assert (ROOT / "plugin" / action["entrypoint"]).is_file()
        for icon in action.get("icons-light", []) + action.get("icons-dark", []):
            assert (ROOT / "plugin" / icon).is_file()
