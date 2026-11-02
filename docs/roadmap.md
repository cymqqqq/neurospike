# Analysis development roadmap

**English** | [简体中文](roadmap.zh-CN.md)

Updated 2026-11-02. Python analysis and result delivery remain the priority. Qt is retained and paused. This is a sequenced development backlog, not a claim of feature parity or a delivery date.

## Evidence and scope

The [official pCLAMP 11/11.4 product page](https://www.moleculardevices.com/products/axon-patch-clamp-system/acquisition-and-analysis-software/pclamp-software-suite), read 2026-11-02, describes Clampfit analysis separately from Clampex acquisition and AxoScope background recording. Relevant locations: **NEW Minis Analysis Feature**, **Comprehensive analysis tools**, **Population spike analysis**, **Action potential analysis**, **Batch analysis**, and the batch-filtering FAQ. A retrieval manifest is in [clampfit-sources.json](clampfit-sources.json).

This public page supports a functional gap inventory, not exact algorithm definitions. AP search, population spike search and batch macros are marked **Advanced**. Minis Search is advertised for 11.4. Edition availability and numerical equivalence must be checked against the applicable manual and laboratory exports before claiming compatibility. The source includes acquisition features: membrane-test displays, gap-free acquisition, protocol editing and hardware digital outputs are outside this project's current scope.

## What exists and what is missing

- **AP measurements — partial.** Counts, peak timing/voltage, fixed-dV/dt onset, onset-to-peak amplitude/half-width/rise time, signed extrema of slopes, AHP, ISI and simple adaptation summaries exist. Clampfit advertises APD90 and decay measurements, which are missing. Existing slopes/onset definitions have not been established as identical to Clampfit.
- **Event management — partial.** Explicit exclusion/restoration is retained in the API/Qt. New local review packets validate labels and provenance. Manual addition of missed events, event adjudication, and audited application of labels are missing. Minis Search advertises addition/deletion and superimposed events; this does not imply NeuroSpike currently handles overlapping events.
- **Regions and plots — partial.** One shared analysis window plus baseline window and paginated traces exist. Clampfit advertises 24 cursor pairs, I–V and histograms. Named multiple regions, I–V analysis and dedicated histograms are missing. CLI region definitions will serve the analysis workflow; reproducing cursor UI is unnecessary.
- **Batch workflows — partial.** Multiple files/sweeps share a configuration and export metadata. Saved, schema-validated recipes with different regions/protocols, per-file failures/resume and general filtering macros are missing.
- **Synaptic events / Minis — missing.** Voltage-clamp current channels are deliberately rejected by the present voltage loader. Detection, event kinetics/charge, overlapping-event handling and continuous-recording event review need a separate current-signal model.
- **Population spikes — missing.** Area, coastline and paired-pulse analysis require a dedicated extracellular/field-potential workflow. AP half-width in intracellular data is not a substitute.
- **Single-channel analysis — missing.** Vendor FAQ verifies batch filtering of single-channel recordings. Idealization, dwell times and open probabilities are possible additional targets but require manual/method review before making a vendor-parity claim.

General curve fitting, FFT/PSD, leak subtraction and additional filters are **candidate extensions**. The retrieved product page does not establish their detailed Clampfit scope; inspect the relevant manual before completing a broader comparison. Do not interpret this list as an exhaustive inventory of all Clampfit versions.

## P0 — establish trusted review and experiment metadata

**Delivered in this increment:** `review-create` builds hash-bound sweep drafts and optional relaxed-only event drafts from existing bundles; `review-validate` checks source hashes, immutable identity columns, duplicates/missing rows, controlled labels, annotators and reasons, then reports coverage. All sweeps are included, not just ML outliers. Labels do not alter events. See [review workflow](review-workflow.md).

**Next implementation:** full-interval event annotation (including primary detections and events missed by every detector), independent review/adjudication, append-only corrections with reviewer/reason and before/after event counts, event snippets in the reusable exporter, and persistent project/recipe storage. Keep source analysis immutable; each corrected result gets new provenance. Existing local draft sheets are not silently imported because they lack the new identity bindings.

**Metadata prerequisite:** record animal/cell/session IDs, recording mode, stimulation source, current units and calibration, protocol windows and experimenter-confirmed meaning. Enabled DAC epoch reconstruction already exists, but a command level with unknown units must never become pA. Save measured-current vs command-current provenance.

**Acceptance:** changed source bytes, wrong channel/time/configuration, duplicate decisions and stale review files are rejected. Unknown metadata stays missing. Corrections can be replayed and reversed into separate result bundles. Complete reviewed intervals, not just extra candidates, become the basis of detection evaluation.

## P1 — complete current-clamp experiment analysis

1. **AP shape extensions:** explicitly named duration/repolarization metrics, including an APD90-style option only after fixing the reference voltage, crossing rules, truncation and interpolation definitions. Add 10–90% rise/decay, phase plots, aligned waveforms, burst and adaptation summaries with documented rules. Preserve `ap-dvdt-1`; a new numerical method gets a new identifier.
2. **Stimulus-response:** validated current steps → first-spike latency, f–I, rheobase and gain. Distinguish smallest tested spiking current from an unobserved exact threshold. Refuse current-dependent outputs when units/calibration are missing.
3. **Passive properties:** selected subthreshold steps → input resistance, exponential membrane time constant, sag and conditional capacitance estimate. Bound fitting windows; expose residuals, confidence/fit quality and model assumptions. Never fit across spikes or blindly infer capacitance from a poor single-exponential fit.
4. **Cell/animal summaries:** preserve repeated sweeps within cell/animal; report valid counts and missingness at each level. Inferential tests require a specified experimental design and independent biological IDs.

**Acceptance:** analytical waveforms and exponential responses with known values, noisy/boundary/failure cases, unit conversions and protocol mismatches; then blinded laboratory comparison of event times and every metric under matched settings. Predetermine tolerances from sampling and the scientific use case. Unknown current or biological IDs must block dependent conclusions without blocking existing AP measurements.

## P2 — reusable signal and batch analysis

Named multiple regions, explicit baseline correction, optional documented filters with edge/transient handling, alignment/averaging, distributions with bin settings, I–V curves, saved recipes, resumable per-file execution and project reopening. Fit/FFT/PSD modules follow only when the scientific question and method are specified. Raw arrays remain immutable; each processing chain, unit and parameter is exported. No implicit denoising before morphology measurement.

**Acceptance:** replay a saved recipe with matching output; reject incompatible units/windows; preserve failure status per file; verify filter frequency response/edge effects, alignment offsets, averaging sample counts, histogram totals and known I–V relations. Quantify changes in threshold, width and slopes caused by filtering.

## P3 — voltage clamp and synaptic events

Introduce a unit-safe current trace alongside the voltage model. Add inward/outward event polarity, baseline/noise estimates, threshold/template candidates, amplitude, frequency, rise/decay, charge, evoked latency and paired-pulse metrics. Establish overlap and artifact review before automated deconvolution. Support continuous records without loading every derived snippet indefinitely.

**Acceptance:** synthetic currents with known amplitude/charge/tau and overlap; polarity/unit/window/fitting failures; held-out manually reviewed intervals, false events per minute and amplitude/kinetic bias. Require representative voltage-clamp recordings and recording/protocol metadata before claiming laboratory readiness. Current AP ABFs alone cannot validate this module.

## P4 — specialist analyses and optional model improvements

Population spikes/field potentials, single-channel idealization and dwell-time models are separate modules after representative data and verified definitions. Acquisition hardware control and GUI parity remain deferred.

ML stays an optional review aid. Existing Isolation Forest ranking is exploratory. First measure review time and missed/false events with full labels; compare random review, heuristic review and ML ordering at an equal review budget. Report uncertainty at the independent-source level. If a supervised classifier is justified, split by the highest independent unit (animal/session as appropriate), keep the test set frozen, and fit all preprocessing on training data only. Current unknown biological identities and unlabeled candidates do not support supervised training, accuracy claims or cell-type/causal diagnoses. Train no denoising model until waveform bias is evaluated. No external data upload or model-file publication is implied.

## Working order

Finish P0 annotation/metadata evidence → P1 current-clamp priorities → reusable P2 components as needed → P3 with appropriate data → specialist P4. P0 and P1 deliver the most value for the current AP workflow. Each release updates English/Chinese README, method provenance, tests and this status record; GUI development resumes only on explicit request.
