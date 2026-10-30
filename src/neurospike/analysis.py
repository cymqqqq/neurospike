"""Explicit, configurable AP definitions; no hidden baseline correction."""

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.signal import find_peaks, savgol_filter

from .models import Trace


@dataclass(frozen=True)
class AnalysisConfig:
    start_s: float | None = None
    end_s: float | None = None
    baseline_start_s: float | None = None
    baseline_end_s: float | None = None
    min_peak_mv: float = -20.0
    prominence_mv: float = 20.0
    dvdt_threshold_mv_ms: float = 20.0
    refractory_ms: float = 2.0
    threshold_lookback_ms: float = 5.0
    ahp_window_ms: float = 20.0
    smoothing_ms: float = 0.0
    excluded_peak_times_s: tuple[float, ...] = ()

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name == "excluded_peak_times_s":
                if not np.isfinite(value).all():
                    raise ValueError("排除峰值时间必须是有限数值。")
                continue
            if value is not None and not np.isfinite(value):
                raise ValueError(f"{name} 必须是有限数值。")
        for name in (
            "prominence_mv",
            "dvdt_threshold_mv_ms",
            "refractory_ms",
            "threshold_lookback_ms",
            "ahp_window_ms",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} 必须大于 0。")
        if self.smoothing_ms < 0:
            raise ValueError("平滑时间不能为负数。")


@dataclass
class Spike:
    source: str
    sweep: int
    channel: int
    spike_number: int
    peak_time_s: float
    peak_mv: float
    threshold_time_s: float | None = None
    threshold_mv: float | None = None
    amplitude_mv: float | None = None
    half_width_ms: float | None = None
    rise_time_ms: float | None = None
    max_upstroke_mv_ms: float | None = None
    max_downstroke_mv_ms: float | None = None
    ahp_trough_time_s: float | None = None
    ahp_trough_mv: float | None = None
    ahp_depth_from_threshold_mv: float | None = None
    ahp_depth_from_baseline_mv: float | None = None
    isi_ms: float | None = None
    instantaneous_frequency_hz: float | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    trace: Trace
    config: AnalysisConfig
    spikes: list[Spike]
    summary: dict
    warnings: list[str]
    processed_mv: np.ndarray


def _crossing_time(t, v, level, rising):
    """Interpolate the last rising or first falling crossing."""
    if len(t) < 2:
        return None
    mask = (
        ((v[:-1] < level) & (v[1:] >= level)) if rising else ((v[:-1] >= level) & (v[1:] < level))
    )
    indices = np.flatnonzero(mask)
    if not len(indices):
        return None
    i = indices[-1] if rising else indices[0]
    return float(t[i] + (level - v[i]) * (t[i + 1] - t[i]) / (v[i + 1] - v[i]))


