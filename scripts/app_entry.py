"""PyInstaller application entry; smoke test never displays a window."""

import os
import sys

if "--smoke-test" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    from neurospike.analysis import analyze
    from neurospike.demo import demo_recording
    from neurospike.gui import MainWindow

    app = QApplication([])
    window = MainWindow()
    recording = demo_recording()
    window.set_recording(recording)
    counts = [len(analyze(t).spikes) for t in recording.traces]
    assert counts == [3, 5], counts
    window.close()
    print("NeuroSpike packaged smoke test passed: Qt + NumPy + SciPy; demo counts 3, 5")
else:
    from neurospike.gui import main

    raise SystemExit(main())
