"""Transactional export bundles: per-spike CSV, sweep CSV, metadata and a review plot."""

import csv
import hashlib
import json
import platform
import shutil
import tempfile
from dataclasses import asdict, fields
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .analysis import AnalysisResult, Spike

METHOD_VERSION = "ap-dvdt-1"


def _write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            clean = {k: ";".join(v) if isinstance(v, list) else v for k, v in row.items()}
            # Protect spreadsheet users from formula injection in filenames/labels.
            clean = {
                k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v
                for k, v in clean.items()
            }
            writer.writerow(clean)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_review_plot(results, path):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    visible = results[:12]
    fig = Figure(figsize=(11, max(3, len(visible) * 2.1)), layout="constrained")
    FigureCanvasAgg(fig)
    for i, result in enumerate(visible):
        ax = fig.add_subplot(len(visible), 1, i + 1)
        trace = result.trace
        # Min/max envelope reduction preserves short spikes in long traces.
        t, v = trace.time_s, trace.voltage_mv
        if len(t) > 30000:
            import numpy as np

            size = int(np.ceil(len(t) / 15000))
            indices = []
            for start in range(0, len(t), size):
                chunk = v[start : start + size]
                indices.extend(
                    sorted((start + int(np.argmin(chunk)), start + int(np.argmax(chunk))))
                )
            ax.plot(t[indices], v[indices], lw=0.5, color="#567187")
        else:
            ax.plot(t, v, lw=0.5, color="#567187")
        ax.scatter(
            [s.peak_time_s for s in result.spikes],
            [s.peak_mv for s in result.spikes],
            c="#e27836",
            s=14,
            label="Accepted peaks",
            zorder=3,
        )
        threshold_spikes = [s for s in result.spikes if s.threshold_mv is not None]
        ax.scatter(
            [s.threshold_time_s for s in threshold_spikes],
            [s.threshold_mv for s in threshold_spikes],
            c="#16817a",
            s=12,
            label="dV/dt thresholds",
            zorder=3,
        )
        ax.axvspan(result.summary["window_start_s"], result.summary["window_end_s"], alpha=0.06)
        ax.set(
            ylabel="mV",
            xlabel="Time (s)",
            title=f"Sweep {trace.sweep} | {len(result.spikes)} AP | "
            f"{result.summary['firing_rate_hz']:.3g} Hz",
        )
        ax.legend(loc="upper right", fontsize=7)
    fig.suptitle("NeuroSpike review — first 12 sweeps maximum; CSV contains all results")
    fig.savefig(path, dpi=130)


def export_bundle(results: list[AnalysisResult], destination):
    if not results:
        raise ValueError("没有分析结果可以导出。")
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("导出目录已经存在，请选择新名称，以免覆盖以前的分析。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".neurospike-", dir=destination.parent))
    try:
        _write_csv(
            staging / "spikes.csv",
            [asdict(s) for r in results for s in r.spikes],
            [f.name for f in fields(Spike)],
        )
        _write_csv(staging / "sweeps.csv", [r.summary for r in results], list(results[0].summary))
        sources = {}
        for r in results:
            source = r.trace.source
            if source not in sources:
                sources[source] = _sha256(Path(source)) if Path(source).is_file() else None
        metadata = {
            "software": "NeuroSpike",
            "software_version": __version__,
            "method_version": METHOD_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "dependencies": {name: version(name) for name in ("numpy", "scipy", "pyabf")},
            "units": {"time": "s", "voltage": "mV", "width": "ms", "slope": "mV/ms"},
            "source_sha256": sources,
            "analyses": [
                {
                    "source": r.trace.source,
                    "sweep": r.trace.sweep,
                    "channel": r.trace.channel,
                    "config": asdict(r.config),
                    "warnings": r.warnings,
                    "summary": r.summary,
                }
                for r in results
            ],
        }
        (staging / "analysis.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        save_review_plot(results, staging / "review.png")
        (staging / "说明.txt").write_text(
            "spikes.csv：逐个动作电位；sweeps.csv：逐个 sweep。\n"
            "analysis.json：参数、手动排除、警告、源文件哈希和软件版本。\n"
            "review.png：最多前 12 个 sweep 的概览，不能替代放大检查。\n"
            "空白值表示该项无法测量，不代表零。flags 为质量提示，带提示的波形仍计入，除非手动排除。\n"
            "本软件没有自动识别刺激伪迹或读取刺激电流，潜伏期相对于手动分析起点。\n"
            "同一细胞的多个 sweep 不代表多个独立样本。详细定义请查看项目 docs/measurement-definitions.md。\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
