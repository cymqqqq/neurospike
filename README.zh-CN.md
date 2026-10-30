# NeuroSpike

[English](README.md) | **简体中文**

面向电流钳记录的 Python 动作电位分析项目，支持诱发放电和自发放电。读取 pCLAMP ABF 数据，输出测量结果、质量标记、复现元数据和波形复核图。

## 推荐方式：提供数据，获得分析结果

你提供记录文件或可访问的文件路径，并说明需要哪些指标。AI 编程代理使用本仓库的 Python 代码检查数据、执行计算、复核质量，最后交付所需结果。当代理所在环境能访问数据和仓库时，你无需写代码、安装 Python 或打开桌面软件。

本仓库提供计算代码，尚未提供托管聊天服务、文件上传网站或自主运行的大模型后端。能访问仓库不代表已经取得你的实验数据；代理还需要能执行代码的环境，以及你提供的数据访问权限。

在已配置的 Codex 环境中，可以使用单独安装的个人技能 `$software-engineer`。该技能未随本仓库分发。请求示例：

```text
请使用 neurospike 的 Python 代码分析这些 ABF 数据。
统计动作电位数量、发放率、阈值、幅度、半峰宽、最大上升/下降速率和 AHP 深度。
分析区间为 0.1–0.6 秒，基线区间为 0–0.05 秒。
请交付结果表、必要的波形复核图和简短解释。
保留 Qt 界面，暂不继续界面开发。
```

这里的区间只是示例，应按真实实验协议选择。若不确定刺激区间或基线，可以让代理先检查记录和可用元数据。需要跨记录汇总时，请提供细胞/动物编号和分组对应关系。

代理应以真实 Python 输出作为数值依据，记录代码版本与参数，说明失败文件和不确定的测量，不能把同一细胞的多个 sweep 当作独立生物学重复。实验数据和结果默认不上传 GitHub；对话平台如何处理数据取决于实际平台和执行环境。

## 项目状态

当前优先发展 Python 分析内核、命令行入口和分析脚本。已有 Qt/PySide6 桌面界面保留；暂停新增界面功能和例行手动应用打包，直到明确要求恢复。已有 CI 测试和 macOS 打包工作流继续保留，推送后仍可能自动生成应用产物。

本次文档更新不改变分析算法，也不移除桌面功能。

## 已支持的分析

- 读取 ABF1、ABF2，选择电压通道，分析单个或多个 sweep；补充支持 CSV、TSV 和带表头的 TXT。
- 测量动作电位数量、区间发放率、峰值时间/电位、dV/dt 阈值、阈值到峰值幅度、半峰宽、阈值到峰值上升时间、最大上升/下降速率，以及 AHP 最低点的时间/电位/深度。
- 输出 ISI、瞬时频率、ISI 变异系数和末/首 ISI 比。
- 导出逐事件与逐 sweep 的 CSV、带源文件哈希的 JSON 元数据及 PNG 概览图。
- 无法可靠测量时保留缺失值和质量标记。Python API 支持显式排除检测峰值，保留的 Qt 界面也提供排除操作。

默认设置为最低峰值 −20 mV、突出度 20 mV、dV/dt 阈值 20 mV/ms、最小峰间隔 2 ms，默认不平滑。必须结合细胞类型与实验协议检查这些设置是否适用。

## 结果与解释

- `spikes.csv`：每行一个保留事件。空白表示无法测量，不是零；质量标记不会自动剔除事件。
- `sweeps.csv`：每行一个已分析 sweep，包含分析区间、基线、数量、发放率及各指标均值和有效数量。
- `analysis.json`：软件/方法/依赖版本、参数、排除峰值时间、警告、汇总和输入 SHA256。包含本地路径，共享前应检查。
- `review.png`：最多前 12 个已分析 sweep 的概览，CSV 始终包含所有已分析 sweep。长记录使用保留极值的降采样，不能替代详细波形复核。

当前内置导出记录软件和方法版本，尚不自动记录 Git commit。代理执行分析时应额外保存仓库提交号、影响计算的未提交修改或脚本快照、环境及执行信息。

半峰宽取 dV/dt 阈值电位与峰值电位之间一半幅度处的宽度；AHP 同时报告相对阈值和基线的深度。首峰潜伏期相对所选分析起点计算，不是自动识别的刺激起点。完整方法见 [测量定义](docs/measurement-definitions.md)。

