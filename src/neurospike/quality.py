"""Experimental sweep review prioritization; never corrects physiological measurements."""

import hashlib
import json
from collections import defaultdict

import numpy as np
from scipy.signal import find_peaks

FEATURES = (
    "baseline_deviation_within_source_mv",
    "baseline_iqr_mv",
    "baseline_candidate_count",
    "tail_elevation_from_baseline_mv",
    "terminal_silence_fraction",
    "extra_candidate_fraction",
    "missing_shape_fraction",
)


def quality_review(results, sensitivity, *, machine_learning=False):
    """Review a comparable-window batch; model scores are relative, not probabilities.

    Fixed review heuristics and unsupervised scores are separate. In-sample
    ranking is transductive exploration. There is no labeled training or test set.
    """
    if not results:
        raise ValueError("Quality review requires at least one analysis.")
    if len(sensitivity["analyses"]) != len(results):
        raise ValueError("Sensitivity rows must match analyses in order.")
    baselines = defaultdict(list)
    for r in results:
        baselines[(r.trace.source, r.trace.channel)].append(r.summary["baseline_mv"])
    centers = {k: float(np.median(v)) for k, v in baselines.items()}
    rows = []
    for r, comparison in zip(results, sensitivity["analyses"], strict=True):
        tr, sm = r.trace, r.summary
        if (comparison["source"], comparison["sweep"], comparison["channel"]) != (
            tr.source,
            tr.sweep,
            tr.channel,
        ):
            raise ValueError("Sensitivity identity does not match analysis.")
        start, end = sm["window_start_s"], sm["window_end_s"]
        duration = end - start
        bm = (tr.time_s >= sm["baseline_start_s"]) & (tr.time_s < sm["baseline_end_s"])
        bv = tr.voltage_mv[bm]
        peaks, _ = find_peaks(
            bv,
            height=r.config.min_peak_mv,
            prominence=r.config.prominence_mv,
            distance=max(1, int(np.ceil(r.config.refractory_ms / (tr.dt_s * 1000)))),
        )
        tail = tr.voltage_mv[(tr.time_s >= end - 0.2 * duration) & (tr.time_s <= end)]
        silence = (end - r.spikes[-1].peak_time_s) / duration if len(r.spikes) >= 3 else 0.0
        alternative = comparison.get("comparisons", {}).get("lower_height_prominence", {})
        extra = len(alternative.get("alternative_unmatched_peak_times_s", []))
        missing = sum(s.threshold_mv is None or s.half_width_ms is None for s in r.spikes)
        features = {
            "baseline_deviation_within_source_mv": abs(
                sm["baseline_mv"] - centers[(tr.source, tr.channel)]
            ),
            "baseline_iqr_mv": float(np.subtract(*np.percentile(bv, [75, 25]))),
            "baseline_candidate_count": int(len(peaks)),
            "tail_elevation_from_baseline_mv": float(np.median(tail) - sm["baseline_mv"]),
            "terminal_silence_fraction": float(silence),
            "extra_candidate_fraction": extra / max(1, len(r.spikes)),
            "missing_shape_fraction": missing / max(1, len(r.spikes)),
        }
        flags = []
        if features["baseline_deviation_within_source_mv"] > 10:
            flags.append("baseline_shift_review")
        if len(peaks):
            flags.append("baseline_contains_candidates")
        if silence > 0.4 and features["tail_elevation_from_baseline_mv"] > 15:
            flags.append("early_firing_cessation_with_depolarized_tail")
        if features["extra_candidate_fraction"] > 0.2:
            flags.append("detector_disagreement")
        rows.append(
            {
                "source": tr.source,
                "sweep": tr.sweep,
                "channel": tr.channel,
                "window_start_s": start,
                "window_end_s": end,
                "spike_count": len(r.spikes),
                "features": features,
                "review_flags": flags,
                "sensitivity_status": comparison["status"],
                "sensitivity_available": alternative.get("status") == "ok",
            }
        )
    info = {
        "quality_review_version": "1",
        "interpretation": "Review cues, not diagnoses or exclusion rules. No changes to events "
        "or measurements. Compare only compatible protocols/windows; no independent labels.",
        "feature_order": list(FEATURES),
        "feature_notes": {
            "baseline_reference": "Median baseline across supplied sweeps within source/channel; "
            "depends on batch composition and cannot detect a uniformly shifted recording.",
            "tail": "Median raw voltage in final 20% of selected window minus raw baseline.",
            "silence": "Fraction after last retained peak, only if >=3 peaks; otherwise zero "
            "(not applicable), never a diagnosis of depolarization block.",
            "sensitivity": "Unmatched relaxed-detector peaks / max(1, primary count); zero "
            "placeholder if unavailable. ML abstains for unavailable sensitivity rows.",
            "missing": "Fraction with missing threshold or width; zero for no events.",
        },
        "heuristics": {
            "baseline_shift_mv": 10,
            "terminal_silence_fraction": 0.4,
            "tail_elevation_mv": 15,
            "extra_candidate_fraction": 0.2,
        },
        "analyses": rows,
        "machine_learning": {"status": "disabled"},
    }
    if not machine_learning:
        return info
    eligible = [i for i, row in enumerate(rows) if row["sensitivity_available"]]
    if len(eligible) < 20:
        info["machine_learning"] = {"status": "insufficient_eligible_sweeps", "minimum": 20}
        return info
    from sklearn import __version__ as sklearn_version
    from sklearn.ensemble import IsolationForest

    matrix = np.array([[rows[i]["features"][k] for k in FEATURES] for i in eligible])
    if not np.isfinite(matrix).all():
        raise ValueError("Quality features must be finite.")
    if np.unique(matrix, axis=0).shape[0] < 5:
        info["machine_learning"] = {"status": "insufficient_feature_variation"}
        return info
    parameters = {
        "n_estimators": 200,
        "max_samples": min(256, len(matrix)),
        "contamination": "auto",
        "random_state": 0,
        "n_jobs": 1,
    }
    model = IsolationForest(**parameters).fit(matrix)
    scores = -model.score_samples(matrix)
    for index, score in zip(eligible, scores, strict=True):
        rows[index]["ml_atypicality_score"] = float(score)
    for rank, pos in enumerate(np.argsort(-scores, kind="stable"), 1):
        rows[eligible[int(pos)]]["ml_review_rank"] = rank
    info["machine_learning"] = {
        "status": "exploratory_in_sample_ranking",
        "algorithm": "IsolationForest",
        "sklearn_version": sklearn_version,
        "parameters": parameters,
        "eligible_sweeps": len(eligible),
        "feature_matrix_sha256": hashlib.sha256(
            json.dumps(matrix.tolist(), separators=(",", ":")).encode()
        ).hexdigest(),
        "validation": "No labeled validation. Scores are not failure probabilities; "
        "contamination does not designate a fraction to delete. Do not compare scores "
        "across separately fitted batches. No persisted pickle model or external data upload.",
    }
    return info
