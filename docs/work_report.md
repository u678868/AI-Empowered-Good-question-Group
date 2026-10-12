# 工作报告：四张新流形、可配置距离策略与上游合并

**分支**：`codex/four-maps-integration`（已推送，tip = `bff80b6`）
**基线**：`origin/main` = `30dec65`（上游 playable v1 release）
**状态**：全部完成并验证；全量测试 **233 项通过**

本报告如实区分**本次工作**与**上游既有工作**，所有数字均为本仓库实测值，未测的东西不写成结论。

---

## 目录

1. [摘要](#1-摘要)
2. [背景与分工](#2-背景与分工)
3. [交付物](#3-交付物)
4. [上游合并与集成](#4-上游合并与集成)
5. [验证证据](#5-验证证据)
6. [诚实性与已知边界](#6-诚实性与已知边界)
7. [提交、产物与索引](#7-提交产物与索引)
8. [复现命令](#8-复现命令)
9. [后续建议](#9-后续建议)

---

## 1. 摘要

| 项目 | 结果 |
| :--- | :--- |
| 新增可玩地图 | **5 张**（克莱因瓶 + 打结环面 + 瓶形克莱因瓶 + 椭圆曲线 + 射影平面），注册总数 5 → **9** |
| 新增流形模型 | 4 个（`KnottedTorus` / `BottleKleinBottle` / `EllipticCurveTorus` / `ProjectivePlane`），全部解析一二阶偏导 |
| 引擎扩展 | 1 处语义扩展：可配置距离策略 `WorldConfig.distance_mode`（默认保持原行为） |
| 契约升级 | chart 副本由内核数据驱动下发（`chart_copy_transforms` → `chart_copies`） |
| 修复缺陷 | **3 个**（上帝视角切图不刷新、合并后 `hideCard` 未定义、`sync_position` 的 2π 硬折回） |
| 测试 | 全量 **233 项通过**（本次两轮共新增 48 项：克莱因瓶 17 + 四张新地图 31；上游新增 26 项；仓库基线 159 项） |
| 文档 | README 新增两大章节 + 编号说明；architecture / contributing_extensions 更新；3 份 ai-log |
| 集成 | 拉取并合并上游 release（7 处冲突全部保留双方特性，无内容丢失） |
| 上传 | 分支 `codex/four-maps-integration` 已推送（未推 `main`，遵循仓库约定） |

---

## 2. 背景与分工

### 2.1 需求序列

1. 连接仓库 `u678868/AI-Empowered-Good-question-Group`
2. 通读并梳理项目功能
3. 新增克莱因瓶关卡
4. 修复"上帝模式下克莱因瓶 3D 图不绘制"
5. 新增打结环面、瓶形克莱因瓶、复分析黎曼曲面、RP² 对跖世界（距离定义单独配置，其它不改）
6. 拉取并合并远程仓库
7. 上传

### 2.2 与上游的分工（重要）

上游 `main` 的 **Task 17 / 18 / 19** 指「等比缩放与三阶难度」「几何印记任务引擎」「绳索与量具工具链」，是**另一条并行工作线**；本分支的 **Task 17 / 18** 指「克莱因瓶关卡」「四张新地图」。两边编号重名，合并后已在 README 加注说明，并把本次日志从 `task18_report1.txt` 更名为 `four_maps_report1.txt`。

| 归属 | 内容 |
| :--- | :--- |
| **上游** | 缩放/难度/计分、任务引擎与出口封印、流形扫描器、绳索与复合量具、Web 工具链重构 |
| **本次工作** | 5 张新地图、距离策略、chart 副本契约、3 个缺陷修复、上游合并与集成验证 |

---

## 3. 交付物

### 3.1 克莱因瓶关卡 `klein_bottle`

**模型**：经典 figure-8 浸入（R³ 中克莱因瓶**不可能嵌入**，只能浸入）

```
P(u, v) = R + t ( cos(u/2) sin v - sin(u/2) sin 2v )
Q(u, v) = t ( sin(u/2) sin v + cos(u/2) sin 2v )
r(u, v) = ( P cos u, P sin u, Q )          # R = 90, t = 31
```

利用手推恒等式 `P_u = -Q/2`、`Q_uu = -Q/4`，全部偏导解析；运行时零数值差分。

| 检查 | 实测 |
| :--- | :--- |
| 正则性（真浸入） | `min(EG−F²) ≈ 1.27e6`，退化点比例 **0** |
| 解析偏导 vs 中心差分 | 一阶 **< 2.1e-8**，二阶 **< 2.4e-6** |
| 必然自交 | `r(u,0) = r(u,π) = (R cos u, R sin u, 0)`，两处切平面横截 |
| 不可定向 | `n(u+2π, v) = -n(u, -v)`，误差 ~2.8e-16（无全局"外侧"） |
| 高斯-博内 | χ=0 ⇒ ∬K dA = **0.0000** |
| 表面积（数值） | ≈ 1.66e5 |

**工程重点：chart 周期不是 2π × 2π。** `r(u+2π, v) = r(u, -v)`——u 平移 2π 会**镜像 v**，若按旧逻辑独立折回 `[-π,π)`，玩家每跨一次缝局部图就整体镜像一次。为此把"chart 如何识别自己的点"收敛为 manifold 公开接口：

| 接口 | 环面族 | 克莱因瓶 |
| :--- | :--- | :--- |
| `chart_periods()` | `(2π, 2π)` | `(4π, 2π)` |
| `wrap(u, v)` | 独立折回 | 按 4π/2π 折回（纯平移，不可见） |
| `chart_copies()` | 1 份 | 2 份（同一三维点） |
| `chart_relative()` | ≈ `wrap_difference` | 在两份中挑最近的 |

连续移动实测：沿 u / v / 对角各走 400 步，坐标恒在 `[-2π,2π) × [-π,π)`，`clamped` 恒 False，单步三维位移 ≤ `|r_u| × 步长`（无瞬移）。

### 3.2 四张新地图

#### (1) 打结环面 `knot_garden` —— 拓扑平凡，嵌入不平凡

管道沿 (2,3) 环面结走，用载环面自身的正交标架（外法向 `N`、`phi` 切向 `E`）造管：`r = K + ρ(cos v N + sin v E)`。标架不做法向归一化，偏导全部初等。

| 事实 | 实测 |
| :--- | :--- |
| 拓扑 | 仍是**环面**：可定向、χ=0、∬K dA = **−3.6e-15** |
| 正则性 | `min(EG−F²) = 36864`，退化点 0 |
| 解析偏导误差 | 一阶 1.4e-8，二阶 1.3e-5 |
| 嵌入性 | 构造期校验 `ρ < 股距/2`；股间中心距 20.0（=2a），取 ρ=8 |
| 玩法核心 | 两股表面最近约 **12.0**，沿曲面却要走半圈（≈200）；`detector_scale = 30` ⇒ 探测器对两股读数几乎相同 |

#### (2) 经典瓶形克莱因瓶 `klein_bottle_traditional`

采用维基百科 action=raw 源码中的官方"瓶子"参数化（不再依赖记忆），并重参数化 `U = 2u, w = v − π/2` 使其满足 `r(U+2π, w) = r(U, −w)`。偏导由轮廓多项式字典经 `_poly_derivative` **符号求导**后按 `1/2^k` 缩放。

| 事实 | 实测 |
| :--- | :--- |
| 与公开公式一致性 | 与逐字抄写的参考实现最大偏差 **8.9e-16** |
| 正则性 | `min(EG−F²) = 0.0094`（scale=1 实测；该量按尺度²缩放，scale=30 时 7599） |
| χ=0 | ∬K dA ≈ **0**（实测 −2.3e-16 ~ −3.4e-16，机器精度） |
| 必然自交 | 参数相距 2.18 的两点三维重合（脖子穿过瓶身），误差 < 0.01 |
| 与 figure-8 的关系 | 正则同伦类：figure-8 **手性**、瓶形**非手性**，两者覆盖三类中的两类 |

#### (3) 椭圆曲线 `elliptic_curve` —— 复分析的黎曼曲面

世界是 **Clifford 环面的球极投影**（环:管 = √2:1），球极投影共形，故这是 ℂ/(ℤ+iℤ) 的**共形模型**。

| 事实 | 实测 |
| :--- | :--- |
| 共形周期 | `W = ∫ r dv/(R+r cos v)` 与解析式 `2πr/√(R²−r²)` 相对误差 **0** |
| 共形模数 | `τ = i·r/√(R²−r²)`；R/r = √2 时 **τ = i**（正方形格） |
| 交叉验证 | (3,1) → 0.353553i、(5,2) → 0.436436i，公式与数值积分逐位一致 |
| 拓扑 | χ=0、∬K dA = 3.1e-15、`min(EG−F²) = 5.9e5` |
| 玩法 | 胖管窄孔（孔/管 = 0.414），三维近邻极多 |

#### (4) 实射影平面 `projective_plane` —— 对跖世界

椭球 chart 本就双重覆盖球面，再商掉对跖映射：`r(u+π, π−v) = −r(u, v)`。前提是径向调制**关于 v 偶且关于 π/2 对称**（即 `cos(2k v)`），否则商空间不是 RP² ⇒ 构造期报错。

| 事实 | 实测 |
| :--- | :--- |
| chart 层数 | **4 层** → 折叠成 **2 个互为对跖的三维实现** |
| 高斯-博内 | RP² 自身 χ=1 ⇒ 2π；chart 覆盖 4 份 ⇒ 原始积分 25.1168 ≈ 8π = 25.1327 |
| 不可嵌入 | chart 映射是 2 对 1 到椭球的**覆盖映射**（不自交） |

**距离定义单独配置**（本任务唯一引擎改动）：

| `distance_mode` | 含义 | 使用者 |
| :--- | :--- | :--- |
| `"euclidean"`（默认） | 两个三维实现之间的直线距离 | 其余**全部**地图（行为逐位不变，有逐图回归测试） |
| `"orbit_min"` | 对双方 chart 副本取最小 | 仅 `projective_plane` |

实测：出口与其对跖 chart 点世界距离 **0.0**（同一处），三维相距 **84.6**；探测器在两处读数都是 **1.000000**；从任一实现 `sync_position` 均判定胜利。

### 3.3 chart 副本契约升级（数据驱动）

原前端把翻转孪生坐标写死为 `(u+2π, −v)`；RP² 有 4 层、瓶形克莱因瓶扭转不同，写死不再成立。现在内核下发：

```
"chart_copies":  [[du, dv, flip_v], ...]
"chart_periods": [p_u, p_v]
```

前端 `chartCopies()` 直接照抄、`chartDelta()` 在副本中取最近——因此"对跖点落在玩家脚下"这类 RP² 语义在前端自动正确。

### 3.4 缺陷修复

#### (a) 上帝视角切图后不刷新（用户报告"克莱因瓶 3D 图没绘制"）

**根因**：`setGodView(true)` 在"已处于该状态"时只重绘**缓存**的 `state.debugState`，从不重新请求 `/api/state/debug`；而 `/api/session/new` 已重建世界。

**证据**（无头浏览器，planar_landscape → klein_bottle）：切换后画布像素与切换前**逐位相同**（包围盒 `155,604,179,340`，37093 像素），而当前会话模型已是 figure-8 Klein bottle。

**修复**：新增 `refreshGodView()`（**总是**重新请求再重绘）；`setGodView`/`toggleGodView` 复用；`enterWorld` 清空 `state.debugState`。

**顺带修正可见性**：上帝画布改用 `frameCanvas`（按 CSS 尺寸 × DPR 绘制，原先固定 760×520 被拉伸到约 1400px 而模糊）；画布改 1000×500 并 `max-width: 1000px`；投影填充系数 0.42 → 0.68；按 G 时 `scrollIntoView`。回归：切换后绘制包围盒 = 当前会话投影包围盒 `163,832,136,358`，`scrollY = maxScroll`。

#### (b) 合并后 `hideCard is not defined`（用户报告"无论选什么都会提示"）

**根因**：上游 release 删除了工具栏/结果卡 UI（连同 `hideCard`），而冲突解决时保留了本分支对 `hideCard()` 的调用 ⇒ `enterWorld()` 必抛异常，故"选什么都会报"。

**修复**：删除该调用（保留 `state.debugState = null`）。

**验证方式升级**（承认原先只做语法检查不够）：新增 node 侧**静态扫描**（提取所有被调用标识符与定义比对，现仅剩字符串字面量误报）；并用无头浏览器跑真实流程——进入世界 / 快捷槽 1-5 / 上帝视角 / Esc / 重开大厅换图重进，**三次运行 0 报错**。

#### (c) `sync_position` 的 2π 硬折回（合并引入的语义接缝）

上游新增的 `sync_position` 用 `wrap_parameter(du)` 按 2π 折回增量：克莱因瓶 u 周期是 **4π**、射影平面有 **4 层** chart ⇒ 语义错误。改为向 chart 要最近代表（`chart_relative`），保留原兜底分支。

---

## 4. 上游合并与集成

### 4.1 过程

1. **先保护本地工作**：把本次改动提交到 `codex/task17-task18-maps`（`c8ff1f3`）
2. `main` 快进到 `origin/main`（`604efa3` → `30dec65`）
3. 合并本地分支 ⇒ `241cb66`，**7 处冲突**全部按"双方特性都保留"解决

### 4.2 冲突与解决

| 文件 | 冲突 | 解决 |
| :--- | :--- | :--- |
| `config.py` | 上游 `scale_factor`/`difficulty` 默认值 vs 本分支 `distance_mode` | 都保留（并修掉合并把模块常量夹进类体导致的 `IndentationError`） |
| `maps/__init__.py` | 上游 `genus` vs 本分支 `non_orientable` | 字段、装饰器参数、`to_dict` 三处同时保留 |
| `gameplay.py` | 上游出口封印/难度判定 vs 本分支距离策略 | 用**世界距离策略**算距离 + 保留封印逻辑与 `effective_capture_radius` |
| `obstacles.py` | 上游 1/S 物理缩放 vs 本分支距离策略 | 半径/边距按 1/S，散布与碰撞按策略 |
| `server.py` | 上游 quest/ropes/scoring 载荷 vs 本分支 `chart_copies` | 都保留 |
| `web/app.js` | 上游 `project`/hitNodes vs 本分支 `chartDelta` 投影 | 用 `chartDelta` + 保留命中列表；上帝视角刷新修复保留 |
| `README.md` | 双方各自新增的大段章节 | 都保留 + 编号说明；本次日志更名避免与上游 Task 18 混淆 |

### 4.3 合并后完整性核查

- 上游 **28** 个章节标题、本分支 **27** 个，合并后 **30** 个，**双向均无缺失**
- 上游 151 条表格行中仅 **3** 条不同，且均为**有意的更新**（地图目录 4→9、`obstacles.py` 行补距离策略、`manifold.py` 行列出新模型）——**不是丢失**
- 上游 26 项新测试全部通过；无头浏览器流程 0 报错

---

## 5. 验证证据

### 5.1 测试规模演进

| 阶段 | 通过数 | 说明 |
| :--- | :--- | :--- |
| 任务开始（仓库原状） | **159** | 上游 Task 16 之后的基线 |
| 克莱因瓶关卡后 | **176** | 本次第一轮新增 17 项 |
| 四张新地图后 | **207** | 本次第二轮新增 31 项 |
| 合并上游后 | **233** | 上游新增 26 项 |

本次新增测试文件（共 48 项）：`test_klein_bottle.py`(17)、`test_knotted_torus.py`(8)、`test_bottle_klein.py`(8)、`test_projective_plane.py`(8)、`test_elliptic_curve.py`(7)。

### 5.2 数学一致性实测汇总

| 地图 | χ | 实测 ∬K dA | 理论值 | 偏导误差（一阶/二阶） |
| :--- | :--- | :--- | :--- | :--- |
| `torus_genus1` | 0 | ~1e-15 | 0 | 沿用 |
| `klein_bottle` | 0 | **0.0000** | 0 | 2.1e-8 / 2.4e-6 |
| `knot_garden` | 0 | **−3.6e-15** | 0 | 1.4e-8 / 1.3e-5 |
| `klein_bottle_traditional` | 0 | **−3.4e-16** | 0 | 与公开公式 8.9e-16 |
| `elliptic_curve` | 0 | **3.1e-15** | 0 | 沿用（τ=i 另证） |
| `projective_plane` | 1 | 25.1168（chart，4 份） | 8π = 25.1327 | 沿用 |

### 5.3 浏览器与端到端

| 验证 | 结果 |
| :--- | :--- |
| 四张新地图（无头 Edge，各一次） | 局部地图 ≈30 万像素、上帝视角 7–13 万像素、模型/副本数正确、0 报错 |
| 合并后完整流程（3 种配置 + 重进大厅换图） | **0 报错**；god 模式上帝视角 11.9 万像素，player 模式正确显示"不可用" |
| 服务器端到端 | 9 张地图；`genus` 与 `non_orientable` 并存；载荷同时含 `chart_copies/chart_periods/twisted/orientable` 与 `scale_factor/difficulty/detector_locked/quest/ropes/score`；**无出口泄露** |
| 前端契约（node，真实 payload 逐图） | 环面/打结环面/椭圆曲线 1 层、两个克莱因瓶 2 层、RP² 4 层；对跖副本识别为零位移且真实异点不被折叠 |

---

## 6. 诚实性与已知边界

本项目的判定标准是"未测的不写成功"。以下限制均写入代码文档、README 与测试，而非隐藏：

| 地图 / 主题 | 如实标注的内容 |
| :--- | :--- |
| 克莱因瓶（两个浸入） | R³ 中**不可能嵌入**，必然自交；**无全局外侧**；自交圆上两个不同曲面点三维重合，环境距离探测器**无法区分**；自交圆两侧约 0.074 薄带内可能出现"看不见却被挡/穿过去" |
| 打结环面 | 结属于**嵌入**而非拓扑（χ 仍为 0）；两股表面最近约 12 而 `detector_scale = 30`，读数几乎相同——这是设计意图 |
| 椭圆曲线 | 只是**共形**模型、非等距嵌入（R³ 中不存在完备平坦闭曲面，Hilbert）；"复分析"体现在共形结构，而紧黎曼曲面上不存在非常值全纯函数 |
| 射影平面 | 距离必须取轨道最小（`orbit_min` 仅此图开启）；chart 覆盖 4 份，原始积分是 8π 而非 2π |
| 真亏格 2 | 仍为**外观近似**（`double_torus` 实为亏格 1 像）；真亏格 2 需亏格 2 参数域或隐式曲面引擎 |
| Möbius / Boy 曲面 | 未实现：前者需带边界流形支持，后者（RP² 无 pinch point 浸入）参数化与求导成本高 |
| 编号重名 | 上游与本分支各自使用 "Task 17/18"，已在 README 加注并以文件名区分 |

---

## 7. 提交、产物与索引

### 7.1 提交（分支 `codex/four-maps-integration`，相对 `origin/main`）

| 提交 | 内容 |
| :--- | :--- |
| `c8ff1f3` | 四张新流形 + 可配置距离策略 + chart 副本契约（31 项新测试） |
| `241cb66` | 合并 `codex/task17-task18-maps` 到 main（7 处冲突全保留） |
| `c411009` | 为两张可定向新图声明 `genus=1`（不可定向者保持 `None` + `non_orientable`） |
| `bff80b6` | 修复 `hideCard is not defined` |

### 7.2 新增/修改文件（相对 `origin/main`：27 files, +3597 / −798）

| 类别 | 文件 |
| :--- | :--- |
| 流形内核 | `src/the_curved_world/manifold.py`（+848） |
| 距离策略 | `config.py`、`geometry.py`、`world.py`、`detector.py`、`gameplay.py`、`obstacles.py`、`server.py` |
| 地图注册 | `maps/__init__.py`、`maps/builtin.py`（+105） |
| 前端 | `web/app.js`（+113/−30）、`web/index.html`、`web/style.css` |
| 测试 | `test_klein_bottle.py`、`test_knotted_torus.py`、`test_bottle_klein.py`、`test_elliptic_curve.py`、`test_projective_plane.py` + 3 个既有测试更新 |
| 文档 | `README.md`、`docs/architecture.md`、`docs/contributing_extensions.md`、`DEMO_LINK.md`、本报告 |
| 日志 | `ai-logs/klein_report1.txt`、`ai-logs/four_maps_report1.txt`、`ai-logs/merge_report1.txt` |

### 7.3 文档索引

- 总报告：本文（`docs/work_report.md`）
- 关卡细节与实测：`README.md` 的 Task 17 / Task 18 两节
- 分层与契约约束：`docs/architecture.md`（chart 折回、chart 副本、距离策略三条硬约束）
- 扩展新地图的方法：`docs/contributing_extensions.md`
- 工作日志：`ai-logs/klein_report1.txt`、`ai-logs/four_maps_report1.txt`、`ai-logs/merge_report1.txt`

---

## 8. 复现命令

```powershell
# 环境
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

# 测试（全量 233 项）
.\.venv\Scripts\python.exe -m pytest

# 新地图
.\.venv\Scripts\python.exe -m src.main --play  --map klein_bottle --seed 12345
.\.venv\Scripts\python.exe -m src.main --play  --map knot_garden --seed 12345
.\.venv\Scripts\python.exe -m src.main --play  --map klein_bottle_traditional --seed 12345
.\.venv\Scripts\python.exe -m src.main --serve --map elliptic_curve --debug
.\.venv\Scripts\python.exe -m src.main --serve --map projective_plane --debug
# 浏览器打开 http://127.0.0.1:8000/

# 关键单测
.\.venv\Scripts\python.exe -m pytest tests/test_klein_bottle.py tests/test_knotted_torus.py `
    tests/test_bottle_klein.py tests/test_elliptic_curve.py tests/test_projective_plane.py
```

---

## 9. 后续建议

按"性价比"排序：

1. **Möbius 带**：给定 chart 契约后成本已很低，只需补"带边界流形"支持（顺带换来环带/圆盘世界），并可用高斯-博内带边界形式 `∬K dA + ∮k_g ds = 2πχ` 做诚实测试。
2. **真亏格 2**：需要隐式/SDF 引擎（marching cubes + 隐函数曲率闭式 + 最近点投影 chart），一次性解锁任意亏格与连通和。
3. **更多结型与缠绕环面**：`KnottedTorus` 已参数化 (p,q)，只需注册新条目即可扩成"结园"系列。
4. **Boy 曲面**：RP² 的无 pinch point 浸入，能"看得见自交"，但参数化与解析偏导成本最高。
5. **按种子的闭流形形变**：目前闭流形按种子原样使用；环面可直接加谐波，克莱因瓶/RP² 需保持 chart 对称性（否则商空间不成立）。
