> **Submission note.** This folder is the packaged hackathon submission.
> `AGENTS.md` is a local collaboration contract and is intentionally not shipped;
> mentions of it below are historical. See `DEMO_LINK.md` for the exact
> reproduction steps (create a venv, install the requirements, run the tests,
> then start the web session).

# The Curved World

> 一个数学探索原型：玩家在一块嵌入三维欧氏空间的**光滑曲面**上移动，用**距离敏感探测器**（只能读到信号强弱）寻找隐藏出口。

本目录遵循 `AGENTS.md` 的协作规范与安全边界。实现进度以本文件「功能状态表」为准，未完成项均如实标注。

## 赛题背景与竞品对比

**赛题背景**：多数“探索类”游戏把世界当成**平面**或**规则网格**，玩家天然拥有全局地图，
“找路”退化成读坐标。本作品把世界换成**嵌入三维欧氏空间的光滑曲面 / 封闭流形**，
玩家只拿到一个**距离敏感探测器**与一张**局部切空间视图**，必须靠测量与推理重建空间结构，
把“非欧几何”变成可玩的核心机制。

**竞品对比（如实描述，不做夸大）**

| 对比对象 | 常见做法 | 本项目 |
| :--- | :--- | :--- |
| 常规 3D 游戏小地图 | 欧氏平面地图 + 直接给出坐标/朝向 | 局部切空间视图 + 几何迷雾，网格按第一基本形式畸变 |
| 专业曲面可视化（ParaView / Blender 等） | 全知视角，专业操作门槛 | 玩家视角 + 信息受限 + 探测器信号，另有开发者全知视图 |
| 地图 / 导航类应用 | 固定平面投影，不考虑曲率 | 封闭可环绕流形，曲率与测地三角可实测 |
| 数学教学演示 | 静态图像 / 动画 | 可交互行走 + 高斯-博内测量仪 + 解析微分几何内核 |

需要说明：本项目是**光滑曲面 + 环境欧氏距离探测器**的数学探索原型，
不是完整的非欧几何物理仿真，也不以画面表现力为目标。

## 项目目标

在一块光滑二维曲面上放置一个隐藏出口。玩家唯一的线索是一个**距离敏感探测器**：越靠近出口信号越强，但探测器**不告诉**玩家精确距离、出口坐标或方向。玩家靠移动、比较信号、做标记来定位出口。

> **范围声明**：本版本实现的是**嵌入普通三维欧氏空间的光滑曲面** + **基于环境欧氏距离的探测器**；它**不是**完整的非欧几何物理仿真。

## 数学模型

世界是一张**图曲面**，嵌入普通三维欧氏空间：

```
S = { (x, y, f(x, y)) : (x, y) in D }
```

`D` 是有界矩形参数域，`f` 是光滑高度函数（本原型 = 一个正弦波 + 若干高斯丘，全部 C-infinity）：

```
f(x, y) = A*sin(kx*x)*cos(ky*y)
        + sum_i h_i * exp( -((x-cx_i)^2 + (y-cy_i)^2) / s_i^2 )
```

- 系数、中心、尺度可配置（`src/the_curved_world/config.py`）。
- 偏导数**解析求解**（非数值差分）。
- 玩家位置在**参数空间** `(x, y)` 表示，三维坐标恒由 `(x, y, f(x, y))` 导出，玩家**永远在曲面上**。

### 距离定义（重要）

探测器使用的距离是**环境欧氏距离**：

```
d_E(P, Q) = ||P - Q||_2        （三维空间中的直线距离）
```

**这不是**沿曲面行走的**测地线距离**（geodesic distance），后者不在本项目范围内。对弯曲曲面：环境距离 <= 测地线距离。

### 探测器模型

```
signal = exp( -d_E / scale )，  scale > 0
```

信号有界于 `(0, 1]`，**距离越小信号越强**（严格单调），确定性、无噪声。默认 `scale = 25`（与 100x100 世界尺度匹配：`Weak/Moderate/Strong` 的分界约在 d≈27.7 / d≈10.4）。

## 玩法与控制

