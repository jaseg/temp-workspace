"""The GUI's layout process (kicoil.worker.build_model run by KiCoilGUI.start_layout, poll_layout and stop_layout): the
model is built in a separate process that can be cancelled. The GUI methods run on a fake GUI object without a display;
tkinter is replaced by a stub if it is not installed."""

import sys
import time
import types
from functools import partial

import pytest

from kicoil.geometry import CircleShape, StarShape, SVGShape

try:
    import tkinter # noqa: F401 (importing it needs no display)
except ImportError:
    class _Stub(types.ModuleType):
        def __getattr__(self, name):
            return type(name, (), {})
    for name in ('tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox', 'tkinter.scrolledtext'):
        sys.modules[name] = _Stub(name)
    for name in ('ttk', 'filedialog', 'messagebox', 'scrolledtext'):
        setattr(sys.modules['tkinter'], name, sys.modules[f'tkinter.{name}'])
    sys.modules['tkinter'].TclError = type('TclError', (Exception,), {})

from kicoil.gui import KiCoilGUI


CIRCLE = {'shape': partial(CircleShape, outer_diameter=50, inner_diameter=25), 'turns': 5, 'twists': 2,
          'clearance': 0.15}
# The straight skeleton of a star with many points takes minutes
SLOW = dict(CIRCLE, shape=partial(StarShape, inner_diameter=24, outer_diameter=40, annular_width=3, points=600))


class FakeGUI:
    """ The state that KiCoilGUI's layout methods use. Tk's after() callbacks are run by run_until_idle. """
    start_layout = KiCoilGUI.start_layout
    poll_layout = KiCoilGUI.poll_layout
    stop_layout = KiCoilGUI.stop_layout
    cancel_layout = KiCoilGUI.cancel_layout

    def __init__(self, params):
        self.params = params
        self.results = []
        self.pending = []
        self._validation_after_id = None
        self.layout_process = None
        self.cancel_button = {}
        self.status_var = types.SimpleNamespace(set=lambda text: None)
        self.root = types.SimpleNamespace(after=lambda ms, fn, *args: self.pending.append((fn, args)))

    def get_parameters(self):
        if isinstance(self.params, Exception):
            raise self.params
        return self.params

    def show_result(self, model, error, messages):
        self.results.append((model, error, messages))

    def run_until_idle(self, timeout=120):
        t0 = time.monotonic()
        while self.pending:
            assert time.monotonic() - t0 < timeout
            fn, args = self.pending.pop(0)
            fn(*args)
            time.sleep(0.02)

    def run(self):
        self.results.clear()
        self.start_layout()
        self.run_until_idle()
        result, = self.results
        return result


@pytest.fixture
def gui():
    gui = FakeGUI(CIRCLE)
    yield gui
    gui.stop_layout()


def test_model_and_messages(gui):
    model, error, messages = gui.run()
    assert error is None and model.trace_width > 0
    assert model.render_footprint('coil').arcs
    assert ('info', 'INFO: Outer diameter: 50 mm') in messages
    assert ('warning', 'WARNING: No via drill given, defaulting to 3.62 mm based on via diameter.') in messages
    assert gui.layout_process is None and gui.cancel_button['state'] == 'disabled'


def test_warnings(gui):
    gui.params = dict(CIRCLE, clearance=None)
    model, error, messages = gui.run()
    assert any(tag == 'warning' and 'Neither trace width nor clearance' in text for tag, text in messages)


def test_infeasible_request(gui):
    gui.params = dict(CIRCLE, turns=4) # 4 turns and 2 twists are not co-prime
    model, error, messages = gui.run()
    assert model is None and 'co-prime' in error


def test_cancel_and_restart(gui):
    gui.params = SLOW
    gui.start_layout()
    process = gui.layout_process
    time.sleep(0.5)
    gui.poll_layout(process)
    assert not gui.results and gui.cancel_button['state'] == 'normal'
    t0 = time.monotonic()
    gui.cancel_layout()
    assert time.monotonic() - t0 < 5 and process.exitcode is not None
    assert gui.results == [(None, 'Cancelled', [])]
    # A parameter change stops the running process, and the polls of the old process do nothing
    gui.results.clear()
    gui.start_layout()
    slow = gui.layout_process
    gui.params = CIRCLE
    model, error, messages = gui.run()
    assert slow.exitcode is not None and error is None


def test_invalid_parameter_stops_the_running_process(gui):
    gui.params = SLOW
    gui.start_layout()
    slow = gui.layout_process
    gui.params = ValueError('could not convert string to float')
    model, error, messages = gui.run()
    assert slow.exitcode is not None and gui.layout_process is None
    assert error == 'Invalid parameter: could not convert string to float'


def test_crashed_process(gui):
    gui.params = SLOW
    gui.start_layout()
    process = gui.layout_process
    time.sleep(0.5)
    process.kill() # e.g. killed for running out of memory
    gui.run_until_idle()
    (model, error, messages), = gui.results
    assert model is None and 'ended unexpectedly' in error
    assert process.exitcode is not None and gui.layout_process is None # reaped


SQUARE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="{0}mm" height="{0}mm" viewBox="0 0 {0} {0}">' \
             '<rect width="{0}" height="{0}"/></svg>'


def test_rereads_an_edited_svg_file(gui, tmp_path):
    path = tmp_path / 'outline.svg'
    gui.params = {'shape': partial(SVGShape, filename=str(path), annular_width=8), 'turns': 3, 'twists': 1}
    path.write_text(SQUARE_SVG.format(30))
    first, _, _ = gui.run()
    path.write_text(SQUARE_SVG.format(60))
    second, _, _ = gui.run()
    assert second.trace_width != first.trace_width


PARENT = '''
import multiprocessing, sys, time
from functools import partial
from kicoil.geometry import StarShape
from kicoil.worker import build_model
if __name__ == '__main__':
    ctx = multiprocessing.get_context('spawn')
    conn, child_conn = ctx.Pipe(duplex=False)
    params = {'shape': partial(StarShape, inner_diameter=24, outer_diameter=40, annular_width=3, points=600),
              'turns': 5, 'twists': 2, 'clearance': 0.15}
    process = ctx.Process(target=build_model, args=(child_conn, params), daemon=True)
    process.start()
    print(process.pid, flush=True)
    time.sleep(600)
'''


def test_exits_when_the_gui_is_killed(tmp_path):
    import os
    import signal
    import subprocess
    script = tmp_path / 'parent.py'
    script.write_text(PARENT)
    parent = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    time.sleep(3) # (the child is computing the skeleton)
    os.kill(parent.pid, signal.SIGKILL)
    parent.wait()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 10:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        # (it is a child of init now, which reaps it)
        time.sleep(0.1)
    os.kill(child, signal.SIGKILL)
    pytest.fail('The layout process is still running after the GUI process was killed')
