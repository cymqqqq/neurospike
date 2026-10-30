"""PyInstaller application entry; smoke test never displays a window."""

import os
import sys

if "--smoke-test" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import tempfile
    from pathlib import Path

    import numpy as np
    from pyabf.abfWriter import writeABF1
    from PySide6.QtWidgets import QApplication

    from neurospike.analysis import analyze
    from neurospike.demo import demo_recording
    from neurospike.export import export_bundle
    from neurospike.gui import MainWindow
    from neurospike.io import load_recording

    app = QApplication([])
    window = MainWindow()
    recording = demo_recording()
    window.set_recording(recording)
    counts = [len(analyze(t).spikes) for t in recording.traces]
    assert counts == [3, 5], counts
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "smoke.abf"
        writeABF1(
            np.stack([t.voltage_mv for t in recording.traces]),
            str(source),
            sampleRateHz=50000,
            units="mV",
        )
        results = [analyze(t) for t in load_recording(source).traces]
        assert [len(r.spikes) for r in results] == [3, 5]
        output = export_bundle(results, root / "export")
        assert (output / "review.png").stat().st_size > 1000
        assert (output / "analysis.json").is_file()
    window.close()
    print("NeuroSpike packaged smoke test passed: Qt + ABF + analysis + CSV/JSON/PNG export")
else:
    from neurospike.gui import main

    raise SystemExit(main())