```powershell
.\.venv\Scripts\python.exe -m src.main                          # 终端游戏（默认种子 12345）
.\.venv\Scripts\python.exe -m src.main --seed 42                # 指定种子
.\.venv\Scripts\python.exe -m src.main --demo                   # 只打印开发者摘要
.\.venv\Scripts\python.exe -m src.main --demo-scenario          # 可复现完整 Demo（固定种子 12345）
.\.venv\Scripts\python.exe -m src.main --render                 # 终端游戏 + Matplotlib 3D 玩家视图
.\.venv\Scripts\python.exe -m src.main --render --view debug    # 终端游戏 + 开发者视图
.\.venv\Scripts\python.exe -m src.main --play --view player     # 交互式实时游玩（Task 5，实时就地重绘）
.\.venv\Scripts\python.exe -m src.main --serve --port 8000      # Web 双视角界面 + 本地 JSON API（Task 6）
.\.venv\Scripts\python.exe -m src.main --serve --debug          # 同上，并启用特权 /api/state/debug
```

| 命令 | 作用 |
| :--- | :--- |
| `move <dx> <dy>` | 沿方向 (dx,dy) 移动**固定一步**；方向会被归一化，**对角不会更快** |
| `w` / `a` / `s` / `d` | 快捷移动一步：w=+y / s=-y / a=-x / d=+x（另保留 n=+y、e=+x） |
| `scan [note]` | 原地取一次探测器读数并写入探索日志（别名 `read`） |
| `mark <name>` | 在当前点放置命名标记 |
| `markers` | 列出所有标记 |
| `log` | 显示探索日志 |
| `measure <a> <b>` | 测两个**标记点**之间的环境欧氏（直线 3D）距离 |
| `curvature` | 当前位置的**高斯曲率** K（解析计算） |
| `status` | 显示当前位置、步数、读数与标记数量 |
| `view player` / `view debug` | 切换渲染视图（玩家 / 开发者） |
| `seed <n>` / `new [seed]` | 用指定种子重开 / 开新世界 |
| `help` / `quit` | 帮助 / 退出 |

**探索循环**：移动 -> 读信号 -> 比较升降 -> 放标记 / 量距离 -> 决定下一步 -> 靠近出口触发胜利。胜利摘要含：读数次数、标记数、步数、模拟时间、种子。

**移动模型**：参数空间移动，每步后重算曲面高度；坐标被**钳制在参数域内**（越界时贴边并标注 `clamped`）。**不是**测地线运动或物理真实行走。

## 3D 可视化与视图模式（Task 3）

加上 `--render` 后，每次命令执行完都会刷新 3D 图。游戏中可用 `view player` / `view debug` 随时切换。

| 视图 | 显示 | 不显示 |
| :--- | :--- | :--- |
| **玩家视图**（默认） | 曲面、玩家位置、探索轨迹、玩家标记、当前信号/步数统计 | 出口位置、到出口的连线、精确距离、隐藏距离热力图 |
| **开发者视图**（需显式开启） | 上述全部，**加上**：起点、隐藏出口、玩家 3D 坐标、到出口的真实距离、种子与曲面参数 | — |

**设计要点：**

- 渲染层与仿真层**完全分离**：`build_scene()` 把游戏状态转为纯数据 `Scene`，`MatplotlibRenderer` 只负责画，之后可替换为实时 3D 引擎而不动游戏逻辑。
- 绘图用的曲面**始终**来自仿真的同一个 `SmoothSurface`，绝不另造一张面。
- 网格采样**带缓存**：仅当曲面或分辨率变化时才重建（不是每步重建）。
- 玩家标记恒画在 `(x, y, f(x, y))` 上，与仿真坐标严格一致。
- 开发者视图默认关闭，只有 `--view debug` 或 `view debug` 才会显示隐藏状态。

### Matplotlib 交互的已知限制

- 这是**命令驱动**的刷新式原型（每次操作后重绘），**不是**实时 3D 游戏。
- 终端 `input()` 与 GUI 窗口并用时，输入期间窗口不响应（已用 `plt.pause()` 尽量让事件循环呼吸）。
- **未实现**键盘方向键回调，命令界面更可靠且功能更全。
- 旋转/缩放用 Matplotlib 内置交互，手感与精度有限。

## 交互式实时游玩（Task 5）

```powershell
.\.venv\Scripts\python.exe -m src.main --play --seed 12345 --view player
.\.venv\Scripts\python.exe -m src.main --play --seed 12345 --view debug
```

