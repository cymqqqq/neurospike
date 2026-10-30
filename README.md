# NeuroSpike

macOS 本地动作电位分析软件。面向电流钳 ABF 记录，支持诱发与自发放电的第一版参数统计。实验数据保留在本机，不连接云端分析服务，不修改原始记录。

## 已实现

- ABF1 / ABF2 读取，选择电压通道，切换和批量分析 sweep；CSV / TSV / TXT 可作补充输入。
- 交互波形缩放，峰值/阈值标记，逐个动作电位结果表，手动排除误检后重新统计。
- 事件数、区间平均发放率、峰值时间/电位、dV/dt 阈值、阈值到峰值幅度、半峰宽、阈值到峰值时间、最大上升与下降斜率、AHP 最低点和深度、ISI/瞬时频率、ISI 变异系数、末/首 ISI 比。
- 导出逐个动作电位与逐个 sweep 的 CSV、参数及源文件哈希 JSON、波形概览 PNG。
- 本地桌面界面和脚本批量分析两种入口，分析耗时操作在后台线程完成。

## 如何使用

### 已打包的 Mac 应用

使用与你的芯片和 macOS 版本相符的 `NeuroSpike.app`。双击即可使用，无需安装 Python。首轮打包以构建机器的架构为准，具体兼容性和实测情况见 [验证记录](docs/validation.md)。应用尚未进行 Apple Developer ID 签名或公证；macOS 可能要求在“隐私与安全性”中允许打开。

1. 打开程序后可先点“加载合成演示”，熟悉操作。
2. 点“打开 ABF / CSV”，选择 `.abf` 文件和单位为 mV/V/µV 的电压通道。
3. 选择 sweep。诱发记录将分析开始/结束设为刺激区间；自发记录设为希望统计的观察区间。软件不自动识别刺激开始和电流强度。
4. 基线选择没有刺激、放电和伪迹的一段记录。默认最初 10 ms，需要你核对。每个 sweep 的时间从该 sweep 的记录时间轴读取。
5. 先用默认峰值 −20 mV、突出度 20 mV、dV/dt 20 mV/ms、不应期 2 ms 运行，再根据实际波形调整；这些值不是所有细胞通用的标准。
6. 检查橙色峰值和绿色阈值。滚轮缩放、拖动平移，点击结果行放大；取消“保留”勾选可剔除伪迹。需要恢复时点“恢复当前 sweep 手动排除项”。当前版本不支持手动增加漏检事件，需调检测参数或时间段。
7. 可勾选“分析所有 sweep”。批量使用相同区间、参数，因此须确认每个 sweep 都适用。
8. 点“导出当前分析结果”，填写一个新的文件夹名称。不会覆盖既有结果。导出的是已分析的 sweep，CSV 包含完整指标。

界面改变测量参数后会清除旧结果和排除项，必须重新分析。切换 sweep 不会清除其他 sweep 结果。场景选择只提示如何设置区间，不暗中改变算法。

### 从源码安装（开发或未打包的平台）

需要 Python 3.11 或更高版本。以下命令在项目目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
neurospike-gui
```

依赖范围在 `pyproject.toml`，本次 macOS Python 3.12 的确切依赖快照见 `requirements-macos-py312.lock`。其他平台优先从项目声明安装，锁文件不承诺跨平台二进制兼容。

### 脚本分析

```bash
neurospike demo --output results/demo
neurospike analyze /path/to/cell.abf --channel 0 --start 0.1 --end 0.6 \
  --baseline-start 0 --baseline-end 0.05 --output results/cell
neurospike analyze /path/to/one.abf /path/to/two.abf --output results/batch
neurospike analyze /path/to/data.csv --time-unit ms --voltage-unit mV --output results/csv
```

所有时间区间单位为秒；`--refractory`、`--lookback`、`--ahp-window`、`--smooth` 为毫秒。`--dvdt` 为 mV/ms。默认不平滑。输出目录必须不存在。脚本批量遇到无效输入时整体失败，不悄悄跳过文件。

CSV 表头示例为 `time_s,sweep0_mV,sweep1_mV`：第一列时间，后续每列一个电压 sweep，共享时间轴。支持时间 s/ms 和电压 mV/V/uV；不能识别单位时拒绝猜测。每行必须完整，时间须递增且近似均匀采样。

## 如何理解结果

- `spikes.csv`：每行一个保留事件。空白代表无法测量，不是零；`flags` 提醒波形或测量不完整，带标记的事件仍计入统计，除非手动排除。
- `sweeps.csv`：每行一个 sweep，包括区间、基线、事件数、发放率和可测指标均值/有效数量。
- `analysis.json`：软件/方法/依赖版本、参数、排除峰值时间、区间、警告与输入 SHA256，可用于复核。导出包含本地路径，请在共享结果前自行检查。
- `review.png`：最多前 12 个 sweep 的概览，CSV 始终包含所有已分析 sweep。概览使用保留极值的降采样，不能替代原波形放大查看。

半峰宽、AHP、阈值等定义见 [参数定义](docs/measurement-definitions.md)。软件没有液接电位补偿、自动刺激伪迹识别、rheobase、输入电阻、膜电容或 f–I 曲线；没有采集硬件控制，不等同于完整 pCLAMP。当前对每个 sweep 单独汇总，未做细胞间组统计或显著性检验。

## 开发与自动检查

```bash
ruff check src tests scripts
ruff format --check src tests scripts
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m build
```

GitHub Actions 在 Linux 与 macOS 执行检查、无窗口 Qt 测试和 wheel 构建。macOS 额外打包并执行无窗口 smoke test，产物作为 Actions artifact 保存，不公开发布。工作流未配置凭证或生产部署。

本地打包：

```bash
python scripts/build_macos.py
```

项目模块与验收范围见 [设计记录](docs/implementation-plan.md)。本项目未授予开源许可证，GitHub 仓库保持私有。
