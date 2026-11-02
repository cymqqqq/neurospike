import csv
import hashlib
import json
from dataclasses import fields
from pathlib import Path

import numpy as np
import pyabf
import pytest
from pyabf.abfWriter import writeABF1

from neurospike.analysis import AnalysisConfig, Spike, analyze
from neurospike.cli import main
from neurospike.demo import demo_recording
from neurospike.export import export_bundle
from neurospike.io import abf_channels, load_recording
from neurospike.methods import method_manifest


def test_real_abf_binary_round_trip_with_scaling_and_sweeps(tmp_path):
    recording = demo_recording()
    path = tmp_path / "known.abf"
    data = np.stack([trace.voltage_mv for trace in recording.traces])
    writeABF1(data, str(path), sampleRateHz=50000, units="mV")
    loaded = load_recording(path)
    assert len(loaded.traces) == 2
    assert abf_channels(path)[0]["unit"] == "mV"
    for expected, actual in zip(recording.traces, loaded.traces, strict=True):
        np.testing.assert_allclose(actual.voltage_mv, expected.voltage_mv, atol=0.02)
        assert actual.dt_s == pytest.approx(expected.dt_s)
    assert [len(analyze(t).spikes) for t in loaded.traces] == [3, 5]
    assert pyabf.ABF(str(path)).abfVersion["major"] == 1


def test_voltage_clamp_channel_rejected(tmp_path):
    path = tmp_path / "current.abf"
    writeABF1(np.zeros((1, 10000)), str(path), sampleRateHz=20000, units="pA")
    with pytest.raises(ValueError, match="电压通道"):
        load_recording(path)


def test_csv_units_multiple_sweeps_and_source_hash(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        "time_ms,first_V,second_uV\n" + "\n".join(f"{i},-0.065,-65000" for i in range(10)),
        encoding="utf-8",
    )
    recording = load_recording(path)
    assert len(recording.traces) == 2
    for trace in recording.traces:
        np.testing.assert_allclose(trace.voltage_mv, -65)
        assert trace.dt_s == pytest.approx(0.001)
    result = analyze(recording.traces[0], AnalysisConfig(baseline_start_s=0, baseline_end_s=0.005))
    output = export_bundle([result], tmp_path / "export")
    metadata = json.loads((output / "analysis.json").read_text())
    assert (
        metadata["source_sha256"][str(path.resolve())]
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert metadata["analyses"][0]["summary"]["spike_count"] == 0
    with (output / "spikes.csv").open(encoding="utf-8-sig") as f:
        assert list(csv.DictReader(f)) == []
    assert (output / "review.png").stat().st_size > 1000


@pytest.mark.parametrize(
    "text",
    [
        "time,voltage\n" + "\n".join(f"{i},-65" for i in range(10)),
        "time_s,v_mV\n0,-65\n1,-65\n2,nan\n3,-65\n4,-65",
        "time_s,v_mV\n0,-65\n1,-65\n2,-65,9\n3,-65\n4,-65",
    ],
)
def test_bad_csv_rejected(tmp_path, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_recording(path)


def test_explicit_csv_units_and_tab_delimiter(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("time\tvoltage\n" + "\n".join(f"{i}\t-65" for i in range(10)))
    recording = load_recording(path, time_unit="ms", voltage_unit="mv")
    assert recording.traces[0].dt_s == pytest.approx(0.001)


def test_export_no_overwrite_and_records_manual_exclusion(tmp_path):
    trace = demo_recording().traces[0]
    initial = analyze(trace)
    result = analyze(trace, AnalysisConfig(excluded_peak_times_s=(initial.spikes[1].peak_time_s,)))
    output = export_bundle([result], tmp_path / "export")
    metadata = json.loads((output / "analysis.json").read_text())
    assert metadata["analyses"][0]["config"]["excluded_peak_times_s"]
    with (output / "spikes.csv").open(encoding="utf-8-sig") as f:
        assert len(list(csv.DictReader(f))) == 2
    with pytest.raises(FileExistsError):
        export_bundle([result], output)


def test_export_carries_complete_method_audit_and_actual_nondefault_settings(tmp_path):
    cfg = AnalysisConfig(
        start_s=0.05,
        end_s=0.4,
        baseline_start_s=0,
        baseline_end_s=0.04,
        dvdt_threshold_mv_ms=15,
        ahp_window_ms=12,
        smoothing_ms=0.1,
    )
    result = analyze(demo_recording().traces[0], cfg)
    output = export_bundle([result], tmp_path / "audited")
    metadata = json.loads((output / "analysis.json").read_text())
    manifest = metadata["method_manifest"]
    assert metadata["method_version"] == manifest["method_version"] == "ap-dvdt-1"
    provenance = {"source", "sweep", "channel", "spike_number", "flags"}
    for field in fields(Spike):
        if field.name not in provenance:
            assert field.name in manifest["metrics"]
    for name in result.summary:
        if name.startswith(("mean_", "n_")) or name in (
            "spike_count",
            "firing_rate_hz",
            "first_peak_latency_ms",
            "isi_cv",
            "last_over_first_isi",
            "baseline_mv",
            "flagged_spike_count",
        ):
            assert name in manifest["metrics"]
    for metric in manifest["metrics"].values():
        assert metric["definition"] and metric["unit"]
        for ref in metric["references"]:
            assert manifest["references"][ref]["url"].startswith("https://")
    saved = metadata["analyses"][0]
    assert saved["config"]["dvdt_threshold_mv_ms"] == 15
    assert saved["config"]["ahp_window_ms"] == 12
    assert saved["summary"]["smoothing_window_samples"] > 0
    import neurospike.analysis

    assert (
        metadata["analysis_code_sha256"]
        == hashlib.sha256(Path(neurospike.analysis.__file__).read_bytes()).hexdigest()
    )
    # Callers must not be able to contaminate later exports by editing a manifest.
    manifest = method_manifest()
    manifest["metrics"]["isi_cv"]["unit"] = "corrupted"
    assert method_manifest()["metrics"]["isi_cv"]["unit"] == "dimensionless"


def test_cli_end_to_end_and_error_status(tmp_path):
    assert main(["demo", "--output", str(tmp_path / "demo")]) == 0
    metadata = json.loads((tmp_path / "demo" / "analysis.json").read_text())
    assert [a["summary"]["spike_count"] for a in metadata["analyses"]] == [3, 5]
    assert main(["analyze", str(tmp_path / "missing.abf"), "--output", str(tmp_path / "bad")]) == 2


def test_csv_formula_injection_guard(tmp_path):
    path = tmp_path / "=unsafe.csv"
    path.write_text("time_s,=label_mV\n" + "\n".join(f"{i / 1000},-65" for i in range(10)))
    result = analyze(load_recording(path).traces[0])
    output = export_bundle([result], tmp_path / "safe")
    with (output / "sweeps.csv").open(encoding="utf-8-sig") as f:
        assert next(csv.DictReader(f))["label"] == "'=label_mV"
