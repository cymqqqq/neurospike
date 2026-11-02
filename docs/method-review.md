# Action potential method review

[简体中文解读](method-review.zh-CN.md) · [Operational definitions](measurement-definitions.md)

Reviewed 2026-11-02. All existing numerical AP measurements, sweep summaries and effective counts were audited against `src/neurospike/analysis.py` and compared with the sources below. This is a literature and implementation review, not a claim of experimental accuracy or equivalence to Clampfit, eFEL or IPFX. The algorithm remains `ap-dvdt-1`; the additive method registry is version `1`.

## Evidence and decisions

The Gouwens et al. 2019 full text was read via NCBI BioC, especially its Methods paragraph beginning “Electrophysiological features were measured”. It describes initial detection at 20 mV/ms, refinement at 5% of mean maximal upstroke, and a width referenced to peak minus fast trough. Those settings belong to that protocol, not a universal standard. The paper describes AllenSDK at publication time; the separately pinned modern IPFX source below is an implementation comparator, not the historical paper's exact code.

The eFEL documentation and pinned source were read for onset-based amplitude/width, AHP sign, ISI CV and firing/adaptation statistics. Van Geit et al. 2016, section “Electrophysiology feature extraction”, describes eFEL's role in feature-based analysis; it does not establish that every eFEL definition is the only valid definition. Lazic 2010 supports the distinction between observations and independent experimental units. Kapoor and Narayanan 2023 supports the leakage precautions in the ML proposal; it is not an intracellular detection performance study.

Defaults and numbers have been preserved. A legitimate alternative definition is labeled explicitly rather than silently replacing the existing method. No automatic Allen/eFEL compatibility mode has been implemented. Every new result bundle includes a complete `method_manifest`, citations/comparison notes, actual analysis config, and SHA256 of `analysis.py`. Git commit, modified files/scripts and execution details still need to be saved by the executing agent. The hash identifies this analysis module, not the whole environment.

## Shared signal and selection rules

Current-clamp voltage in mV and seconds is required. Default processing uses raw voltage, no liquid junction potential correction, detrending or resampling. Optional order-3 Savitzky–Golay smoothing uses at least 5 samples and an odd window; actual window size is exported. Shape metrics use processed voltage; baseline uses raw voltage.

The candidate detector is SciPy `find_peaks` within the selected interval, with configurable peak height, prominence and separation. Defaults are −20 mV, 20 mV and 2 ms. Prominence is not onset-to-peak amplitude. Endpoint peaks are not counted. This is not the Gouwens/IPFX detection pipeline, and small spikes or strong artifacts may be missed or misclassified. The fixed onset crossing defaults to 20 mV/ms in a 5 ms lookback. The AHP window defaults to 20 ms, limited by analysis end and the next retained event's onset (next peak if onset unavailable). Excluding an event recomputes neighboring intervals and search boundaries.

Quality flags remain in the statistics until explicit exclusion. Unavailable values are null/blank, never zero; counts of valid measurements accompany means. Zero spikes is a valid result with zero full-window rate. No events, unavailable onset, truncated repolarization and failed input must remain distinguishable.

## Complete metric audit

Each entry states the implementation and the relevant comparison. Source IDs resolve below. They document a related definition or difference, not an endorsement of NeuroSpike. Fields identifying source/sweep/channel/event number, window endpoints, sample rate and smoothing size are provenance, not AP physiological measurements; they are exported with units/meaning in the operational definitions and configuration.

### `peak_time_s` (s)

Timestamp of retained sampled local maximum; no peak fitting.

Comparison: Detection and filtering affect which peak is retained.

Sources: gouwens2019. Status: implementation reviewed; laboratory validation pending.

### `peak_mv` (mV)

Processed voltage at retained peak sample.

Comparison: Absolute potential, without liquid junction potential correction.

Sources: gouwens2019. Status: implementation reviewed; laboratory validation pending.

### `threshold_time_s` (s)

Last upward fixed dV/dt crossing before maximal upstroke in lookback; linear time interpolation; bounded by analysis start and previous retained peak.

Comparison: Not Allen/IPFX 5%-of-mean-upstroke refinement.

Sources: gouwens2019, ipfx_detector. Status: implementation reviewed; laboratory validation pending.

### `threshold_mv` (mV)

Voltage linearly interpolated at threshold_time_s.

Comparison: Fixed dV/dt onset differs from IPFX refined onset.

Sources: gouwens2019, ipfx_detector. Status: implementation reviewed; laboratory validation pending.

### `amplitude_mv` (mV)

peak_mv - threshold_mv; unavailable if threshold missing.

Comparison: Same reference family as eFEL AP_amplitude; onset may differ.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `half_width_ms` (ms)

