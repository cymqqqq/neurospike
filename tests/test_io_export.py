import csv
import hashlib
import json

import numpy as np
import pyabf
import pytest
from pyabf.abfWriter import writeABF1

from neurospike.analysis import AnalysisConfig, analyze
from neurospike.cli import main
from neurospike.demo import demo_recording
from neurospike.export import export_bundle
from neurospike.io import abf_channels, load_recording


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