进入会话后提示符为 `[CurvedWorld]> `，每轮先打印一行紧凑状态：`(x,y,z)` + 最新信号与趋势 + 步数。

- **窗口常驻**：Matplotlib 窗口在会话开始时创建一次，之后每次指令**就地重绘**（`draw_idle()` + `pause()`），窗口不重建、不闪退。
- **不重建曲面**：曲面 `plot_surface` / `plot_wireframe` 只在曲面变化时创建；每步只移除/重建廉价的动态图元（玩家点、轨迹、标记、历史面板）。
- **退出/胜利**：`quit`/`exit` 关闭窗口；胜利时窗口保持常驻展示。
- **信息边界**：`--view player` 下终端与窗口都不显示出口坐标、真实距离或任何特权数据。

## Web 双视角交互（Task 6）

渲染从 Matplotlib 解耦：Python 只做**数学内核 + 安全 API**，浏览器负责交互与两个视角。
前端是原生 HTML5 + ES6 模块 + 极简 CSS，**无打包编译、无 CDN 依赖**，可完全离线运行。

```powershell
.\.venv\Scripts\python.exe -m src.main --serve --port 8000              # 玩家接口（安全）
.\.venv\Scripts\python.exe -m src.main --serve --debug                  # 额外开启特权调试接口
```

启动后浏览器打开 `http://127.0.0.1:8000/`。

