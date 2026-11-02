"""Auditable definitions of ap-dvdt-1; references are comparators, not certification."""

from copy import deepcopy

METHOD_VERSION = "ap-dvdt-1"
REGISTRY_VERSION = "1"

IPFX_COMMIT = "c607a36e25618a6bb8ba5438c1cd945fb429e659"
EFEL_COMMIT = "1b6c129dd0de1e782ee70777a92d642898af28b5"
REFERENCES = {
    "gouwens2019": {
        "title": "Classification of electrophysiological and morphological neuron types "
        "in the mouse visual cortex",
        "doi": "10.1038/s41593-019-0417-0",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8078853/",
        "locator": "Methods: electrophysiological feature analysis",
        "evidence": "full_text",
    },
    "ipfx_detector": {
        "url": f"https://github.com/AllenInstitute/ipfx/blob/{IPFX_COMMIT}/ipfx/spike_detector.py",
        "locator": "detect_putative_spikes; refine_threshold_indexes; find_upstroke_indexes; find_downstroke_indexes",
        "evidence": "pinned_source",
    },
    "ipfx_shape": {
        "url": f"https://github.com/AllenInstitute/ipfx/blob/{IPFX_COMMIT}/ipfx/spike_features.py",
        "locator": "find_widths; analyze_trough_details",
        "evidence": "pinned_source",
    },
    "ipfx_train": {
        "url": f"https://github.com/AllenInstitute/ipfx/blob/{IPFX_COMMIT}/ipfx/spike_train_features.py",
        "locator": "basic_spike_train_features; average_rate; latency; norm_diff",
        "evidence": "pinned_source",
    },
    "efel": {
        "url": f"https://github.com/BlueBrain/eFEL/blob/{EFEL_COMMIT}/docs/source/eFeatures.rst",
        "locator": "AP_amplitude; AP_duration_half_width; AHP_depth; ISI_CV",
        "evidence": "pinned_documentation",
    },
    "efel_train": {
        "url": f"https://github.com/BlueBrain/eFEL/blob/{EFEL_COMMIT}/efel/cppcore/SpikeEvent.cpp",
        "locator": "firing_rate; __adaptation_index",
        "evidence": "pinned_source",
    },
    "lazic2010": {
        "title": "The problem of pseudoreplication in neuroscientific studies: "
        "is it affecting your analysis?",
        "doi": "10.1186/1471-2202-11-5",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC2817684/",
        "locator": "Introduction; hierarchically organised data; solutions",
        "evidence": "full_text",
    },
}


def _metric(unit, definition, comparison, *references):
    return {
        "unit": unit,
        "definition": definition,
        "comparison": comparison,
        "references": list(references),
        "review_status": "implementation_reviewed; laboratory_validation_pending",
    }


