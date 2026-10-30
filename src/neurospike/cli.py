"""Headless analysis interface and desktop entry point."""

import argparse
import sys
from pathlib import Path

from .analysis import AnalysisConfig, analyze
from .demo import demo_recording
from .export import export_bundle
from .io import load_recording


def main(argv=None):
    parser = argparse.ArgumentParser(description="NeuroSpike 动作电位分析（本地、离线）")
    sub = parser.add_subparsers(dest="command")
    analyze_parser = sub.add_parser("analyze", help="分析一个或多个文件")
    analyze_parser.add_argument("files", nargs="+", type=Path)
    demo_parser = sub.add_parser("demo", help="分析已知事件的合成演示记录")
    for item in (analyze_parser, demo_parser):
        item.add_argument("--output", required=True, type=Path)
        item.add_argument("--start", type=float)
        item.add_argument("--end", type=float)
        item.add_argument("--baseline-start", type=float)
        item.add_argument("--baseline-end", type=float)
        item.add_argument("--min-peak", type=float, default=-20)
        item.add_argument("--prominence", type=float, default=20)
        item.add_argument("--dvdt", type=float, default=20)
        item.add_argument("--refractory", type=float, default=2)
        item.add_argument("--lookback", type=float, default=5)
        item.add_argument("--ahp-window", type=float, default=20)
        item.add_argument("--smooth", type=float, default=0)
    analyze_parser.add_argument("--channel", type=int, default=0, help="ABF 通道，从 0 开始")
    analyze_parser.add_argument("--time-unit", choices=["s", "ms"])
    analyze_parser.add_argument("--voltage-unit", choices=["mV", "V", "uV"])
    sub.add_parser("gui", help="打开桌面程序")
    args = parser.parse_args(argv)
    if args.command in (None, "gui"):
        from .gui import main as gui_main

        return gui_main()
    try:
        config = AnalysisConfig(
            start_s=args.start,
            end_s=args.end,
            baseline_start_s=args.baseline_start,
            baseline_end_s=args.baseline_end,
            min_peak_mv=args.min_peak,
            prominence_mv=args.prominence,
            dvdt_threshold_mv_ms=args.dvdt,
            refractory_ms=args.refractory,
            threshold_lookback_ms=args.lookback,
            ahp_window_ms=args.ahp_window,
            smoothing_ms=args.smooth,
        )
        recordings = (
            [demo_recording()]
            if args.command == "demo"
            else [
                load_recording(
                    p,
                    args.channel,
                    args.time_unit,
                    args.voltage_unit.lower() if args.voltage_unit else None,
                )
                for p in args.files
            ]
        )
        results = [analyze(trace, config) for recording in recordings for trace in recording.traces]
        output = export_bundle(results, args.output)
        for result in results:
            print(
                f"{Path(result.trace.source).name} sweep={result.trace.sweep}: "
                f"{len(result.spikes)} AP, {result.summary['firing_rate_hz']:.4g} Hz"
            )
            for warning in result.warnings:
                print("  提示:", warning)
        print("已导出:", output)
        return 0
    except Exception as exc:
        print(f"分析失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
