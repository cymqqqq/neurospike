# Experimental machine learning for review prioritization

NeuroSpike can optionally fit an Isolation Forest to sweep-level features and rank atypical sweeps. It is a local, unsupervised review aid. The deterministic `ap-dvdt-1` detection and measurements are unchanged. No classification into valid/invalid recordings, automatic exclusions, waveform reconstruction or supervised spike detector is implemented.

## Inputs and feature definitions

Use compatible current-clamp protocols, baseline rules and analysis windows. Files are not assumed to represent independent cells/animals. Source names, sweep IDs and treatment labels are not model features. Each row uses:

- Absolute difference of baseline from the median baseline of supplied sweeps in the same source/channel, in mV. This batch-relative feature misses a whole file with uniformly abnormal baseline.
- Raw baseline interquartile range, in mV.
- Number of baseline candidates using the primary height/prominence/distance detector. Baseline endpoints and the detector can miss events; this is a cue, not a validated baseline-cleanliness test.
- Median raw voltage in the final 20% of the analysis window minus baseline, in mV.
- Fraction of the window remaining after the final retained peak, only for sweeps with at least three retained peaks; otherwise zero means not applicable, not evidence of sustained firing.
- Number of unmatched lower-height/prominence candidates divided by max(1, primary count). These candidates are not ground truth. Unavailable sensitivity is explicitly marked, and those rows are excluded from ML fitting/scoring.
- Fraction of primary events with missing onset or half-width; zero for no events is a documented convention, not proof that measurements are complete.

These features deliberately focus on recording state and detection uncertainty. Normal stimulus responses, biological variation, protocol differences and an unusual valid phenotype may all be atypical. Neither rarity nor a high score establishes a recording error.

## Separate interpretable cues

Fixed exploratory heuristics flag baseline deviation >10 mV, baseline candidates, unmatched relaxed candidates/primary count >0.2, and early firing cessation (last-peak silence >40% of the window with at least three peaks) while tail voltage remains >15 mV above baseline. These choices are review heuristics, not literature-derived physiological cutoffs, and have not been calibrated for a cell type. The last cue cannot diagnose depolarization block, distinguish genuine adaptation from detector misses, or exclude recording faults. AHP window truncation remains an event-level flag; it is not used as the main ML anomaly feature because high-frequency firing routinely truncates a fixed AHP window.

## Fit, export and abstention

`pip install -e '.[ml]'` installs the optional scikit-learn dependency. `neurospike analyze ... --ml-review` enables sensitivity review and writes `quality-review.json`. Default analysis imports no scikit-learn and uses no ML. The Python API also exposes `quality_review(results, sensitivity, machine_learning=True)`.

The model uses 200 trees, `max_samples=min(256, eligible_sweeps)`, `random_state=0`, `n_jobs=1`, and scikit-learn's `contamination='auto'`. Only negative `score_samples` and a descending rank are reported. `predict` is not used; `contamination` is not a quota for deleting data. Scores are not calibrated probabilities and must not be compared between separately fitted batches. All-equal or very small feature sets abstain (20 eligible rows and five distinct vectors are implementation guards, not evidence of sufficient independent sample size).

The JSON stores feature order, values and notes, heuristic thresholds, eligibility, model parameters, scikit-learn version, feature matrix SHA256 and the in-sample status. Fits are recreated from these records and the source/version/parameters in the analysis export. No pickle is loaded/saved and no remote training service is called. There is no frozen reusable pretrained model. An optional-dependency import failure leaves no partially committed export bundle.

## What has and has not been validated

Synthetic regression cases check baseline-shift and firing-cessation cues, abstention, deterministic rankings with a fixed seed, model provenance and preservation of primary events. Laboratory execution confirmed the code can rank real sweeps and reveal review targets; there are no expert labels establishing ML accuracy or improved review efficiency.

Repeating the same fit with different random seeds assesses numerical ranking stability only. Holding out a file can explore novelty but does not establish independent generalization when cell/animal identity is unknown and there are only a few recordings. In-sample outlier ranking is exploratory analysis, not a held-out performance claim. Normalization by within-source baseline also uses the supplied batch and must not be confused with prospective single-sweep inference.

Before promoting ML into detection or exclusion, collect independent expert annotations (including quiet intervals, weak spikes and uncertain cases), reconcile disagreements, preserve animal/cell/day IDs and predefine an independent split and event-matching tolerance. Compare the rules and ML on event precision/recall, false positives per minute, parameter bias, missingness and human review time. Fit preprocessing and tune only on training/validation data; retain a frozen independent test set. A supervised model trained only on existing detector labels cannot establish an advantage over that detector.

## 中文使用说明

这是“先看哪些记录”的试验性排序，不是自动诊断。原始 ABF、主检测事件和参数不会因此修改。报告同时给出具体证据和模型排序；高排名应结合原始波形看，不能直接删除。具有正常生物变异的记录也可能排名很高。

缺少人工真值时，可以探索无监督模型，但不能宣称提高了动作电位检出准确率。后续标注应区分“记录质量”“发放模式”和“事件是否为动作电位”，避免把真实生理变化标成坏数据。用户只需提供数据和目标；执行环境、可选依赖和命令由代理处理。

## Implementation references

- [scikit-learn IsolationForest API](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html), particularly `score_samples`, `contamination`, `max_samples` and `random_state`. The installed version is recorded in each fit.
- [NeuroSpike literature and method audit](method-review.md), including Lazic 2010 on independent experimental units and Kapoor & Narayanan 2023 on leakage. Neither paper validates this model's electrophysiology performance.