METRICS = {
    "peak_time_s": _metric(
        "s",
        "Timestamp of retained sampled local maximum; no peak fitting.",
        "Detection and filtering affect which peak is retained.",
        "gouwens2019",
    ),
    "peak_mv": _metric(
        "mV",
        "Processed voltage at retained peak sample.",
        "Absolute potential, without liquid junction potential correction.",
        "gouwens2019",
    ),
    "threshold_time_s": _metric(
        "s",
        "Last upward fixed dV/dt crossing before maximal upstroke in lookback; "
        "linear time interpolation; bounded by analysis start and previous retained peak.",
        "Not Allen/IPFX 5%-of-mean-upstroke refinement.",
        "gouwens2019",
        "ipfx_detector",
    ),
    "threshold_mv": _metric(
        "mV",
        "Voltage linearly interpolated at threshold_time_s.",
        "Fixed dV/dt onset differs from IPFX refined onset.",
        "gouwens2019",
        "ipfx_detector",
    ),
    "amplitude_mv": _metric(
        "mV",
        "peak_mv - threshold_mv; unavailable if threshold missing.",
        "Same reference family as eFEL AP_amplitude; onset may differ.",
        "efel",
    ),
    "half_width_ms": _metric(
        "ms",
        "Time between last rising and first falling crossings of "
        "(peak_mv + threshold_mv)/2; linear interpolation; falling search ends at AHP stop.",
        "eFEL onset-reference family; IPFX uses trough-reference half-height with fallback.",
        "efel",
        "ipfx_shape",
        "gouwens2019",
    ),
    "rise_time_ms": _metric(
        "ms",
        "1000 * (peak_time_s - threshold_time_s).",
        "Not a 10-90% rise time; onset method must match.",
        "efel",
    ),
    "max_upstroke_mv_ms": _metric(
        "mV/ms",
        "Maximum numpy.gradient(processed_voltage, time_ms) from first sample "
        "at/after threshold through peak.",
        "Derivative/filtering and segment endpoints matter.",
        "gouwens2019",
        "ipfx_shape",
    ),
    "max_downstroke_mv_ms": _metric(
        "mV/ms",
        "Minimum gradient from peak through sampled AHP trough; retain negative sign.",
        "Do not compare with absolute downstroke magnitudes without sign conversion.",
        "ipfx_shape",
    ),
    "ahp_trough_time_s": _metric(
        "s",
        "Timestamp of minimum processed voltage from peak to configurable AHP stop; "
        "stop bounded by analysis end and before next retained onset (or peak if onset missing).",
        "Window minimum is not a separated fast/medium/slow AHP component.",
        "efel",
        "ipfx_shape",
    ),
    "ahp_trough_mv": _metric(
        "mV",
        "Minimum processed voltage in the AHP search segment, including the peak.",
        "Window selection differs from eFEL/IPFX trough rules.",
        "efel",
        "ipfx_shape",
    ),
    "ahp_depth_from_threshold_mv": _metric(
        "mV",
        "threshold_mv - ahp_trough_mv; positive means below onset voltage.",
        "Reference voltage and AHP segment must match before comparison.",
        "efel",
    ),
    "ahp_depth_from_baseline_mv": _metric(
        "mV",
        "baseline_mv - ahp_trough_mv; positive means below baseline; negative allowed.",
        "Opposite sign to eFEL AHP_depth for identical baseline and trough.",
        "efel",
    ),
    "isi_ms": _metric(
        "ms",
        "1000 * difference between consecutive retained peak timestamps; first is missing.",
        "IPFX uses threshold timestamps. Exclusions change intervals.",
        "ipfx_train",
        "efel",
    ),
    "instantaneous_frequency_hz": _metric(
        "Hz",
        "1000 / isi_ms; attached to the later peak.",
        "Its mean is not count divided by window duration.",
        "ipfx_train",
    ),
    "baseline_mv": _metric(
        "mV",
        "Median raw voltage in [baseline_start_s, baseline_end_s); "
        "automatic fallback and effective interval recorded in summary.",
        "Not automatically a resting membrane potential.",
        "efel",
    ),
    "spike_count": _metric(
        "count",
        "Number of retained peaks after explicit exclusions; flagged events included.",
        "Peak height/prominence/distance detector is not the Allen detection pipeline.",
        "gouwens2019",
        "ipfx_detector",
    ),
    "firing_rate_hz": _metric(
        "Hz",
        "spike_count / (window_end_s - window_start_s); zero if no peaks.",
        "Same full-window denominator family as IPFX average_rate; eFEL mean_frequency "
        "ends at last spike.",
        "ipfx_train",
        "efel_train",
    ),
    "first_peak_latency_ms": _metric(
        "ms",
        "1000 * (first retained peak timestamp - window_start_s); missing if no peak.",
        "Not threshold latency; stimulus onset is not automatically detected.",
        "ipfx_train",
    ),
    "mean_isi_ms": _metric(
        "ms",
        "Arithmetic mean of all retained peak-to-peak ISIs; missing with fewer than 2 peaks.",
        "Specify inclusion of first ISI and peak/threshold timing.",
        "efel",
        "ipfx_train",
    ),
    "isi_cv": _metric(
        "dimensionless",
        "Sample SD (ddof=1) / mean of all ISIs, including first; "
        "requires at least 2 ISIs (3 peaks).",
        "eFEL ISI_CV excludes first ISI by default unless ignore_first_ISI=0.",
        "efel",
    ),
    "last_over_first_isi": _metric(
        "dimensionless",
        "Last ISI / first ISI; requires at least 2 ISIs (3 peaks).",
        "Not normalized consecutive-ISI adaptation_index in IPFX/eFEL.",
        "ipfx_train",
        "efel_train",
    ),
    "flagged_spike_count": _metric(
        "count",
        "Number of retained peaks with at least one quality flag.",
        "A quality flag does not automatically exclude an event.",
    ),
}

for _key in (
    "threshold_mv",
    "amplitude_mv",
    "half_width_ms",
    "max_upstroke_mv_ms",
    "max_downstroke_mv_ms",
    "ahp_depth_from_threshold_mv",
    "ahp_depth_from_baseline_mv",
):
    METRICS["mean_" + _key] = _metric(
        METRICS[_key]["unit"],
        f"Arithmetic mean of available {_key} within one sweep; "
        "missing values ignored; flagged events included unless explicitly excluded.",
        "Descriptive event-level mean, not a cell/animal/group inference.",
        "lazic2010",
    )
    METRICS["n_" + _key] = _metric(
        "count",
        f"Number of non-missing {_key} values used in the sweep mean.",
        "Measurement count is not independent biological sample size.",
        "lazic2010",
    )


def method_manifest():
    """Return an independent, JSON-safe manifest bundled with each result export."""
    return deepcopy(
        {
            "registry_version": REGISTRY_VERSION,
            "method_version": METHOD_VERSION,
            "scope": "Current-clamp voltage; literature/source audit, not experimental validation.",
            "metrics": METRICS,
            "references": REFERENCES,
            "implementation": {
                "voltage": "Raw by default; optional Savitzky-Golay order 3, odd window >=5 samples. "
                "Actual window_samples in summary; raw median baseline regardless of smoothing.",
                "detection": "scipy.signal.find_peaks on selected closed interval; endpoints not "
                "peaks; configurable height/prominence/ceil(distance_ms/dt_ms); exclusions within dt/2.",
                "parameters": "Effective config, baseline/window endpoints and smoothing samples "
                "are stored for each analysis; defaults are not universal physiological standards.",
                "missing": "JSON null / CSV blank means unavailable, never zero imputation.",
            },
        }
    )
