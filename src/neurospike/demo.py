"""Deterministic synthetic recordings, never presented as experimental data."""

import numpy as np

from .models import Recording, Trace


def demo_recording():
    t = np.arange(0, 0.5, 0.00002)
    rng = np.random.default_rng(42)
    traces = []
    for sweep, times in enumerate(([0.1, 0.2, 0.3], [0.08, 0.14, 0.22, 0.32, 0.43])):
        v = np.full(len(t), -65.0)
        for onset in times:
            knots = onset + np.array([-0.002, 0, 0.0005, 0.001, 0.002, 0.004, 0.012])
            shape = np.array([-65, -55, 30, -25, -70, -75, -65])
            v += np.interp(t, knots, shape, left=-65, right=-65) + 65
        v += rng.normal(0, 0.12, len(v))
        traces.append(Trace(t, v, "synthetic_demo", sweep))
    return Recording(traces, [{"index": 0, "name": "Synthetic voltage", "unit": "mV"}])
