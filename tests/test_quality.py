from dataclasses import replace

import numpy as np
import pytest

from neurospike.analysis import AnalysisConfig, analyze
from neurospike.demo import demo_recording
from neurospike.models import Trace
from neurospike.quality import quality_review
from neurospike.review import detection_review


def test_review_flags_do_not_delete_early_firing_or_shifted_sweeps():
    trace = demo_recording().traces[0]
    results = [analyze(replace(trace, sweep=i)) for i in range(5)]
    shifted = analyze(replace(trace, sweep=5, voltage_mv=trace.voltage_mv + 20))
    results.append(shifted)
    report = quality_review(results, detection_review(results))
    assert "baseline_shift_review" in report["analyses"][-1]["review_flags"]
    assert len(shifted.spikes) == 3
    t = np.arange(0, 1, 0.00005)
    v = np.full(len(t), -65.0)
    v[(t >= 0.1) & (t <= 0.8)] = -30
    for peak in [0.13, 0.16, 0.19]:
        v += np.interp(t, [peak - 0.001, peak, peak + 0.001], [0, 70, 0], left=0, right=0)
    r = analyze(
        Trace(t, v), AnalysisConfig(start_s=0.1, end_s=0.8, baseline_start_s=0, baseline_end_s=0.08)
    )
    row = quality_review([r], detection_review([r]))["analyses"][0]
    assert "early_firing_cessation_with_depolarized_tail" in row["review_flags"]
    assert row["features"]["terminal_silence_fraction"] > 0.8
    assert len(r.spikes) == 3


def test_ml_abstains_without_enough_sweeps_or_with_exclusions():
    r = analyze(demo_recording().traces[0])
    report = quality_review([r], detection_review([r]), machine_learning=True)
    assert report["machine_learning"]["status"] == "insufficient_eligible_sweeps"
    assert "ml_review_rank" not in report["analyses"][0]
    excluded = analyze(r.trace, AnalysisConfig(excluded_peak_times_s=(0.1,)))
    row = quality_review([excluded], detection_review([excluded]))["analyses"][0]
    assert not row["sensitivity_available"]
    with pytest.raises(ValueError, match="identity"):
        quality_review([r], detection_review([replace(r, trace=replace(r.trace, sweep=9))]))


def test_ml_ranking_is_reproducible_and_records_model_provenance():
    pytest.importorskip("sklearn")
    tr = demo_recording().traces[0]
    results = [analyze(replace(tr, sweep=i, voltage_mv=tr.voltage_mv + i * 0.1)) for i in range(24)]
    results.append(analyze(replace(tr, sweep=24, voltage_mv=tr.voltage_mv + 30)))
    sensitivity = detection_review(results)
    first = quality_review(results, sensitivity, machine_learning=True)
    second = quality_review(results, sensitivity, machine_learning=True)
    assert first == second
    assert first["machine_learning"]["eligible_sweeps"] == 25
    assert len(first["machine_learning"]["feature_matrix_sha256"]) == 64
    ranks = [row["ml_review_rank"] for row in first["analyses"]]
    assert sorted(ranks) == list(range(1, 26))
    assert ranks[-1] <= 3  # Deliberately extreme synthetic shift should merit review.
    assert all(len(r.spikes) == 3 for r in results)


def test_cli_optional_ml_exports_review_without_claiming_small_batch_fit(tmp_path):
    import json

    from neurospike.cli import main

    assert main(["demo", "--ml-review", "--output", str(tmp_path / "review")]) == 0
    metadata = json.loads((tmp_path / "review/analysis.json").read_text())
    review = json.loads((tmp_path / "review/quality-review.json").read_text())
    assert metadata["quality_review_file"] == "quality-review.json"
    assert metadata["detection_review_file"] == "detection-review.json"
    assert review["machine_learning"]["status"] == "insufficient_eligible_sweeps"
    assert [a["summary"]["spike_count"] for a in metadata["analyses"]] == [3, 5]