def analyze(trace: Trace, config: AnalysisConfig | None = None) -> AnalysisResult:
    cfg = config or AnalysisConfig()
    t = trace.time_s
    raw = trace.voltage_mv
    dt = trace.dt_s
    start = float(t[0]) if cfg.start_s is None else cfg.start_s
    # The interval covers sampled timestamps; frequency uses its explicit duration.
    end = float(t[-1]) if cfg.end_s is None else cfg.end_s
    if not t[0] <= start < end <= t[-1] + dt * 1e-6:
        raise ValueError("分析起止时间必须在记录范围内，且结束时间大于开始时间。")
    a = int(np.searchsorted(t, start, side="left"))
    b = int(np.searchsorted(t, end, side="right"))
    if b - a < 5:
        raise ValueError("分析区间至少需要 5 个采样点。")
    v = raw.copy()
    warnings = []
    smoothing_samples = 0
    if cfg.smoothing_ms:
        smoothing_samples = max(5, int(round(cfg.smoothing_ms / (dt * 1000))) | 1)
        if smoothing_samples > len(v):
            raise ValueError("平滑窗口长于记录。")
        v = savgol_filter(v, smoothing_samples, 3)
        warnings.append("平滑已开启：阈值、波宽和其他波形指标均在平滑后电压上测量。")
    dv = np.gradient(v, t * 1000)  # mV / ms, including non-zero time origin
    if dt > 0.0001 + 1e-12:
        warnings.append("采样率低于 10 kHz：阈值、波宽和最大斜率的时间分辨率有限。")
    bs = cfg.baseline_start_s
    be = cfg.baseline_end_s
    if (bs is None) != (be is None):
        raise ValueError("基线起止时间需要同时指定。")
    if bs is None:
        bs = float(t[0])
        be = start if start - bs >= 2 * dt else min(float(t[-1]), bs + 0.01)
        warnings.append(
            "未指定基线：使用分析前记录；若不足则使用记录最初 10 ms。请确认无放电/刺激。"
        )
    if not t[0] <= bs < be <= t[-1] + dt * 1e-6:
        raise ValueError("基线区间必须在记录范围内，且结束时间大于开始时间。")
    baseline_mask = (t >= bs) & (t < be)
    if np.count_nonzero(baseline_mask) < 2:
        raise ValueError("基线区间至少需要 2 个采样点。")
    baseline = float(np.median(raw[baseline_mask]))
    # Limit peak detection to the selected interval: outside-window events must not
    # suppress an inside-window peak through the refractory-distance constraint.
    peaks, properties = find_peaks(
        v[a:b],
        height=cfg.min_peak_mv,
        prominence=cfg.prominence_mv,
        distance=max(1, int(np.ceil(cfg.refractory_ms / (dt * 1000)))),
        plateau_size=True,
    )
    peaks = peaks + a
    keep = np.array(
        [
            not any(abs(t[p] - excluded) <= dt / 2 for excluded in cfg.excluded_peak_times_s)
            for p in peaks
        ],
        dtype=bool,
    )
    peaks = peaks[keep]
    properties = {key: value[keep] for key, value in properties.items()}
    if v[a] >= cfg.min_peak_mv or v[b - 1] >= cfg.min_peak_mv:
        warnings.append("分析区间边界处电压较高：可能存在被截断且未计数的动作电位。")
    spikes = []
    threshold_indices = []
    for n, p in enumerate(peaks):
        spike = Spike(trace.source, trace.sweep, trace.channel, n + 1, float(t[p]), float(v[p]))
        lo = max(a, p - int(np.ceil(cfg.threshold_lookback_ms / (dt * 1000))))
        if n:
            lo = max(lo, int(peaks[n - 1]) + 1)
        steep = lo + int(np.argmax(dv[lo : p + 1]))
        onset = _crossing_time(
            t[lo : steep + 1], dv[lo : steep + 1], cfg.dvdt_threshold_mv_ms, rising=True
        )
        if onset is None:
            spike.flags.append("threshold_not_found")
            threshold_indices.append(None)
        else:
            spike.threshold_time_s = onset
            spike.threshold_mv = float(np.interp(onset, t, v))
            spike.amplitude_mv = spike.peak_mv - spike.threshold_mv
            spike.rise_time_ms = (spike.peak_time_s - onset) * 1000
            onset_index = int(np.searchsorted(t, onset, side="left"))
            threshold_indices.append(onset_index)
            spike.max_upstroke_mv_ms = float(np.max(dv[onset_index : p + 1]))
        if properties["plateau_sizes"][n] * dt * 1000 >= 0.2:
            spike.flags.append("flat_peak_check_clipping")
        spikes.append(spike)
    for n, (p, spike) in enumerate(zip(peaks, spikes, strict=True)):
        ahp_end = spike.peak_time_s + cfg.ahp_window_ms / 1000
        stop = min(b - 1, int(np.searchsorted(t, ahp_end, side="right")) - 1)
        if n + 1 < len(peaks):
            next_start = threshold_indices[n + 1]
            stop = min(stop, (next_start if next_start is not None else int(peaks[n + 1])) - 1)
        if stop <= p:
            spike.flags.append("repolarization_not_observed")
            continue
        if t[stop] < ahp_end - dt:
            spike.flags.append("ahp_window_truncated")
        trough = int(p + np.argmin(v[p : stop + 1]))
        if trough == p:
            spike.flags.append("repolarization_not_observed")
        spike.ahp_trough_time_s = float(t[trough])
        spike.ahp_trough_mv = float(v[trough])
        spike.ahp_depth_from_baseline_mv = baseline - spike.ahp_trough_mv
        if trough == stop and dv[stop] < 0:
            spike.flags.append("ahp_trough_at_window_edge")
        spike.max_downstroke_mv_ms = float(np.min(dv[p : trough + 1]))
        if spike.threshold_mv is not None:
            spike.ahp_depth_from_threshold_mv = spike.threshold_mv - spike.ahp_trough_mv
            half = (spike.peak_mv + spike.threshold_mv) / 2
            onset_index = max(a, int(np.searchsorted(t, spike.threshold_time_s)) - 1)
            up = _crossing_time(t[onset_index : p + 1], v[onset_index : p + 1], half, True)
            down = _crossing_time(t[p : stop + 1], v[p : stop + 1], half, False)
            if up is not None and down is not None:
                spike.half_width_ms = (down - up) * 1000
            else:
                spike.flags.append("half_width_not_observed")
    # Compute ISI independently of whether repolarization could be measured.
    for n in range(1, len(spikes)):
        spikes[n].isi_ms = (spikes[n].peak_time_s - spikes[n - 1].peak_time_s) * 1000
        spikes[n].instantaneous_frequency_hz = 1000 / spikes[n].isi_ms
    intervals = [s.isi_ms for s in spikes if s.isi_ms is not None]
    summary = {
        "source": trace.source,
        "sweep": trace.sweep,
        "channel": trace.channel,
        "label": trace.label,
        "sampling_rate_hz": 1 / dt,
        "window_start_s": start,
        "window_end_s": end,
        "window_duration_s": end - start,
        "baseline_start_s": bs,
        "baseline_end_s": be,
        "baseline_mv": baseline,
        "smoothing_window_samples": smoothing_samples,
        "spike_count": len(spikes),
        "firing_rate_hz": len(spikes) / (end - start),
        "first_peak_latency_ms": (spikes[0].peak_time_s - start) * 1000 if spikes else None,
        "mean_isi_ms": float(np.mean(intervals)) if intervals else None,
        "isi_cv": float(np.std(intervals, ddof=1) / np.mean(intervals))
        if len(intervals) > 1
        else None,
        "last_over_first_isi": intervals[-1] / intervals[0] if len(intervals) > 1 else None,
        "flagged_spike_count": sum(bool(s.flags) for s in spikes),
    }
    for key in (
        "threshold_mv",
        "amplitude_mv",
        "half_width_ms",
        "max_upstroke_mv_ms",
        "max_downstroke_mv_ms",
        "ahp_depth_from_threshold_mv",
        "ahp_depth_from_baseline_mv",
    ):
        values = [getattr(s, key) for s in spikes if getattr(s, key) is not None]
        summary["mean_" + key] = float(np.mean(values)) if values else None
        summary["n_" + key] = len(values)
    return AnalysisResult(trace, cfg, spikes, summary, warnings, v)
