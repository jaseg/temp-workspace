"""The GUI's layout worker (kicoil.worker): layouts run in a separate process and can be cancelled."""

import time

from kicoil.worker import LayoutWorker, run_job


CIRCLE = {'shape': ('CircleShape', {'outer_diameter': 50, 'inner_diameter': 25}),
          'inductor': {'turns': 5, 'twists': 2, 'clearance': 0.15}, 'render': {'name': 'coil'}}


def wait(worker, timeout=120):
    t0 = time.monotonic()
    while (result := worker.poll()) is None:
        assert worker.busy and time.monotonic() - t0 < timeout
        time.sleep(0.02)
    return result


def test_run_job_returns_footprint_values_and_messages():
    result = run_job(CIRCLE)
    assert result['ok'], result
    assert result['footprint'].name == 'coil' and result['footprint'].arcs
    assert result['values']['trace_width'] > 0
    assert any('drill' in text for _level, text in result['messages']) # a logged warning


def test_run_job_reports_infeasible_requests():
    job = dict(CIRCLE, inductor={'turns': 4, 'twists': 2}) # not co-prime
    result = run_job(job)
    assert not result['ok'] and 'co-prime' in result['error']


def test_worker_runs_jobs_and_can_be_cancelled():
    worker = LayoutWorker()
    try:
        worker.submit(CIRCLE)
        assert wait(worker)['ok']
        # The straight skeleton of a star with many points takes minutes: cancel it and run another job right away
        slow = dict(CIRCLE, shape=('StarShape', {'inner_diameter': 24, 'outer_diameter': 40, 'annular_width': 3,
                                                 'points': 600}))
        worker.submit(slow)
        time.sleep(0.5)
        assert worker.busy and worker.poll() is None
        t0 = time.monotonic()
        worker.cancel()
        assert not worker.busy and time.monotonic() - t0 < 5
        worker.submit(CIRCLE)
        assert wait(worker)['ok']
    finally:
        worker.close()


def test_worker_reports_a_crashed_process_and_recovers():
    worker = LayoutWorker()
    try:
        worker.submit(dict(CIRCLE, shape=('StarShape', {'inner_diameter': 24, 'outer_diameter': 40,
                                                        'annular_width': 3, 'points': 600})))
        time.sleep(0.5)
        proc = worker._proc
        proc.kill() # e.g. killed for running out of memory
        result = wait(worker)
        assert not result['ok'] and 'ended unexpectedly' in result['error']
        assert proc.exitcode is not None # reaped, not a zombie
        worker.submit(CIRCLE)
        assert wait(worker)['ok']
    finally:
        worker.close()


SQUARE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="{0}mm" height="{0}mm" viewBox="0 0 {0} {0}">' \
             '<rect width="{0}" height="{0}"/></svg>'


def test_run_job_rereads_an_edited_svg_file(tmp_path):
    path = tmp_path / 'outline.svg'
    job = dict(CIRCLE, shape=('SVGShape', {'filename': str(path), 'annular_width': 8}),
               inductor={'turns': 3, 'twists': 1})
    path.write_text(SQUARE_SVG.format(30))
    first = run_job(job)
    path.write_text(SQUARE_SVG.format(60))
    second = run_job(job)
    assert first['ok'] and second['ok']
    assert second['values']['trace_width'] != first['values']['trace_width']