**API 一览**

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/action/move` | 方向输入 -> 新的参数坐标、局部高度与信号读数 |
| POST | `/api/action/tool` | `scan` / `mark` / `measure` / `curvature` / `angle_sum` |
| GET | `/api/state/player` | 玩家可见状态：坐标、局部曲面块、轨迹、标记、信号与趋势、曲率 |
| GET | `/api/state/debug` | **特权**：全局网格采样 + 出口真实三维坐标（仅 `--debug`） |

**前端布局**

- **Player View（主视窗）**：玩家平面局部视角，带**探索迷雾（Fog of War）**、分层等高着色与网格，叠加轨迹、标记与玩家位置。迷雾在浏览器本地维护。
- **Instrument Panel**：探测器表盘（弱/中/强指针与配色）、局部高斯曲率数值、命名标记管理（点选参与测量）、测地三角内角和工具。
- **God View**：按 `G` 展开/收起的全局透视曲面视窗（需服务端 `--debug`），支持鼠标拖拽旋转。

**安全与信息边界**

- 玩家端接口**不含**出口坐标、真实距离或任何特权字段（测试含正向对照）。
- `/api/state/debug` 仅在 `--debug` 下存在，默认返回 403。
- 静态服务做路径穿越防护，默认只绑定 `127.0.0.1`。
- 前端与接口中不含任何影响评审的语句（有自动化扫描测试）。

## 大尺度流形与微分几何工具箱（Task 7）

默认参数域扩大到 **[-50, 50] × [-50, 50]**（100×100）；高度函数改为**多尺度**结构：
4 个不同波长的平滑正弦项 + 8 个混合高斯丘（山峰 / 凹陷 / 宽阔穹顶），仍处处 C-infinity。
实测高斯曲率 K 约在 [-0.25, 0.31]，正曲率聚集区与负曲率隘口各约占 1/3 采样点。

**玩家局部切空间视图**

- 玩家**始终位于画面中心**；只绘制半径 R 的局部补丁（不裁剪），其余被**几何迷雾**覆盖。
- 坐标网格按**第一基本形式 (E, F, G)** 的局部面积元 `sqrt(E G - F^2)` 做相对压缩 / 拉伸，
  直观暗示"这个世界并不平"。

**微分几何工具链**

- **测地三角测角仪（`tool: triangle`）**：选 3 个标记点，后端给出
  - 切平面内角和 `sum(theta)` 与超出 pi 的余量；
  - 数值曲率面积分 `iint_T K dA`（`dA = sqrt(1 + f_x^2 + f_y^2) dx dy`）；
  - 高斯-博内残差 `sum(theta) - pi - iint K dA`（如实给出，不宣称恒为 0）。
  内角和 > 180 度提示正曲率隆起，< 180 度提示负曲率鞍部。
- **切平面指向器（`tool: pointer`）**：**有限次数**（默认 3 次）的指引，
  只返回切平面内的**量化方位角**（默认 16 扇区）与**法向俯仰角**；
  不返回出口坐标、精确距离或真实三维偏移。

**交互热键**

- WASD / 方向键：**按住连续行走**（防抖 + 可配置步长倍数 1x / 2x / 3x）。
- `1` 测距尺 · `2` 测角仪 · `3` 高斯曲率 · `4` 指向器 · `G` 上帝视角。

## 封闭紧致流形（Task 8）

默认世界已从“有界平面高度图”重构为**嵌入 R^3 的紧致正则封闭曲面**，参数域统一为
周期的 `(u, v) in [-pi, pi) x [-pi, pi)`；边界钳制被**周期环绕**取代 —— 玩家沿
一个方向一直走会平滑绕回原点，没有死胡同、没有边界墙。

**三套可调参模型（`src/the_curved_world/manifold.py`）**

| 模型 | 形状 | 参数化 | 正则性 |
| :--- | :--- | :--- | :--- |
| `DeformedTorus`（默认） | 亏格 1 变形环面 | `r = ((R + rho cos u) cos v, (R + rho cos u) sin v, rho sin u)`，`rho = r0 + sum A_k cos(k u + phi) + sum B_l sin(l v + psi)` | `R > max|rho| > 0` => `E G - F^2 > 0` 处处成立 |
| `DeformedEllipsoid` | 亏格 0 变形椭球 | `r = (a m sin v cos u, b m sin v sin u, c m cos v)`，径向调制 `m(v)` | 极点 `v = 0, pi` 必为参数退化点 |
| `GenusTwoApproximation` | 双孔外观近似 | 环半径调制 `R(u) = R0 + R1 cos 2u` + 管半径谐波 | `E G - F^2 > 0` 处处成立 |

**解析微分几何**：切向量 `r_u, r_v`、法向 `n`、第一基本形式 `E, F, G`、第二基本形式
`L, M, N`、高斯曲率 `K = (L N - M^2)/(E G - F^2)` 全部**解析求出**（不使用运行时数值差分）。

**必须说清的拓扑事实（未加掩饰）**

- 用 `[-pi, pi)^2` 做**正则**参数化的像必然是亏格 1（参数方块被识别成环面）。
- 因此 `DeformedTorus` 与 `GenusTwoApproximation` 处处正则；
- `DeformedEllipsoid` 是亏格 0，**必然**有 2 个参数退化点（两极），曲率公式用分母下限保证不出现除零；
- 真正的亏格 2 需要亏格 2 的参数域，模型 C 只是“双孔外观近似”，名称已如实标注。

**玩法与探测**：出口是流形上的随机参数点；探测器仍用**环境三维欧氏距离**
`d = ||r(u,v) - r_exit||`，因此会出现“隔着曲面很近、走起来要绕大圈”的非欧折叠感。
标记存于周期参数空间，`measure` 仍是两点三维直线距离；测角仪与高斯-博内仍在局部切空间成立，
而环面的全局曲率积分 `iint K dA = 0`（亏格 1，chi = 0）——数值实测 = 0.0000。

**前端同步**：玩家仍居中；跨周期边界时局部网格与历史足迹**平滑环绕**（universal cover 绘制），
迷雾升级为**环面周期位图**（索引前先 wrap，跨越接缝不撕裂）；上帝视角渲染完整的封闭三维网格
（`/api/state/debug` 返回三维坐标网格 X/Y/Z）。

**实测**（种子 12345）

| 检查 | 结果 |
| :--- | :--- |
| 环面 `iint K dA` | 0.0000（理论 0） |
| 椭球 `iint K dA` | 24.53（双覆盖理论 8 pi = 25.13，极点退化导致 ~2.4% 数值偏差） |
| 双孔近似 `iint K dA` | ~0.08（理论 0） |
| 解析 vs 数值偏导 | 一阶误差 < 1e-6；二阶（h=1e-4）误差 < 1e-3 |
| 连续行走 400 步 | 坐标始终在 [-pi, pi)，`clamped` 恒为 False |

```powershell
.\.venv\Scripts\python.exe -m src.main --serve --port 8000        # Web 双视角（封闭流形）
.\.venv\Scripts\python.exe -m src.main --play --seed 12345        # 终端实时游玩
```

## 地图工厂与启动大厅（Task 9）

所有可玩世界都封装进**地图注册表**，新增地图只需写一个类并加装饰器，
**无需改动世界生成器或服务端主逻辑**：

```python
from src.the_curved_world.maps import register_map, BOUNDED_PLANE

