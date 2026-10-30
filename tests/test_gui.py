import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from neurospike.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qt_app):
    app = qt_app
    w = MainWindow()
    w.load_demo()
    yield app, w
    deadline = time.monotonic() + 15
    while w.thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert w.thread is None
    w.close()


def wait_done(app, window):
    deadline = time.monotonic() + 15
    while window.thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.thread is None


def test_offscreen_load_analyze_exclude_and_invalidate(window):
    from PySide6.QtCore import Qt

    app, w = window
    w.all_sweeps.setChecked(True)
    w.run_analysis()
    wait_done(app, w)
    assert [len(r.spikes) for r in w.results.values()] == [3, 5]
    assert w.table.rowCount() == 3
    w.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    wait_done(app, w)
    assert len(w.results[0].spikes) == 2
    assert w.table.rowCount() == 2
    w.reset_exclusions()
    wait_done(app, w)
    assert len(w.results[0].spikes) == 3
    w.inputs["min_peak_mv"].setValue(-10)
    assert not w.results
    assert not w.export_button.isEnabled()


def test_sweep_switch_and_worker_error(window):
    app, w = window
    errors = []
    w.error = errors.append
    w.sweep.setCurrentIndex(1)
    w.run_analysis()
    wait_done(app, w)
    assert w.table.rowCount() == 5
    assert w.sweep.currentIndex() == 1
    w.run_task(lambda: 1 / 0, lambda result: None)
    wait_done(app, w)
    assert errors and "ZeroDivisionError" in errors[0]
    assert w.analyze_button.isEnabled()


def test_worker_callbacks_return_to_main_thread_and_export(window, tmp_path):
    from neurospike.export import export_bundle

    app, w = window
    callback_threads = []
    main_thread = threading.get_ident()
    w.run_task(
        lambda: threading.get_ident(),
        lambda result: callback_threads.append((result, threading.get_ident())),
    )
    wait_done(app, w)
    assert callback_threads[0][0] != main_thread
    assert callback_threads[0][1] == main_thread
    w.run_analysis()
    wait_done(app, w)
    outputs = []
    w.run_task(
        lambda: export_bundle(list(w.results.values()), tmp_path / "gui-export"), outputs.append
    )
    wait_done(app, w)
    assert (outputs[0] / "review.png").exists()