Time between last rising and first falling crossings of (peak_mv + threshold_mv)/2; linear interpolation; falling search ends at AHP stop.

Comparison: eFEL onset-reference family; IPFX uses trough-reference half-height with fallback.

Sources: efel, ipfx_shape, gouwens2019. Status: implementation reviewed; laboratory validation pending.

### `rise_time_ms` (ms)

1000 * (peak_time_s - threshold_time_s).

Comparison: Not a 10-90% rise time; onset method must match.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `max_upstroke_mv_ms` (mV/ms)

Maximum numpy.gradient(processed_voltage, time_ms) from first sample at/after threshold through peak.

Comparison: Derivative/filtering and segment endpoints matter.

Sources: gouwens2019, ipfx_shape. Status: implementation reviewed; laboratory validation pending.

### `max_downstroke_mv_ms` (mV/ms)

Minimum gradient from peak through sampled AHP trough; retain negative sign.

Comparison: Do not compare with absolute downstroke magnitudes without sign conversion.

Sources: ipfx_shape. Status: implementation reviewed; laboratory validation pending.

### `ahp_trough_time_s` (s)

Timestamp of minimum processed voltage from peak to configurable AHP stop; stop bounded by analysis end and before next retained onset (or peak if onset missing).

Comparison: Window minimum is not a separated fast/medium/slow AHP component.

Sources: efel, ipfx_shape. Status: implementation reviewed; laboratory validation pending.

### `ahp_trough_mv` (mV)

Minimum processed voltage in the AHP search segment, including the peak.

Comparison: Window selection differs from eFEL/IPFX trough rules.

Sources: efel, ipfx_shape. Status: implementation reviewed; laboratory validation pending.

### `ahp_depth_from_threshold_mv` (mV)

threshold_mv - ahp_trough_mv; positive means below onset voltage.

Comparison: Reference voltage and AHP segment must match before comparison.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `ahp_depth_from_baseline_mv` (mV)

baseline_mv - ahp_trough_mv; positive means below baseline; negative allowed.

Comparison: Opposite sign to eFEL AHP_depth for identical baseline and trough.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `isi_ms` (ms)

1000 * difference between consecutive retained peak timestamps; first is missing.

Comparison: IPFX uses threshold timestamps. Exclusions change intervals.

Sources: ipfx_train, efel. Status: implementation reviewed; laboratory validation pending.

### `instantaneous_frequency_hz` (Hz)

1000 / isi_ms; attached to the later peak.

Comparison: Its mean is not count divided by window duration.

Sources: ipfx_train. Status: implementation reviewed; laboratory validation pending.

### `baseline_mv` (mV)

Median raw voltage in [baseline_start_s, baseline_end_s); automatic fallback and effective interval recorded in summary.

Comparison: Not automatically a resting membrane potential.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `spike_count` (count)

Number of retained peaks after explicit exclusions; flagged events included.

Comparison: Peak height/prominence/distance detector is not the Allen detection pipeline.

Sources: gouwens2019, ipfx_detector. Status: implementation reviewed; laboratory validation pending.

### `firing_rate_hz` (Hz)

spike_count / (window_end_s - window_start_s); zero if no peaks.

Comparison: Same full-window denominator family as IPFX average_rate; eFEL mean_frequency ends at last spike.

Sources: ipfx_train, efel_train. Status: implementation reviewed; laboratory validation pending.

### `first_peak_latency_ms` (ms)

1000 * (first retained peak timestamp - window_start_s); missing if no peak.

Comparison: Not threshold latency; stimulus onset is not automatically detected.

Sources: ipfx_train. Status: implementation reviewed; laboratory validation pending.

### `mean_isi_ms` (ms)

Arithmetic mean of all retained peak-to-peak ISIs; missing with fewer than 2 peaks.

Comparison: Specify inclusion of first ISI and peak/threshold timing.

Sources: efel, ipfx_train. Status: implementation reviewed; laboratory validation pending.

### `isi_cv` (dimensionless)

Sample SD (ddof=1) / mean of all ISIs, including first; requires at least 2 ISIs (3 peaks).

Comparison: eFEL ISI_CV excludes first ISI by default unless ignore_first_ISI=0.

Sources: efel. Status: implementation reviewed; laboratory validation pending.

### `last_over_first_isi` (dimensionless)

Last ISI / first ISI; requires at least 2 ISIs (3 peaks).

Comparison: Not normalized consecutive-ISI adaptation_index in IPFX/eFEL.

Sources: ipfx_train, efel_train. Status: implementation reviewed; laboratory validation pending.

### `flagged_spike_count` (count)

Number of retained peaks with at least one quality flag.