@register_map(
    map_id="my_map",
    name="My Map",
    description="...",
    topology=BOUNDED_PLANE,
    placement={"min_separation": 5.0, "boundary_margin": 1.0, "detector_scale": 5.0},
)
class MyMap:
    def build(self, params):
        return SmoothSurface(...)
```

**已注册的 4 张地图**

| id | 名称 | 拓扑 | 播放提示 |
| :--- | :--- | :--- | :--- |
| `torus_genus1` | 变形环面（亏格 1） | closed_periodic | 默认；χ=0，∬K dA=0 |
| `ellipsoid_genus0` | 波动椭球（亏格 0） | closed_periodic | χ=2，双层覆盖，两极退化 |
| `double_torus` | 双孔近似（亏格 2 外观） | closed_periodic | 双瓣轮廓；真亏格 2 需亏格 2 参数域 |
| `planar_landscape` | 经典平面图曲面 | bounded_plane | 有界 100x100，带边界钳制 |

**命令行切图**

```powershell
.\.venv\Scripts\python.exe -m src.main --serve --map torus_genus1
.\.venv\Scripts\python.exe -m src.main --serve --map ellipsoid_genus0 --debug
.\.venv\Scripts\python.exe -m src.main --play --map double_torus --seed 7
.\.venv\Scripts\python.exe -m src.main --demo-scenario --map planar_landscape
```

**Web 启动大厅**：页面首次加载弹出毛玻璃大厅（`#lobby-modal`），可选择
地图（下拉框动态显示数学简介）、游玩模式（玩家探索 / 全知观测）与随机种子
（留空随机）；点击「进入学院」调用 `POST /api/session/new` 平滑过渡。
导航栏「🔄 新世界 / 选图」可随时唤回大厅。全知模式会自动展开三维全局网格并高亮出口。

