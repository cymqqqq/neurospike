import numpy as np
import pytest

from neurospike.analysis import AnalysisConfig, analyze
from neurospike.models import Trace


def triangle_trace(peaks=(0.02,), end=0.1, offset=0):
    t = np.arange(0, end + 0.000005, 0.00001)
    v = np.full(t.shape, -65.0)
    for peak in peaks:
        knots = np.array([peak - 0.001, peak, peak + 0.001, peak + 0.003, peak + 0.008])
        v += np.interp(t, knots, [-65, 35, -65, -75, -65], left=-65, right=-65) + 65
    return Trace(t + offset, v)


def config(**kwargs):
    return AnalysisConfig(baseline_start_s=0, baseline_end_s=0.005, **kwargs)


def test_analytical_triangle_width_slopes_amplitude_and_ahp():
    result = analyze(triangle_trace(), config(start_s=0.01, end_s=0.09))
    assert len(result.spikes) == 1
    s = result.spikes[0]
    assert s.peak_time_s == pytest.approx(0.02)
    assert s.peak_mv == pytest.approx(35)
    assert -65.1 < s.threshold_mv < -64.8
    assert s.amplitude_mv == pytest.approx(100, abs=0.2)
    assert s.half_width_ms == pytest.approx(1, abs=0.005)
    assert s.max_upstroke_mv_ms == pytest.approx(100)
    assert s.max_downstroke_mv_ms == pytest.approx(-100)
    assert s.ahp_trough_time_s == pytest.approx(0.023)
    assert s.ahp_depth_from_baseline_mv == pytest.approx(10)
    assert s.ahp_depth_from_threshold_mv == pytest.approx(10, abs=0.2)
    assert result.summary["first_peak_latency_ms"] == pytest.approx(10)
    assert result.summary["firing_rate_hz"] == pytest.approx(12.5)
    assert result.summary["n_half_width_ms"] == 1


def test_multiple_spikes_interval_frequency_and_adaptation():
    result = analyze(triangle_trace((0.02, 0.04, 0.08)), config())
    assert len(result.spikes) == 3
    assert result.spikes[0].isi_ms is None
    assert result.spikes[1].isi_ms == pytest.approx(20)
    assert result.spikes[2].instantaneous_frequency_hz == pytest.approx(25)
    assert result.summary["mean_isi_ms"] == pytest.approx(30)
    assert result.summary["last_over_first_isi"] == pytest.approx(2)
    assert result.summary["isi_cv"] == pytest.approx(np.std([20, 40], ddof=1) / 30)


def test_no_spikes_and_single_spike_undefined_values():
    trace = triangle_trace()
    flat = Trace(trace.time_s, np.full(len(trace.time_s), -65))
    result = analyze(flat, config())
    assert result.summary["spike_count"] == 0
    assert result.summary["firing_rate_hz"] == 0
    assert result.summary["mean_half_width_ms"] is None
    assert result.summary["mean_isi_ms"] is None
    assert analyze(trace, config()).summary["isi_cv"] is None


def test_noise_does_not_generate_spikes():
    t = np.arange(0, 0.2, 0.00002)
    noise = np.random.default_rng(3).normal(-65, 0.5, len(t))
    assert not analyze(Trace(t, noise), config()).spikes


def test_interval_selection_and_exclusion_recompute():
    trace = triangle_trace((0.02, 0.04, 0.08))
    result = analyze(trace, config(start_s=0.03, end_s=0.09))
    assert len(result.spikes) == 2
    excluded = analyze(trace, config(excluded_peak_times_s=(0.04,)))
    assert len(excluded.spikes) == 2
    assert excluded.spikes[1].isi_ms == pytest.approx(60)
    assert excluded.summary["spike_count"] == 2


def test_missing_threshold_remains_missing():
    result = analyze(triangle_trace(), config(dvdt_threshold_mv_ms=500))
    s = result.spikes[0]
    assert s.threshold_mv is None
    assert s.half_width_ms is None
    assert "threshold_not_found" in s.flags
    assert result.summary["n_half_width_ms"] == 0


def test_nonzero_origin_does_not_change_waveform_measurements():
    original = analyze(triangle_trace(), config())
    shifted = analyze(
        triangle_trace(offset=12), AnalysisConfig(baseline_start_s=12, baseline_end_s=12.005)
    )
    assert shifted.spikes[0].half_width_ms == pytest.approx(original.spikes[0].half_width_ms)
    assert shifted.spikes[0].peak_time_s == pytest.approx(12.02)


def test_truncated_ahp_and_partial_spike_are_flagged():
    trace = triangle_trace()
    result = analyze(trace, config(end_s=0.021))
    assert "ahp_window_truncated" in result.spikes[0].flags
    result = analyze(trace, config(end_s=0.0202, prominence_mv=5))
    assert result.spikes[0].half_width_ms is None
    assert "half_width_not_observed" in result.spikes[0].flags


def test_smoothing_records_method_and_preserves_raw():
    trace = triangle_trace()
    raw = trace.voltage_mv.copy()
    result = analyze(trace, config(smoothing_ms=0.1))
    assert len(result.spikes) == 1
    assert result.summary["smoothing_window_samples"] % 2 == 1
    np.testing.assert_array_equal(trace.voltage_mv, raw)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_s": 0.05, "end_s": 0.01},
        {"start_s": -1},
        {"end_s": 1},
        {"baseline_start_s": 0.02, "baseline_end_s": 0.01},
        {"baseline_start_s": 0.001},
        {"smoothing_ms": 1000},
    ],
)
def test_invalid_intervals_raise(kwargs):
    with pytest.raises(ValueError):
        analyze(triangle_trace(), AnalysisConfig(**kwargs))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"refractory_ms": 0},
        {"prominence_mv": -1},
        {"min_peak_mv": np.nan},
        {"dvdt_threshold_mv_ms": np.inf},
        {"smoothing_ms": -1},
    ],
)
def test_invalid_parameters_raise(kwargs):
    with pytest.raises(ValueError):
        AnalysisConfig(**kwargs)


@pytest.mark.parametrize(
    "time,voltage",
    [
        ([0, 1, 2, 3, 3], [1] * 5),
        ([0, 1, 2, 4, 5], [1] * 5),
        ([0, 1, 2, 3, 4], [1, 1, np.nan, 1, 1]),
        ([0, 1, 2, 3, 4], [1, 2]),
    ],
)
def test_invalid_trace_rejected(time, voltage):
    with pytest.raises(ValueError):
        Trace(time, voltage)
