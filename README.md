# NeuroSpike

**English** | [简体中文](README.zh-CN.md)

Python action-potential analysis for current-clamp recordings, including evoked and spontaneous firing. NeuroSpike reads pCLAMP ABF files and produces measurements, quality flags, reproducibility metadata, and review plots.

## Recommended workflow: provide data, receive analysis results

Provide your recording files or accessible file paths and describe the measurements you need. An AI coding agent can use this repository's Python analysis code to inspect the data, run the calculation, review quality, and return the requested results. You do not need to write code, install Python, or open a desktop application when the agent handles execution in an environment with access to the files and repository.

This repository supplies the calculation code. It does not include a hosted chat service, file-upload website, or autonomous AI backend. Repository access alone does not give an agent access to your experimental files. The agent needs an execution environment and access to the data you provide.

For the configured Codex workflow, use the separately installed personal `$software-engineer` skill. That skill is not bundled with this repository. A typical request is:

```text
Use the neurospike Python code to analyze the attached ABF recordings.
Measure spike count, firing rate, threshold, amplitude, half-width,
maximum upstroke/downstroke rates, and AHP depth.
Analyze 0.1–0.6 s and use 0–0.05 s as the baseline.
Return the result tables, necessary waveform review plots, and a short explanation.
Keep the Qt interface unchanged.
```

The time windows above are examples; choose them according to the experiment. If the stimulus interval or baseline is unknown, ask the agent to inspect the recording and available metadata first. Supply cell/animal identifiers and group assignments when requesting aggregation across recordings.

The agent should use actual Python output for numerical results, record the code version and parameters, report failed inputs and uncertain measurements, and avoid treating multiple sweeps from one cell as independent biological replicates. Experimental data and analysis outputs are not uploaded to GitHub by default. Data handling by the surrounding AI platform depends on that platform and execution environment.

## Project status

The current priority is the Python analysis core, command-line interface, and analysis scripts. The existing Qt/PySide6 desktop interface is retained; further UI feature development and routine manual application packaging are paused until explicitly requested. The existing CI tests and macOS packaging workflow remain in place and can still produce application artifacts on pushes.

This documentation update does not change the analysis algorithm or remove desktop functionality.

## Available analysis

- Read ABF1 and ABF2 recordings, select a voltage channel, and analyze individual or multiple sweeps. CSV, TSV, and header-based TXT files are also supported.
- Measure spike count, interval firing rate, peak time/voltage, dV/dt threshold, threshold-to-peak amplitude, half-width, threshold-to-peak rise time, maximum upstroke/downstroke rates, and AHP trough time/voltage/depth.
- Report interspike intervals (ISI), instantaneous frequency, ISI coefficient of variation, and the last/first ISI ratio.
- Export per-spike and per-sweep CSV files, JSON analysis metadata with source-file hashes, and a PNG overview.
- Retain quality flags and missing values when a measurement cannot be reliably determined. The Python API supports explicit exclusion of detected peaks; the retained Qt interface also provides exclusion controls.

Default detection settings are a minimum peak of −20 mV, prominence of 20 mV, dV/dt threshold of 20 mV/ms, and minimum peak separation of 2 ms. Smoothing is disabled by default. These settings require review for the recorded cell type and protocol.

## Results and interpretation

- `spikes.csv`: one row per retained event. Empty values mean unavailable measurements, not zero. Quality flags do not automatically exclude events.
- `sweeps.csv`: one row per analyzed sweep, with analysis windows, baseline, counts, firing rate, metric means, and valid measurement counts.
- `analysis.json`: software/method/dependency versions, parameters, excluded peak times, warnings, summaries, and source-file SHA256 hashes. It contains local paths; review these before sharing.
- `review.png`: an overview of at most the first 12 analyzed sweeps. The CSV files contain all analyzed sweeps. Long traces use extrema-preserving downsampling; the overview does not replace detailed waveform review.

The built-in export records software and method versions, but not the Git commit. For reproducible agent-run analyses, also save the repository commit, relevant uncommitted changes or script snapshot, environment, and execution details with the results.

Half-width is measured halfway between the dV/dt threshold voltage and peak voltage. AHP depth is reported relative to both threshold and baseline. First-peak latency is measured from the selected analysis start, not an automatically detected stimulus onset. See the [measurement definitions (Chinese)](docs/measurement-definitions.md) for the full method.