**接口**

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/maps` | 已注册地图元数据列表（id / 名称 / 描述 / 拓扑） |
| POST | `/api/session/new` | `{map_id, seed, mode}` -> 重建世界、探测器与玩家位置 |

**安全边界**：`mode == "player"` 时 `/api/state/debug` **一律** 403，
无论客户端发什么请求；只有大厅选择全知模式或以 `--debug` 启动才放行。

## 目录结构

```
AI Empowered/
├── AGENTS.md                 # 协作规范（只读）
├── screenshots/  demo/       # 隔离区
├── submission/               # 最终提交内容（推送到 Group 仓库）
├── src/
│   ├── main.py               # 命令行入口
│   └── the_curved_world/     # 核心包
│       ├── config.py         # 配置与校验
│       ├── geometry.py       # 光滑曲面几何
│       ├── detector.py       # 距离敏感探测器（特权）
│       ├── observations.py   # 玩家可见接口（信息边界）
│       ├── world.py          # 世界状态、生成器、调试视图
│       ├── gameplay.py       # 探索玩法引擎（与界面无关）
│       ├── render.py         # 3D 场景构建 + Matplotlib 实时渲染器
│       ├── session.py        # 交互式会话主循环（Task 5）
│       ├── cli.py            # 终端命令界面
│       ├── demo.py           # 可复现的完整 Demo 场景
│       └── server.py         # 本地 HTTP API + 静态文件服务（Task 6）
├── web/                      # 轻量 Web 前端（Task 6，原生 HTML5 + ES6，无构建流程）
├── tests/                    # 单元测试
├── docs/                     # 技术文档
├── requirements.txt / requirements-dev.txt
├── pyproject.toml / Makefile
└── README.md / AI_USAGE.md
```

## 核心文件清单

| 文件路径 | 职责说明 |
| :--- | :--- |
| `src/the_curved_world/config.py` | 不可变配置数据类与参数校验 |
| `src/the_curved_world/geometry.py` | `SmoothSurface`、`ambient_distance` |
| `src/the_curved_world/detector.py` | `Detector`（特权）、`DetectorConfig` |
| `src/the_curved_world/observations.py` | 信息边界：`ObservationConfig`、`PlayerObservation`、`PlayerObserver`、`PlayerView` |
| `src/the_curved_world/world.py` | `WorldState`、`DebugView`、`WorldGenerator` |
| `src/the_curved_world/gameplay.py` | `ExplorationGame`、`GameplayConfig`、`Marker`、`LogEntry`、`MoveResult`、`GameSummary` |
| `src/the_curved_world/render.py` | `PlotMode`、`RenderConfig`、`SurfaceMeshCache`、`Scene`、`build_scene`、`MatplotlibRenderer` |
| `src/the_curved_world/cli.py` | `GameCLI`：命令解析、呈现、视图切换 |
| `src/the_curved_world/session.py` | `run_interactive_session()`：阻塞式交互主循环（状态摘要 + 输入流可注入） |
| `src/the_curved_world/server.py` | `GameSession` + `CurvedWorldHandler`：本地 JSON API 与静态文件服务（仅标准库） |
| `web/index.html` / `web/style.css` / `web/app.js` | Web 前端：玩家局部视图（迷雾）、仪表盘、上帝视角（调试） |
| `src/the_curved_world/demo.py` | `run_demo()`：可复现的完整 Demo 场景 |
| `src/main.py` | 入口：终端游戏 / `--demo` / `--render` / `--view` |
| `tests/test_geometry.py` | 曲面几何测试 |
| `tests/test_world_generation.py` | 世界生成与可复现性测试 |
| `tests/test_detector.py` | 探测器与信息边界测试 |
| `tests/test_gameplay.py` | 移动/边界/标记/测量/胜利测试 |
| `tests/test_cli.py` | 命令界面与输入校验测试 |
| `tests/test_render.py` | 渲染一致性、玩家视图不泄露、调试视图、网格缓存测试 |
| `tests/test_server.py` | Web API、信息边界与注入内容扫描测试 |
| `tests/test_large_scale.py` | 大尺度域、坐标钳制、第一基本形式、高斯-博内、指向器测试 |
| `src/the_curved_world/manifold.py` | `ClosedManifold` 基类 + 变形环面 / 变形椭球 / 双孔近似；解析一阶二阶偏导与 K |
| `tests/test_closed_manifold.py` | 三套模型的解析偏导精度、正则性、周期环绕、高斯-博内积分与信息边界 |
| `src/the_curved_world/maps.py` | `MapMetadata` + `MapRegistry` + `@register_map`；4 张内置地图与 `world_config_for` |
| `tests/test_map_registry.py` | 注册、按 id 构造、非法 id、元数据完整性、装饰器扩展 |

## 功能状态表

| 功能模块 | 对应核心文件 | 状态 (已完成/未实现) |
| :--- | :--- | :--- |
| 光滑曲面几何（解析导数） | `src/the_curved_world/geometry.py` | ✅ 已完成 |
| 确定性世界生成（种子可复现） | `src/the_curved_world/world.py` | ✅ 已完成 |
| 距离敏感探测器 | `src/the_curved_world/detector.py` | ✅ 已完成 |
| 信息边界（玩家/调试接口分离） | `src/the_curved_world/observations.py`、`world.py` | ✅ 已完成 |
| 探索移动（参数空间、边界钳制、对角归一化） | `src/the_curved_world/gameplay.py` | ✅ 已完成 |
| 探测器观测（信号 + 标签 + 升降趋势） | `src/the_curved_world/observations.py`、`gameplay.py` | ✅ 已完成 |
| 探索日志、标记、测量探针 | `src/the_curved_world/gameplay.py` | ✅ 已完成 |
| 胜利条件（捕获半径） | `src/the_curved_world/gameplay.py` | ✅ 已完成 |
| 终端命令界面 + 输入校验 | `src/the_curved_world/cli.py` | ✅ 已完成 |
| 3D 可视化（玩家视图，不泄露隐藏状态） | `src/the_curved_world/render.py` | ✅ 已完成 |
| 开发者调试视图（显式开启） | `src/the_curved_world/render.py`、`world.py` | ✅ 已完成 |
| 可复现 Demo 场景 | `src/the_curved_world/demo.py` | ✅ 已完成 |
| 数学审计 + 信息泄露审计 + 最终验证 | `tests/test_math_audit.py`、`tests/test_information_boundary.py`、`tests/test_demo.py`、`docs/final_report.md` | ✅ 已完成 |
| 交互式实时游玩会话（Task 5） | `src/the_curved_world/session.py` | ✅ 已完成 |
| 渲染窗口就地更新（复用网格、不重建曲面） | `src/the_curved_world/render.py` | ✅ 已完成 |
| 高斯曲率工具（解析） | `src/the_curved_world/geometry.py` | ✅ 已完成 |
| Web 交互 + 双视角渲染架构（Task 6） | `src/the_curved_world/server.py`、`web/` | ✅ 已完成 |
| 玩家端只读 API（严格隔离隐藏状态） | `src/the_curved_world/server.py` | ✅ 已完成 |
| 特权 `/api/state/debug`（仅 `--debug` 开启） | `src/the_curved_world/server.py` | ✅ 已完成 |
| 测地三角内角和工具（切平面近似） | `geometry.py`、`gameplay.py` | ✅ 已完成 |
| 大尺度多尺度地貌（100×100 域） | `config.py`、`geometry.py` | ✅ 已完成（Task 7） |
| 玩家居中局部切空间视图 + 几何迷雾 | `web/app.js`、`server.py` | ✅ 已完成（Task 7） |
| 网格按第一基本形式 (E,F,G) 畸变 | `server.py`、`web/app.js` | ✅ 已完成（Task 7） |
| 高斯-博内测地三角测角仪 | `gameplay.py`、`server.py` | ✅ 已完成（Task 7） |
| 有限次切平面指向器（量化提示） | `gameplay.py`、`server.py` | ✅ 已完成（Task 7） |
| 封闭紧致流形引擎（3 套模型，解析微分几何） | `src/the_curved_world/manifold.py` | ✅ 已完成（Task 8） |
| 周期环绕（取消边界钳制） | `manifold.py`、`gameplay.py` | ✅ 已完成（Task 8） |
| 周期迷雾与环绕足迹渲染 | `web/app.js`、`server.py` | ✅ 已完成（Task 8） |
| 封闭曲面上帝视角（三维网格） | `server.py`、`web/app.js` | ✅ 已完成（Task 8） |
| 地图注册表 / 工厂插件化（Task 9） | `src/the_curved_world/maps.py` | ✅ 已完成 |
| Web 启动大厅 + 模式/种子/换图（Task 9） | `web/index.html`、`web/app.js`、`server.py` | ✅ 已完成 |

## 安装、运行与测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m src.main --render          # 玩（带 3D 视图）
.\.venv\Scripts\python.exe -m pytest                     # 测（或： make test）
```

