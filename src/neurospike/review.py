"""Optional detection sensitivity checks; alternatives are not ground truth."""

from dataclasses import asdict, replace

import numpy as np

from .analysis import analyze


def detection_review(results):
    """Compare presets without replacing accepted events or biological interpretation."""
    rows = []
    for result in results:
        cfg = result.config
        # Exclusions encode a particular detector's sampled peak times. Matching
        # those times after filtering is ambiguous; do not silently reapply them.
        if cfg.excluded_peak_times_s:
            rows.append(
                {
                    "source": result.trace.source,
                    "sweep": result.trace.sweep,
                    "channel": result.trace.channel,
                    "status": "skipped_manual_exclusions",
                    "reason": "Review manually excluded events before comparing changed detectors.",
                }
            )
            continue
        variants = {
            "lower_height_prominence": replace(
                cfg,
                min_peak_mv=min(cfg.min_peak_mv, -30),
                prominence_mv=min(cfg.prominence_mv, 10),
            ),
            "savgol_0_15_ms": replace(cfg, smoothing_ms=0.15),
        }
        original = np.array([s.peak_time_s for s in result.spikes])
        comparisons = {}
        for name, alternative in variants.items():
            try:
                other = analyze(result.trace, alternative)
            except ValueError as exc:
                comparisons[name] = {
                    "status": "failed",
                    "error": str(exc),
                    "config": asdict(alternative),
                }
                continue
            candidates = np.array([s.peak_time_s for s in other.spikes])
            # A descriptive nearest-peak check, not precision/recall. Neither set
            # has manual truth labels. A two-sample tolerance accommodates shifts.
            tolerance = 2 * result.trace.dt_s
            unmatched = [
                float(x) for x in candidates if not np.any(np.abs(original - x) <= tolerance)
            ]
            lost = [float(x) for x in original if not np.any(np.abs(candidates - x) <= tolerance)]
            comparisons[name] = {
                "status": "ok",
                "config": asdict(alternative),
                "spike_count": len(candidates),
                "count_difference": len(candidates) - len(original),
                "alternative_unmatched_peak_times_s": unmatched,
                "original_unmatched_peak_times_s": lost,
                "matching_tolerance_s": tolerance,
            }
        rows.append(
            {
                "source": result.trace.source,
                "sweep": result.trace.sweep,
                "channel": result.trace.channel,
                "status": "ok",
                "original_spike_count": len(original),
                "comparisons": comparisons,
            }
        )
    return {
        "review_version": "1",
        "interpretation": "Sensitivity only: alternatives are not manual truth, accuracy "
        "estimates or automatic corrections. No events are added or removed from the main export.",
        "analyses": rows,
    }
