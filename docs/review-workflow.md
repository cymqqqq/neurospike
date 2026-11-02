# Local annotation workflow

The agent runs these commands; users can supply judgments in plain language or edit the generated CSV with a spreadsheet editor. Raw data, review sheets and outputs stay local.

```bash
neurospike review-create results/cell-a results/cell-b \
  --detection-review results/combined-detection-review.json --output results/review
neurospike review-validate results/review --output results/review/coverage.json
```

Omit `--detection-review` for a sweep-only packet. A supplied detection report must cover exactly the selected analyses, with matching primary counts and relaxed configurations. Use one analysis per source/sweep/channel per packet; do not mix full-record and stimulus-window results for the same trace. Raw files must still be accessible at their original paths with matching SHA256. Virtual demo sources are intentionally rejected; tests use synthetic source files with real bytes.

`manifest.json` binds IDs to source SHA256, channel, zero-based sweep, configuration, method, analysis code SHA256 and event time. Input export file hashes record provenance. This protects against accidental mismatches, not malicious edits to both manifest and sheets; it is not a signature. Do not edit identity columns or manifest. New analysis settings require a new packet. Existing filename-only drafts need explicit review before migration.

- `sweep-labels.csv`: all supplied sweeps. Fill `recording_quality` with `usable`, `exclude` or `uncertain`; optionally `firing_observation` with `sustained`, `early_cessation`, `no_firing` or `uncertain`. An observation is not a mechanism or diagnosis. Unknown `animal_id`/`cell_id` stay blank.
- `event-labels.csv`: only peaks found by the relaxed height/prominence detector and unmatched to the primary detector. Fill `event_label` with `ap`, `artifact`, `other_event` or `uncertain`. Inspect raw context before deciding.
- Every judgment requires `annotator`; `exclude`, `artifact` and `other_event` additionally require `notes`. Blank means pending, not normal or negative. `uncertain` counts as reviewed but not decisive. Notes can use Chinese.
- Validation rejects changed identities, unknown labels, duplicate/missing rows, malformed CSV and missing/changed source files. It hashes the CSVs and reports coverage, missing biological IDs and separate firing-observation counts. An optional output report uses exclusive creation; choose a new filename after editing.

This increment validates and summarizes decisions. It does **not** add/delete events, recalculate parameters, resolve reviewer disagreements, compute precision/recall or train a supervised model. Relaxed-only candidates are a biased subset: primary false detections and events missed by both detectors are absent. All-sweep coverage reduces selection bias for recording review but does not make event ground truth complete. Full-interval event annotation and audited application are explicit P0 follow-ups in the [roadmap](roadmap.md).

中文：用户不需要运行命令，可以描述判断并交由代理填写。`usable/exclude/uncertain` 分别表示记录可用/建议剔除/不确定；`ap/artifact/other_event/uncertain` 表示动作电位/伪迹/其他事件/不确定。所有判断都要注明标注人，剔除、伪迹及其他事件还需说明依据；动物和细胞关系不知道就留空。校验成功表示格式和来源检查通过，不表示判断已经科学验证，也不会自动改变原测量。