Comparison: A quality flag does not automatically exclude an event.

Sources: Project-specific quality bookkeeping; no physiological equivalence claimed. Status: implementation reviewed; laboratory validation pending.

### `mean_threshold_mv` (mV)

Arithmetic mean of available threshold_mv within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_threshold_mv` (count)

Number of non-missing threshold_mv values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_amplitude_mv` (mV)

Arithmetic mean of available amplitude_mv within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_amplitude_mv` (count)

Number of non-missing amplitude_mv values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_half_width_ms` (ms)

Arithmetic mean of available half_width_ms within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_half_width_ms` (count)

Number of non-missing half_width_ms values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_max_upstroke_mv_ms` (mV/ms)

Arithmetic mean of available max_upstroke_mv_ms within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_max_upstroke_mv_ms` (count)

Number of non-missing max_upstroke_mv_ms values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_max_downstroke_mv_ms` (mV/ms)

Arithmetic mean of available max_downstroke_mv_ms within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_max_downstroke_mv_ms` (count)

Number of non-missing max_downstroke_mv_ms values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_ahp_depth_from_threshold_mv` (mV)

Arithmetic mean of available ahp_depth_from_threshold_mv within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_ahp_depth_from_threshold_mv` (count)

Number of non-missing ahp_depth_from_threshold_mv values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `mean_ahp_depth_from_baseline_mv` (mV)

Arithmetic mean of available ahp_depth_from_baseline_mv within one sweep; missing values ignored; flagged events included unless explicitly excluded.

Comparison: Descriptive event-level mean, not a cell/animal/group inference.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

### `n_ahp_depth_from_baseline_mv` (count)

Number of non-missing ahp_depth_from_baseline_mv values used in the sweep mean.

Comparison: Measurement count is not independent biological sample size.

Sources: lazic2010. Status: implementation reviewed; laboratory validation pending.

## Measurement versus inference

The exported means are within-sweep descriptive summaries. They do not implement cell-, animal- or group-level hypothesis tests. Before a group comparison, specify animal/cell IDs, paired or repeated conditions, stimulus amplitude/duration, inclusion rules, target estimand and independent treatment-assignment unit. For animal-level treatments, cells nested within an animal are correlated. Use a design-appropriate predeclared aggregation or hierarchical/repeated-measures model, report each level's N, effect size and interval, and address multiple comparisons. More spikes do not create more independent animals [lazic2010]. Missingness and quality flags may be selective; a valid-value mean alone does not solve that bias.

For example, ISIs of 20 and 40 ms give a mean of 30 ms, sample CV about 0.4714 and last/first ratio 2. The IPFX normalized consecutive difference is (40−20)/(40+20) = 1/3. These are different summaries, even on the same events. Three peaks in a 100 ms selected interval give 30 Hz; eFEL mean_frequency uses the last peak rather than the analysis end and can therefore differ. Peak latency includes the threshold-to-peak interval that threshold latency omits.

## Machine learning decision

**Do not add a trained model to the measurement path yet.** There is no laboratory annotation set, independent test set or demonstrated rule-based failure rate. Exact definitions and reproducible formulas address the current problem. The original audit added no ML. A later follow-up adds optional exploratory Isolation Forest review ranking, documented in [ML review](ml-review.md); no supervised detection/measurement model or validated accuracy improvement is claimed.

The first useful candidate is an optional quality-review assistant: score suspected stimulation artifacts, clipped events and possible missed spikes, then prioritize human review. Keep waveform measurements deterministic and preserve raw data. A supervised model may eventually help when artifacts resemble spikes or fixed thresholds miss variable amplitudes; that benefit must be measured, not assumed. A model must search unselected segments too if it is intended to improve recall. Clustering cell-level features can later explore phenotypes under matched protocols; clusters alone do not establish biological cell types. Gouwens 2019 provides an example of feature reduction and stability-tested clustering, not proof that this application's future clusters will be valid.

A practical evaluation plan is:

1. Label representative laboratory recordings, including quiet periods, weak spikes, bursts, clipping, stimulus artifacts and uncertain cases. Use a written event/onset/trough annotation protocol and adjudicate disagreements. Do not use the current detector as the sole truth source.
2. Freeze splits by independent source (usually animal; use the experimental design). Keep all cells/sweeps/windows from that source in one split. Fit scalers, feature selection and tuning on training/validation data only. Hold out recording days/devices or laboratories when feasible [kapoor2023].
3. Compare the current rules with a lightweight classifier on waveform/derivative/quality features before adding a neural network. Predefine one-to-one event matching tolerance, false positives per minute, precision/recall and performance on difficult subsets. Also measure threshold, width and AHP errors, bias, measurement yield and human review time on the same independent records. Report uncertainty across independent units. No numerical success threshold or sample-size claim is justified yet.
4. Validate all denoising against shape distortion. Retain raw voltage, version annotations/models/configs/seeds and first run in shadow mode with confidence/abstention and a disable switch. Promote only if held-out performance improves on the rules without unacceptable parameter bias. No automatic data deletion or external training upload.

## Validation status and remaining scientific work

Existing known-waveform and edge-case tests establish software behavior; the added tests ensure exported definitions cover every physiological metric and derived mean/count, cite resolvable source IDs, and preserve nondefault run settings. They are not experimental validation. This review statically compared external source definitions; it did not execute IPFX or eFEL on matched laboratory traces.

Next, use representative user ABF files plus manual or Clampfit annotations, match channel/sweep/event/filters and windows, and quantify event agreement and per-metric differences. Confirm stimulus timing, current-clamp units, liquid junction potential handling and baseline selection. Slow AHP and stimulus-derived parameters need protocol-specific extensions; the current 20 ms minimum cannot be relabeled as a universal fast/medium/slow AHP. There are no user-data results to report in this change.

## References and precise locations

- **gouwens2019**: [Classification of electrophysiological and morphological neuron types in the mouse visual cortex](https://pmc.ncbi.nlm.nih.gov/articles/PMC8078853/). Location: Methods: electrophysiological feature analysis. Evidence: full_text. DOI: 10.1038/s41593-019-0417-0.
- **ipfx_detector**: [detect_putative_spikes; refine_threshold_indexes; find_upstroke_indexes; find_downstroke_indexes](https://github.com/AllenInstitute/ipfx/blob/c607a36e25618a6bb8ba5438c1cd945fb429e659/ipfx/spike_detector.py). Location: detect_putative_spikes; refine_threshold_indexes; find_upstroke_indexes; find_downstroke_indexes. Evidence: pinned_source.
- **ipfx_shape**: [find_widths; analyze_trough_details](https://github.com/AllenInstitute/ipfx/blob/c607a36e25618a6bb8ba5438c1cd945fb429e659/ipfx/spike_features.py). Location: find_widths; analyze_trough_details. Evidence: pinned_source.
- **ipfx_train**: [basic_spike_train_features; average_rate; latency; norm_diff](https://github.com/AllenInstitute/ipfx/blob/c607a36e25618a6bb8ba5438c1cd945fb429e659/ipfx/spike_train_features.py). Location: basic_spike_train_features; average_rate; latency; norm_diff. Evidence: pinned_source.
- **efel**: [AP_amplitude; AP_duration_half_width; AHP_depth; ISI_CV](https://github.com/BlueBrain/eFEL/blob/1b6c129dd0de1e782ee70777a92d642898af28b5/docs/source/eFeatures.rst). Location: AP_amplitude; AP_duration_half_width; AHP_depth; ISI_CV. Evidence: pinned_documentation.
- **efel_train**: [firing_rate; __adaptation_index](https://github.com/BlueBrain/eFEL/blob/1b6c129dd0de1e782ee70777a92d642898af28b5/efel/cppcore/SpikeEvent.cpp). Location: firing_rate; __adaptation_index. Evidence: pinned_source.
- **lazic2010**: [The problem of pseudoreplication in neuroscientific studies: is it affecting your analysis?](https://pmc.ncbi.nlm.nih.gov/articles/PMC2817684/). Location: Introduction; hierarchically organised data; solutions. Evidence: full_text. DOI: 10.1186/1471-2202-11-5.
- **vangeit2016**: Van Geit et al., [BluePyOpt: Leveraging Open Source Software and Cloud Infrastructure to Optimise Model Parameters in Neuroscience](https://doi.org/10.3389/fninf.2016.00017). Full text [PMC4896051](https://pmc.ncbi.nlm.nih.gov/articles/PMC4896051/); section “Electrophysiology feature extraction”.
- **kapoor2023**: Kapoor & Narayanan, [Leakage and the reproducibility crisis in machine-learning-based science](https://doi.org/10.1016/j.patter.2023.100804). Full text [PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856/); leakage taxonomy and model info sheets.

Retrieved 2026-11-02. The externally hosted `stable` eFEL HTML reported version 5.7.34 when read; implementation comparisons link pinned source commits rather than treating that moving alias as a reproducible version. IPFX `norm_diff`'s docstring reverses subtraction order relative to its executable expression; the positive-for-increasing-ISI formula reported here follows the code. See `method-review-sources.json` for retrieved source hashes and locations. Only bibliography and source fingerprints are committed; third-party full texts/source copies remain in the research scratch directory.