## Python 执行参考

以下命令供代理或开发者运行分析。采用推荐方式的用户无需自行执行。

### 环境准备

需要 Python 3.11 或更高版本，在仓库根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

依赖声明见 `pyproject.toml`。当前安装依赖仍包含 Qt，但命令行分析无需打开界面。`requirements-macos-py312.lock` 是最初 macOS/Python 3.12 验证环境的确切快照，不保证跨平台二进制兼容。

### 命令行分析

```bash
neurospike demo --output results/demo
neurospike analyze /path/to/cell.abf --channel 0 --start 0.1 --end 0.6 \
  --baseline-start 0 --baseline-end 0.05 --output results/cell
neurospike analyze /path/to/one.abf /path/to/two.abf --output results/batch
neurospike analyze /path/to/data.csv --time-unit ms --voltage-unit mV --output results/csv
```

无界面运行时必须显式使用 `analyze` 或 `demo` 子命令；直接运行 `neurospike` 会启动保留的 GUI。目前 CLI 提示和界面标签为中文；默认英文 README 不会改变应用语言。

分析区间和基线区间单位为秒；`--refractory`、`--lookback`、`--ahp-window`、`--smooth` 单位为毫秒，`--dvdt` 为 mV/ms。ABF 通道从 0 开始。输出目录必须不存在。多文件调用遇到无效输入时整体失败，不悄悄跳过文件。共用区间和参数必须适用于每个选中的 sweep。

### Python API

```python
from neurospike.analysis import AnalysisConfig, analyze
from neurospike.export import export_bundle
from neurospike.io import load_recording

recording = load_recording("/path/to/cell.abf", channel=0)
config = AnalysisConfig(
    start_s=0.1,
    end_s=0.6,
    baseline_start_s=0.0,
    baseline_end_s=0.05,
)
results = [analyze(trace, config) for trace in recording.traces]
export_bundle(results, "results/cell")
```

CSV 表头可用 `time_s,sweep0_mV,sweep1_mV`：第一列时间，后续每列为共享该时间轴的电压 sweep。支持时间 s/ms、电压 mV/V/uV；不能识别单位时，除非显式指定，否则拒绝猜测。数据必须完整且为有限数值，时间严格递增并近似均匀采样。

## 保留的桌面界面

已有桌面使用方式仍可通过 `neurospike-gui` 打开，支持文件/通道/sweep 选择、分析和基线区间设置、波形缩放、峰值/阈值标记、事件剔除与恢复、批量 sweep 分析和结果导出。改变测量参数后会清除旧结果和排除项；批量分析共用设置。暂不支持手动补加漏检事件。

已有 `NeuroSpike.app` 需要匹配的 macOS 版本与架构。最初本地包为 x86_64，已在 macOS 14.3.1、M1 Pro 的 Rosetta 环境测试；没有 Apple Developer ID 签名和公证。详细情况见 [验证记录](docs/validation.md)。当前桌面开发暂停。

## 范围与验证限制

当前分析对象为电流钳电压记录。项目不控制采集硬件，尚未覆盖完整 pCLAMP 功能；未实现刺激电流自动解析、刺激伪迹自动识别、液接电位校正、rheobase、输入电阻、膜电容、f–I 曲线及细胞/组级统计检验。

首版通过 37 项自动测试、已知波形测量、ABF1 往返读取、公开 ABF2 读取及无窗口 Qt/导出检查。公开 ABF2 的事件数是程序运行结果，没有人工标注真值；尚未用用户实验室数据与人工标注或 Clampfit 逐事件对照。科学解释前应复核代表性 sweep，并采用一致方法。

## 开发检查

```bash
python -m pip install -e '.[dev]'
ruff check src tests scripts
ruff format --check src tests scripts
QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg python -m pytest -q
python -m build
```

[GitHub Actions](https://github.com/cymqqqq/neurospike/actions) 在 Linux、macOS 执行检查和测试；已有 macOS 任务还会打包应用，无窗口验证 ABF 读取与 CSV/JSON/PNG 导出，并保存 Actions artifact，不公开发布 Release 或部署服务。

模块职责和首版验收范围见 [设计记录](docs/implementation-plan.md)。该文件描述最初以桌面为主的版本，当前以直接分析为主的方向以本 README 为准。仓库保持私有，未授予开源许可证。
