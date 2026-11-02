import csv
import json
from dataclasses import replace

import pytest

from neurospike.analysis import AnalysisConfig, analyze
from neurospike.annotations import create_review_packet, validate_review_packet
from neurospike.cli import main
from neurospike.demo import demo_recording
from neurospike.export import export_bundle


def make_packet(tmp_path):
    # A synthetic source with real bytes for hash/provenance checks, not lab data.
    source = tmp_path / "synthetic-source.txt"
    source.write_text("synthetic fixture: demo_recording()")
    trace = replace(demo_recording().traces[0], source=str(source))
    results = [analyze(trace, AnalysisConfig(min_peak_mv=100))]
    bundle = export_bundle(results, tmp_path / "analysis", sensitivity_review=True)
    packet = create_review_packet(
        [bundle], tmp_path / "review", detection_file=bundle / "detection-review.json"
    )
    return packet, bundle, source


def edit_csv(path, edit):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    edit(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_review_draft_and_labeled_round_trip_does_not_change_analysis(tmp_path):
    packet, bundle, _ = make_packet(tmp_path)
    before = (bundle / "spikes.csv").read_bytes()
    draft = validate_review_packet(packet)
    assert draft["tables"]["sweep"]["labels"] == {"pending": 1}
    assert draft["tables"]["event"]["labels"] == {"pending": 3}
    edit_csv(
        packet / "sweep-labels.csv",
        lambda rows: rows[0].update(
            recording_quality="usable", firing_observation="sustained", annotator="tester"
        ),
    )
    edit_csv(
        packet / "event-labels.csv",
        lambda rows: rows[0].update(event_label="uncertain", annotator="tester"),
    )
    report = validate_review_packet(packet)
    assert report["tables"]["sweep"]["decisive"] == 1
    assert report["tables"]["sweep"]["missing_cell_id"] == 1
    assert report["tables"]["event"]["reviewed"] == 1
    assert report["tables"]["event"]["decisive"] == 0
    assert not report["changes_to_measurements"]
    assert (bundle / "spikes.csv").read_bytes() == before
    assert main(["review-validate", str(packet), "--output", str(tmp_path / "report.json")]) == 0
    assert main(["review-validate", str(packet), "--output", str(tmp_path / "report.json")]) == 2


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda rows: rows[0].update(peak_time_s="0.3"), "Changed identity"),
        (lambda rows: rows.append(dict(rows[0])), "Duplicate or unknown"),
        (lambda rows: rows.pop(), "Missing review rows"),
        (lambda rows: rows[0].update(event_label="automatically_good"), "Unknown event_label"),
        (lambda rows: rows[0].update(event_label="ap"), "annotator"),
        (lambda rows: rows[0].update(event_label="artifact", annotator="a"), "require notes"),
    ],
)
def test_annotation_validation_rejects_wrong_identity_and_incomplete_judgments(
    tmp_path, mutation, match
):
    packet, _, _ = make_packet(tmp_path)
    edit_csv(packet / "event-labels.csv", mutation)
    with pytest.raises(ValueError, match=match):
        validate_review_packet(packet)


def test_source_mutation_and_conflicting_analysis_rejected(tmp_path):
    packet, bundle, source = make_packet(tmp_path)
    with pytest.raises(FileExistsError):
        create_review_packet([bundle], packet)
    with pytest.raises(ValueError, match="Duplicate source"):
        create_review_packet([bundle, bundle], tmp_path / "duplicate")
    source.write_text("changed bytes")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        validate_review_packet(packet)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        create_review_packet([bundle], tmp_path / "changed")


def test_mismatched_sensitivity_and_nonfinite_time_rejected(tmp_path):
    _, bundle, _ = make_packet(tmp_path)
    path = bundle / "detection-review.json"
    data = json.loads(path.read_text())
    data["analyses"][0]["comparisons"]["lower_height_prominence"]["config"]["end_s"] = 0.2
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="configuration/count"):
        create_review_packet([bundle], tmp_path / "mismatch", detection_file=path)
    data["analyses"][0]["comparisons"]["lower_height_prominence"]["config"]["end_s"] = None
    data["analyses"][0]["comparisons"]["lower_height_prominence"][
        "alternative_unmatched_peak_times_s"
    ] = [float("nan")]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="not finite"):
        create_review_packet([bundle], tmp_path / "nan", detection_file=path)


def test_review_without_sensitivity_has_empty_event_table(tmp_path):
    _, bundle, _ = make_packet(tmp_path)
    assert main(["review-create", str(bundle), "--output", str(tmp_path / "sweeps-only")]) == 0
    report = validate_review_packet(tmp_path / "sweeps-only")
    assert report["tables"]["event"]["rows"] == 0