## 已知限制

- 渲染是**刷新式**命令驱动原型，非实时 3D；未实现键盘事件回调。
- 探测器为确定性模型，**暂无**测量噪声（Task 1 明确暂不加入）。
- 移动在参数空间进行，**不是**测地线运动或物理真实行走。
- 曲面族为“正弦波 + 高斯丘”之和；不保证对任意用户提供的函数成立。
- 尚未实现（计划扩展）：测量噪声、键盘/鼠标事件回调、实时 3D 引擎替换、更复杂的曲面族。

## 演示与复现

固定种子 **12345**：

```
powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
```

该命令跑完整流程并**打印真实读数**：起始 → 初始读数 → 移动并比较 → 放两个标记 → 标记间测距 → 受控接近出口（用开发者视图引导，但每次打印的都是真实读数）→ 胜利摘要。种子 12345 下确定性地在 **14 步 / 9 次读数 / 2 个标记** 处获胜。

## 计划扩展

- 可配置的测量噪声模型（Task 1 明确留待后续）。
- 用实时 3D 引擎替换 `MatplotlibRenderer`（`build_scene` 已把渲染与逻辑解耦）。
- 更多曲面族与自适应网格。
- 不依赖开发者视图的自动求解器演示（当前 Demo 的最终接近由开发者视图引导，属受控演示）。

## 环境

- Python 3.13（虚拟环境 `.venv/`，基于本机 3.13.2 创建）
- numpy、matplotlib（运行/可视化）、pytest（测试）