## Python execution reference

These commands are for the agent or developers running the analysis. End users following the recommended workflow do not need to execute them.

### Environment

Python 3.11 or newer is required. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Dependencies are declared in `pyproject.toml`. Qt remains part of the current installation dependencies even when using the CLI; analysis does not require opening the GUI. `requirements-macos-py312.lock` is the exact snapshot from the original macOS/Python 3.12 validation environment, not a cross-platform binary compatibility guarantee.

### Command-line analysis

```bash
neurospike demo --output results/demo
neurospike analyze /path/to/cell.abf --channel 0 --start 0.1 --end 0.6 \
  --baseline-start 0 --baseline-end 0.05 --output results/cell
neurospike analyze /path/to/one.abf /path/to/two.abf --output results/batch
neurospike analyze /path/to/data.csv --time-unit ms --voltage-unit mV --output results/csv
```

Use an explicit `analyze` or `demo` subcommand for headless execution. Running `neurospike` without a subcommand launches the retained GUI. Current CLI messages and desktop labels are in Chinese; selecting the English README does not change application language.

Analysis and baseline windows are in seconds. `--refractory`, `--lookback`, `--ahp-window`, and `--smooth` use milliseconds; `--dvdt` uses mV/ms. ABF channels are zero-indexed. The output directory must not already exist. A multi-file invocation fails as a whole on invalid input; it does not silently skip failed files. Shared windows and settings must be valid for every selected sweep.

### Python API

```python
from neurospike.analysis import AnalysisConfig, analyze
from neurospike.export import export_bundle
from neurospike.io import load_recording

recording = load_recording("/path/to/cell.abf", channel=0)
config = AnalysisConfig(
    start_s=0.1,
    end_s=0.6,
    baseline_start_s=0.0,
    baseline_end_s=0.05,
)
results = [analyze(trace, config) for trace in recording.traces]
export_bundle(results, "results/cell")
```

CSV headers can use `time_s,sweep0_mV,sweep1_mV`: the first column is time, and each remaining column is a voltage sweep sharing that time axis. Supported time units are s/ms and voltage units are mV/V/uV. Unknown units are rejected unless explicitly supplied. Values must be complete and finite; timestamps must increase and be approximately uniformly sampled.

## Retained desktop interface

For an existing desktop workflow, `neurospike-gui` still opens the Qt interface. It provides file/channel/sweep selection, editable analysis and baseline windows, waveform zooming, peak/threshold markers, event exclusion and restoration, batch sweep analysis, and result export. Changing measurement parameters clears previous results and exclusions; sweeps share settings during batch analysis. Manual addition of missed events is not implemented.

Existing `NeuroSpike.app` bundles require a compatible macOS version and architecture. The original local bundle is x86_64 and was tested under Rosetta on macOS 14.3.1 with an M1 Pro. It has no Apple Developer ID signing or notarization. See the [validation record (Chinese)](docs/validation.md) for details. Desktop development is currently paused.

## Scope and validation limits

NeuroSpike currently analyzes current-clamp voltage signals. It does not control acquisition hardware or implement a complete pCLAMP replacement. Automatic stimulus-current parsing, stimulus-artifact identification, liquid junction potential correction, rheobase, input resistance, membrane capacitance, f–I curves, and cell/group-level statistical testing are not implemented.

The initial implementation passed 37 automated tests, known-waveform checks, ABF1 round-trip tests, public ABF2 loading checks, and headless Qt/export checks. Public ABF2 event counts are execution results without manually annotated ground truth. No user laboratory recordings have yet been compared event by event with manual annotation or Clampfit. Review representative experimental sweeps and use consistent methods before interpreting scientific results.

## Development checks

```bash
python -m pip install -e '.[dev]'
ruff check src tests scripts
ruff format --check src tests scripts
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python -m pytest -q
python -m build
```

[GitHub Actions](https://github.com/cymqqqq/neurospike/actions) runs checks and tests on Linux and macOS. The existing macOS job additionally packages the application, exercises ABF loading and CSV/JSON/PNG export in a headless smoke test, and stores the bundle as an Actions artifact. It does not publish a release or deploy a service.

Module responsibilities and the initial acceptance scope are described in the [design record (Chinese)](docs/implementation-plan.md). That record describes the initial desktop-oriented release; the current analysis-first direction is documented here. The repository is private and has no open-source license grant.
