"""Validated recording model; internal units are seconds and millivolts."""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Trace:
    time_s: np.ndarray
    voltage_mv: np.ndarray
    source: str = "synthetic"
    sweep: int = 0
    channel: int = 0
    label: str = "Voltage"

    def __post_init__(self):
        t = np.array(self.time_s, dtype=float, copy=True)
        v = np.array(self.voltage_mv, dtype=float, copy=True)
        if t.ndim != 1 or v.ndim != 1 or len(t) != len(v) or len(t) < 5:
            raise ValueError("时间和电压必须是一维、等长，且至少包含 5 个采样点。")
        if not np.isfinite(t).all() or not np.isfinite(v).all():
            raise ValueError("记录含缺失值或无穷值；请修复原始文件，不能静默删除采样点。")
        dt = np.diff(t)
        if np.any(dt <= 0):
            raise ValueError("时间必须严格递增，不能重复或倒序。")
        if not np.allclose(dt, np.median(dt), rtol=0.01, atol=1e-10):
            raise ValueError("当前版本仅支持均匀采样；检测到不等间隔时间。")
        t.setflags(write=False)
        v.setflags(write=False)
        object.__setattr__(self, "time_s", t)
        object.__setattr__(self, "voltage_mv", v)

    @property
    def dt_s(self):
        return float(np.median(np.diff(self.time_s)))


@dataclass
class Recording:
    traces: list[Trace]
    channels: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.traces:
            raise ValueError("文件没有可分析的 sweep。")
