"""Qt desktop interface. File I/O and analysis run in a worker thread."""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .analysis import AnalysisConfig, analyze
from .demo import demo_recording
from .export import export_bundle
from .io import abf_channels, load_recording


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuroSpike · 动作电位分析")
        self.resize(1320, 870)
        self.recording = None
        self.results = {}
        self.excluded = {}
        self.path = None
        self.thread = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="neurospike")
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(20)
        self.poll_timer.timeout.connect(self.poll_task)
        self._updating = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("NeuroSpike  |  ABF 电流钳 · 诱发与自发放电")
        title.setStyleSheet("font-size: 21px; font-weight: 600; padding: 8px;")
        layout.addWidget(title)
        bar = QHBoxLayout()
        self.open_button = QPushButton("打开 ABF / CSV")
        self.demo_button = QPushButton("加载合成演示")
        self.export_button = QPushButton("导出当前分析结果")
        for widget in (self.open_button, self.demo_button, self.export_button):
            bar.addWidget(widget)
        bar.addStretch()
        layout.addLayout(bar)
        self.file_label = QLabel("请选择实验文件，或先加载合成演示。原始文件不会被修改。")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        split = QSplitter()
        layout.addWidget(split, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(325)
        self.settings_panel = QWidget()
        form = QFormLayout(self.settings_panel)
        scroll.setWidget(self.settings_panel)
        split.addWidget(scroll)
        self.mode = QComboBox()
        self.mode.addItems(["诱发：区间起点设为刺激起点", "自发：区间设为观察时间"])
        form.addRow("分析场景", self.mode)
        self.channel = QComboBox()
        form.addRow("ABF 电压通道", self.channel)
        self.sweep = QComboBox()
        form.addRow("Sweep（从 0 开始）", self.sweep)
        self.inputs = {}
        specs = [
            ("start_s", "分析开始 (s)", 0, -1e6, 1e6, 6),
            ("end_s", "分析结束 (s)", 0.5, -1e6, 1e6, 6),
            ("baseline_start_s", "基线开始 (s)", 0, -1e6, 1e6, 6),
            ("baseline_end_s", "基线结束 (s)", 0.01, -1e6, 1e6, 6),
            ("min_peak_mv", "最低峰值 (mV)", -20, -1000, 1000, 2),
            ("prominence_mv", "最小突出度 (mV)", 20, 0.01, 1000, 2),
            ("dvdt_threshold_mv_ms", "阈值 dV/dt (mV/ms)", 20, 0.01, 10000, 2),
            ("refractory_ms", "最小峰间隔 (ms)", 2, 0.01, 10000, 2),
            ("threshold_lookback_ms", "阈值回溯 (ms)", 5, 0.01, 1000, 2),
            ("ahp_window_ms", "AHP 搜索窗 (ms)", 20, 0.01, 10000, 2),
            ("smoothing_ms", "平滑窗 (ms，0=关)", 0, 0, 100, 3),
        ]
        for key, label, value, low, high, decimals in specs:
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setDecimals(decimals)
            spin.setValue(value)
            spin.setSingleStep(0.001 if key.endswith("_s") else 1)
            spin.valueChanged.connect(self.invalidate)
            self.inputs[key] = spin
            form.addRow(label, spin)
        self.all_sweeps = QCheckBox("分析所有 sweep（使用相同参数/时间段）")
        form.addRow(self.all_sweeps)
        self.analyze_button = QPushButton("运行分析")
        self.reset_button = QPushButton("恢复当前 sweep 手动排除项")
        form.addRow(self.analyze_button)
        form.addRow(self.reset_button)
        help_label = QLabel(
            "橙点=峰值；绿点=阈值。\n滚轮缩放，拖动平移；点击表格行放大。\n"
            "取消勾选可排除伪迹，并重新计算统计。\n"
            "阈值/半峰宽/AHP 请结合原波形复核。\n"
            "场景选项仅提示区间设置，不自动识别刺激。"
        )
        help_label.setWordWrap(True)
        form.addRow(help_label)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        pg.setConfigOptions(antialias=True, background="w", foreground="#233746")
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "Voltage", units="mV")
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setDownsampling(auto=True, mode="peak")
        self.plot.setClipToView(True)
        right_layout.addWidget(self.plot, 3)
        self.summary = QLabel("尚未分析")
        self.summary.setWordWrap(True)
        right_layout.addWidget(self.summary)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "保留",
                "峰值时间 s",
                "阈值 mV",
                "幅度 mV",
                "半峰宽 ms",
                "上升 mV/ms",
                "下降 mV/ms",
                "AHP深度 mV¹",
                "质量提示",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        right_layout.addWidget(self.table, 2)
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(110)
        right_layout.addWidget(self.messages)
        right_layout.addWidget(
            QLabel("¹ AHP 深度相对阈值；逐个 sweep 汇总、ISI 等完整指标见导出 CSV。")
        )
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.open_button.clicked.connect(self.open_file)
        self.demo_button.clicked.connect(self.load_demo)
        self.export_button.clicked.connect(self.export)
        self.analyze_button.clicked.connect(self.run_analysis)
        self.reset_button.clicked.connect(self.reset_exclusions)
        self.sweep.currentIndexChanged.connect(self.sweep_changed)
        self.channel.currentIndexChanged.connect(self.channel_changed)
        self.table.itemChanged.connect(self.toggle_spike)
        self.table.cellClicked.connect(self.zoom_spike)
        self.statusBar().showMessage("就绪 · 所有分析在本地完成")
        self.set_busy(False)

    def set_busy(self, busy):
        self.open_button.setEnabled(not busy)
        self.demo_button.setEnabled(not busy)
        self.settings_panel.setEnabled(not busy and self.recording is not None)
        self.export_button.setEnabled(not busy and bool(self.results))
        self.table.setEnabled(not busy)

    def run_task(self, task, done):
        if self.thread is not None:
            return
        self.set_busy(True)
        self.statusBar().showMessage("正在处理，请稍候…")
        self._task_callback = done
        self.thread = self.executor.submit(task)
        self.poll_timer.start()

    def poll_task(self):
        # Qt timer runs on the main thread. The executor only returns data and
        # never owns or touches a Qt object.
        if self.thread is None or not self.thread.done():
            return
        self.poll_timer.stop()
        future = self.thread
        self.thread = None
        try:
            self._task_callback(future.result())
        except Exception as exc:
            self.error(f"{type(exc).__name__}: {exc}")
        finally:
            self.set_busy(False)
            self.statusBar().showMessage("就绪")

    def error(self, message):
        self.messages.setPlainText(message)
        QMessageBox.warning(self, "操作未完成", message)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择电流钳记录", "", "电生理记录 (*.abf *.csv *.tsv *.txt)"
        )
        if path:
            self.run_task(
                lambda: (path, abf_channels(path) if path.lower().endswith(".abf") else []),
                self.prepare_file,
            )

    def prepare_file(self, payload):
        # Schedule loading only after the metadata worker has been cleaned up.
        from PySide6.QtCore import QTimer

        path, channels = payload
        self.path = path
        self.channel.blockSignals(True)
        self.channel.clear()
        for channel in channels:
            self.channel.addItem(
                f"{channel['index']}: {channel['name']} ({channel['unit']})", channel["index"]
            )
        if not channels:
            self.channel.addItem("CSV/TXT：电压列视为 sweep", 0)
        else:
            voltage_channel = next(
                (
                    i
                    for i, c in enumerate(channels)
                    if c["unit"].strip().lower() in ("mv", "v", "uv", "µv", "μv")
                ),
                0,
            )
            self.channel.setCurrentIndex(voltage_channel)
        self.channel.blockSignals(False)

        def load_when_ready():
            if self.thread is not None:
                QTimer.singleShot(10, load_when_ready)
            else:
                self.channel_changed()

        QTimer.singleShot(10, load_when_ready)

    def channel_changed(self):
        if self.path and self.channel.currentIndex() >= 0:
            path, channel = self.path, self.channel.currentData()
            self.recording = None
            self.results.clear()
            self.table.setRowCount(0)
            self.plot.clear()
            self.run_task(lambda: load_recording(path, channel), self.set_recording)

    def load_demo(self):
        self.path = None
        self.channel.blockSignals(True)
        self.channel.clear()
        self.channel.addItem("0: 合成电压 (mV)", 0)
        self.channel.blockSignals(False)
        self.set_recording(demo_recording())
        self.set_busy(False)

    def set_recording(self, recording):
        self._updating = True
        self.recording = recording
        self.results.clear()
        self.excluded.clear()
        self.sweep.blockSignals(True)
        self.sweep.clear()
        for trace in recording.traces:
            self.sweep.addItem(f"Sweep {trace.sweep}")
        self.sweep.blockSignals(False)
        first = recording.traces[0]
        self.inputs["start_s"].setValue(float(first.time_s[0]))
        # Round inward to avoid GUI decimal rounding beyond the last sample.
        self.inputs["end_s"].setValue(np.floor(float(first.time_s[-1]) * 1e6) / 1e6)
        self.inputs["baseline_start_s"].setValue(float(first.time_s[0]))
        self.inputs["baseline_end_s"].setValue(float(min(first.time_s[-1], first.time_s[0] + 0.01)))
        self.file_label.setText(
            f"{first.source}  |  {len(recording.traces)} sweeps  |  "
            f"{1 / first.dt_s:,.0f} Hz  |  channel {first.channel}"
        )
        self._updating = False
        self.sweep_changed()

    def invalidate(self):
        if self._updating:
            return
        self.results.clear()
        self.excluded.clear()
        self.export_button.setEnabled(False)
        self.table.setRowCount(0)
        self.summary.setText("参数已修改，请重新运行分析；手动排除已重置。")
        self.draw_trace()

    def config(self, index):
        return AnalysisConfig(
            **{k: v.value() for k, v in self.inputs.items()},
            excluded_peak_times_s=tuple(self.excluded.get(index, [])),
        )

    def run_analysis(self):
        if self.recording is None:
            return
        indices = (
            list(range(len(self.recording.traces)))
            if self.all_sweeps.isChecked()
            else [self.sweep.currentIndex()]
        )
        try:
            work = [(i, self.recording.traces[i], self.config(i)) for i in indices]
        except ValueError as exc:
            self.error(str(exc))
            return

        def done(results):
            self.results.update(results)
            self.sweep_changed()

        self.run_task(lambda: {i: analyze(trace, cfg) for i, trace, cfg in work}, done)

    def draw_trace(self):
        self.plot.clear()
        if self.recording is None or self.sweep.currentIndex() < 0:
            return
        index = self.sweep.currentIndex()
        trace = self.recording.traces[index]
        self.plot.plot(trace.time_s, trace.voltage_mv, pen=pg.mkPen("#547385", width=1))
        for key in ("start_s", "end_s"):
            self.plot.addLine(
                x=self.inputs[key].value(), pen=pg.mkPen("#9aa6ae", style=Qt.PenStyle.DashLine)
            )
        result = self.results.get(index)
        if result:
            self.plot.plot(
                [s.peak_time_s for s in result.spikes],
                [s.peak_mv for s in result.spikes],
                pen=None,
                symbol="o",
                symbolBrush="#e27836",
                symbolPen=None,
                symbolSize=8,
            )
            thresholds = [s for s in result.spikes if s.threshold_mv is not None]
            self.plot.plot(
                [s.threshold_time_s for s in thresholds],
                [s.threshold_mv for s in thresholds],
                pen=None,
                symbol="t",
                symbolBrush="#16817a",
                symbolPen=None,
                symbolSize=9,
            )

    def sweep_changed(self):
        self.draw_trace()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        result = self.results.get(self.sweep.currentIndex())
        if result is None:
            self.summary.setText("当前 sweep 尚未分析。请确认分析与基线区间。")
            self.messages.setPlainText(
                "基线应选择无放电、无刺激的区间。默认最初 10 ms，请自行确认。"
            )
        else:
            self.summary.setText(
                f"{len(result.spikes)} 个 AP  |  {result.summary['firing_rate_hz']:.3f} Hz  |  "
                f"基线 {result.summary['baseline_mv']:.2f} mV  |  "
                f"{result.summary['flagged_spike_count']} 个带质量提示  |  已分析 {len(self.results)} sweeps"
            )
            self.messages.setPlainText(
                "\n".join(result.warnings) or "无区间/采样警告；仍请复核检测标记。"
            )
            self.table.setRowCount(len(result.spikes))
            keys = [
                "peak_time_s",
                "threshold_mv",
                "amplitude_mv",
                "half_width_ms",
                "max_upstroke_mv_ms",
                "max_downstroke_mv_ms",
                "ahp_depth_from_threshold_mv",
            ]
            for row, spike in enumerate(result.spikes):
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked)
                check.setData(Qt.ItemDataRole.UserRole, spike.peak_time_s)
                self.table.setItem(row, 0, check)
                for col, key in enumerate(keys, 1):
                    value = getattr(spike, key)
                    item = QTableWidgetItem("—" if value is None else f"{value:.5g}")
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    self.table.setItem(row, col, item)
                flag_item = QTableWidgetItem("; ".join(spike.flags))
                flag_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, 8, flag_item)
        self.table.blockSignals(False)

    def toggle_spike(self, item):
        if item.column() == 0 and item.checkState() == Qt.CheckState.Unchecked:
            index = self.sweep.currentIndex()
            self.excluded.setdefault(index, []).append(item.data(Qt.ItemDataRole.UserRole))
            self.results.pop(index, None)
            self.run_analysis()

    def reset_exclusions(self):
        self.excluded.pop(self.sweep.currentIndex(), None)
        self.run_analysis()

    def zoom_spike(self, row, col):
        result = self.results.get(self.sweep.currentIndex())
        if result and row < len(result.spikes) and col != 0:
            center = result.spikes[row].peak_time_s
            self.plot.setXRange(center - 0.005, center + 0.025, padding=0)
            self.plot.enableAutoRange(axis="y")

    def export(self):
        if not self.results:
            return
        name = "neurospike_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "选择新的结果文件夹名称", str(Path.home() / name)
        )
        if path:
            results = [self.results[i] for i in sorted(self.results)]
            self.run_task(
                lambda: export_bundle(results, path),
                lambda output: self.messages.setPlainText(f"已导出：{output}"),
            )

    def closeEvent(self, event):
        if self.thread is not None:
            self.statusBar().showMessage("任务运行中，请等待结束后关闭。")
            event.ignore()
        else:
            self.executor.shutdown(wait=False)
            event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("NeuroSpike")
    app.setOrganizationName("NeuroSpike")
    window = MainWindow()
    window.show()
    return app.exec()
