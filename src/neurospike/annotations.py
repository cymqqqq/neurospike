"""Local, provenance-bound review drafts. Labels never change measurements."""

import csv
import hashlib
import json
import math
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from .export import _sha256, _write_csv

IDENTITY = ["review_id", "source_name", "sweep", "channel", "peak_time_s", "origin"]
SWEEP_FIELDS = [
    "animal_id",
    "cell_id",
    "recording_quality",
    "firing_observation",
    "annotator",
    "notes",
]
EVENT_FIELDS = ["event_label", "annotator", "notes"]
CHOICES = {
    "recording_quality": {"usable", "exclude", "uncertain"},
    "firing_observation": {"sustained", "early_cessation", "no_firing", "uncertain"},
    "event_label": {"ap", "artifact", "other_event", "uncertain"},
}


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def _key(row):
    return row["source"], row["sweep"], row["channel"]


def _verify_sources(sources):
    for source, expected in sources.items():
        if not expected or not Path(source).is_file() or _sha256(Path(source)) != expected:
            raise ValueError(f"Source unavailable or SHA256 mismatch: {source}")


def create_review_packet(bundles, destination, *, detection_file=None):
    """Bind sweep drafts and optional relaxed-only candidates to exported analyses."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("Review directory already exists; choose a new name.")
    analyses, sources, inputs = {}, {}, []
    for bundle in bundles:
        path = Path(bundle).resolve() / "analysis.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        inputs.append({"path": str(path), "sha256": _sha256(path)})
        for source, digest in data["source_sha256"].items():
            if source in sources and sources[source] != digest:
                raise ValueError("Conflicting source hashes.")
            sources[source] = digest
        for row in data["analyses"]:
            key = _key(row)
            if key in analyses:
                raise ValueError(
                    "Duplicate source/sweep/channel; use one analysis window per packet."
                )
            if not sources.get(row["source"]):
                raise ValueError("Review requires a real source file with a SHA256 hash.")
            analyses[key] = {
                **row,
                "method_version": data["method_version"],
                "analysis_code_sha256": data["analysis_code_sha256"],
            }
    if not analyses:
        raise ValueError("No analyses to review.")
    _verify_sources(sources)
    entries = []

    def add(row, kind, peak=None):
        binding = {
            "source_sha256": sources[row["source"]],
            "sweep": row["sweep"],
            "channel": row["channel"],
            "config": row["config"],
            "method_version": row["method_version"],
            "analysis_code_sha256": row["analysis_code_sha256"],
            "kind": kind,
            "peak_time_s": peak,
        }
        identity = {
            "review_id": _digest(binding),
            "source_name": Path(row["source"]).name,
            "sweep": str(row["sweep"]),
            "channel": str(row["channel"]),
            "peak_time_s": "" if peak is None else repr(peak),
            "origin": "sweep" if kind == "sweep" else "lower_height_prominence_unmatched",
        }
        entries.append({"identity": identity, "binding": binding, "source": row["source"]})

    for row in analyses.values():
        add(row, "sweep")
    if detection_file is not None:
        path = Path(detection_file).resolve()
        detection = json.loads(path.read_text(encoding="utf-8"))
        inputs.append({"path": str(path), "sha256": _sha256(path)})
        seen = set()
        for review in detection["analyses"]:
            key = _key(review)
            if key not in analyses or key in seen:
                raise ValueError("Sensitivity rows must match the supplied analyses exactly.")
            seen.add(key)
            if review["status"] != "ok":
                continue
            row = analyses[key]
            alt = review["comparisons"]["lower_height_prominence"]
            if alt["status"] != "ok":
                continue
            expected = dict(row["config"])
            expected.update(
                min_peak_mv=min(expected["min_peak_mv"], -30),
                prominence_mv=min(expected["prominence_mv"], 10),
            )
            if (
                alt["config"] != expected
                or review["original_spike_count"] != row["summary"]["spike_count"]
            ):
                raise ValueError("Sensitivity configuration/count does not match analysis.")
            for peak in alt["alternative_unmatched_peak_times_s"]:
                peak = float(peak)
                if not math.isfinite(peak) or not (
                    row["summary"]["window_start_s"] <= peak < row["summary"]["window_end_s"]
                ):
                    raise ValueError("Candidate time outside analysis window or not finite.")
                add(row, "event", peak)
        if seen != analyses.keys():
            raise ValueError("Sensitivity report is missing analyses.")
    if len({e["identity"]["review_id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate review identity (possibly duplicate source content).")
    manifest = {"schema_version": "1", "sources": sources, "inputs": inputs, "entries": entries}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".review-", dir=destination.parent))
    try:
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        for kind, fields, filename in (
            ("sweep", SWEEP_FIELDS, "sweep-labels.csv"),
            ("event", EVENT_FIELDS, "event-labels.csv"),
        ):
            _write_csv(
                staging / filename,
                [
                    {**e["identity"], **dict.fromkeys(fields, "")}
                    for e in entries
                    if e["binding"]["kind"] == kind
                ],
                IDENTITY + fields,
            )
        (staging / "instructions.txt").write_text(
            "Edit only annotation columns, never identity columns. Blank = pending.\n"
            "recording_quality: usable / exclude / uncertain\n"
            "firing_observation: sustained / early_cessation / no_firing / uncertain\n"
            "event_label: ap / artifact / other_event / uncertain\n"
            "Each judgment needs annotator; exclude/artifact/other_event also need notes.\n"
            "animal_id and cell_id: use real metadata; leave unknown IDs blank.\n"
            "Observations are not diagnoses. No label automatically changes results.\n"
            "Events cover relaxed-only candidates, not complete event ground truth.\n"
            "Do not estimate recall or train a classifier from this packet alone.\n"
            "Run neurospike review-validate PACKET after editing.\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def validate_review_packet(packet):
    """Accept partial drafts, reject mismatched identities; never apply labels."""
    packet = Path(packet)
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != "1":
        raise ValueError("Unsupported review schema.")
    _verify_sources(manifest["sources"])
    entries = manifest["entries"]
    for entry in entries:
        if _digest(entry["binding"]) != entry["identity"]["review_id"]:
            raise ValueError("Review binding/ID mismatch.")
        if manifest["sources"][entry["source"]] != entry["binding"]["source_sha256"]:
            raise ValueError("Review source binding mismatch.")
    if len({e["identity"]["review_id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate manifest identities.")
    report = {
        "schema_version": "1",
        "manifest_sha256": _sha256(packet / "manifest.json"),
        "source_hashes_verified": True,
        "changes_to_measurements": False,
        "interpretation": "Coverage of this review packet only, not detector accuracy or ML benefit.",
        "tables": {},
    }
    for kind, fields, filename, judgment in (
        ("sweep", SWEEP_FIELDS, "sweep-labels.csv", "recording_quality"),
        ("event", EVENT_FIELDS, "event-labels.csv", "event_label"),
    ):
        expected = {
            e["identity"]["review_id"]: e["identity"]
            for e in entries
            if e["binding"]["kind"] == kind
        }
        seen, counts, observations = set(), Counter(), Counter()
        missing_cell = missing_animal = 0
        with (packet / filename).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != IDENTITY + fields:
                raise ValueError(f"Unexpected columns in {filename}.")
            for row in reader:
                rid = row.get("review_id")
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"Malformed CSV row in {filename}.")
                if rid in seen or rid not in expected:
                    raise ValueError(f"Duplicate or unknown review ID in {filename}.")
                seen.add(rid)
                for name in IDENTITY:
                    # Export escapes spreadsheet formula prefixes in source names.
                    value = expected[rid][name]
                    if value.startswith(("=", "+", "-", "@")):
                        value = "'" + value
                    if row[name] != value:
                        raise ValueError(f"Changed identity {name} in {filename}.")
                labels = {name: row[name].strip() for name in fields}
                for name in fields:
                    if name in CHOICES and labels[name] and labels[name] not in CHOICES[name]:
                        raise ValueError(f"Unknown {name}: {labels[name]}")
                if any(labels.get(name) for name in CHOICES) and not labels["annotator"]:
                    raise ValueError("Judgments require an annotator.")
                if (
                    labels[judgment] in {"exclude", "artifact", "other_event"}
                    and not labels["notes"]
                ):
                    raise ValueError("Exclusion/artifact/other_event judgments require notes.")
                counts[labels[judgment] or "pending"] += 1
                if kind == "sweep":
                    observations[labels["firing_observation"] or "pending"] += 1
                    missing_cell += not labels["cell_id"]
                    missing_animal += not labels["animal_id"]
        if seen != expected.keys():
            raise ValueError(f"Missing review rows in {filename}.")
        report["tables"][kind] = {
            "rows": len(seen),
            "labels": dict(counts),
            "reviewed": len(seen) - counts["pending"],
            "decisive": len(seen) - counts["pending"] - counts["uncertain"],
            "csv_sha256": _sha256(packet / filename),
        }
        if kind == "sweep":
            report["tables"][kind].update(
                firing_observations=dict(observations),
                missing_cell_id=missing_cell,
                missing_animal_id=missing_animal,
            )
    return report
