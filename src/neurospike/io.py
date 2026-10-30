"""Read voltage recordings without modifying source files."""

import csv
import re
from pathlib import Path

import numpy as np

from .models import Recording, Trace

VOLTAGE_FACTORS = {"mv": 1.0, "v": 1000.0, "uv": 0.001, "µv": 0.001, "μv": 0.001}
TIME_FACTORS = {"s": 1.0, "ms": 0.001}


def abf_channels(path):
    import pyabf

    abf = pyabf.ABF(str(path), loadData=False)
    return [
        {"index": i, "name": abf.adcNames[i], "unit": abf.adcUnits[i]}
        for i in range(abf.channelCount)
    ]


def load_abf(path, channel=0):
    import pyabf

    path = Path(path)
    abf = pyabf.ABF(str(path))
    if not 0 <= channel < abf.channelCount:
        raise ValueError(f"通道 {channel} 不存在，文件共有 {abf.channelCount} 个通道。")
    unit = abf.adcUnits[channel].strip().lower()
    if unit not in VOLTAGE_FACTORS:
        raise ValueError(f"通道单位是 {abf.adcUnits[channel]!r}，请选择电压通道（mV/V/µV）。")
    traces = []
    for sweep in abf.sweepList:
        abf.setSweep(sweep, channel=channel)
        traces.append(
            Trace(
                abf.sweepX,
                abf.sweepY * VOLTAGE_FACTORS[unit],
                str(path.resolve()),
                sweep,
                channel,
                abf.adcNames[channel],
            )
        )
    return Recording(traces, abf_channels(path))


def _header_unit(header, factors):
    parts = re.split(r"[_\s()\[\]]+", header.strip().lower())
    return (
        parts[-1]
        if parts[-1] in factors
        else next((p for p in reversed(parts) if p in factors), None)
    )


def load_csv(path, time_unit=None, voltage_unit=None):
    """First column = time; remaining columns = separate voltage sweeps."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        lines = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 6:
        raise ValueError("CSV/TXT 需要表头和至少 5 行数据。")
    first = lines[0]
    delimiter = next((d for d in (",", "\t", ";") if d in first), None)
    rows = (
        list(csv.reader(lines, delimiter=delimiter))
        if delimiter
        else [line.split() for line in lines]
    )
    headers = [h.strip() for h in rows[0]]
    if len(headers) < 2 or len(set(headers)) != len(headers):
        raise ValueError("表头至少需要时间、电压两列，且列名不能重复。")
    if any(len(row) != len(headers) for row in rows[1:]):
        raise ValueError("数据各行列数不一致，或存在空白单元格。")
    try:
        data = np.array(rows[1:], dtype=float)
    except ValueError as exc:
        raise ValueError("除表头外的单元格必须全部为数值。") from exc
    tu = time_unit or _header_unit(headers[0], TIME_FACTORS)
    if tu not in TIME_FACTORS:
        raise ValueError("无法识别时间单位；将第一列命名 time_s/time_ms，或手动指定。")
    traces = []
    for col, header in enumerate(headers[1:], start=1):
        vu = voltage_unit or _header_unit(header, VOLTAGE_FACTORS)
        if vu not in VOLTAGE_FACTORS:
            raise ValueError(f"无法识别 {header!r} 的电压单位；在列名末尾加 _mV，或手动指定。")
        traces.append(
            Trace(
                data[:, 0] * TIME_FACTORS[tu],
                data[:, col] * VOLTAGE_FACTORS[vu],
                str(path.resolve()),
                col - 1,
                0,
                header,
            )
        )
    return Recording(traces)


def load_recording(path, channel=0, time_unit=None, voltage_unit=None):
    suffix = Path(path).suffix.lower()
    if suffix == ".abf":
        return load_abf(path, channel)
    if suffix in {".csv", ".txt", ".tsv"}:
        return load_csv(path, time_unit, voltage_unit)
    raise ValueError("支持 .abf、.csv、.tsv 和带表头的 .txt 文件。")
