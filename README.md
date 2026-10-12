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

**已注册的 9 张地图**

| id | 名称 | 拓扑 | 播放提示 |
| :--- | :--- | :--- | :--- |
| `torus_genus1` | 变形环面（亏格 1） | closed_periodic | 默认；χ=0，∬K dA=0 |
| `ellipsoid_genus0` | 波动椭球（亏格 0） | closed_periodic | χ=2，双层覆盖，两极退化 |
| `double_torus` | 双孔近似（亏格 2 外观） | closed_periodic | 双瓣轮廓；真亏格 2 需亏格 2 参数域 |
| `klein_bottle` | 克莱因瓶（figure-8 浸入） | closed_periodic | χ=0；R³ 中必然自交，无全局外侧（Task 17） |
| `klein_bottle_traditional` | 经典瓶形克莱因瓶 | closed_periodic | 脖子穿过瓶身；与上一张分属三个正则同伦类中的两个（Task 18） |
| `knot_garden` | 打结环面（三叶结管道） | closed_periodic | 拓扑仍是环面，但**嵌入**是打的结：两股在三维里很近、沿曲面却很远（Task 18） |
| `elliptic_curve` | 椭圆曲线 ℂ/(ℤ+iℤ) | closed_periodic | 共形模型，模数恰为 τ=i；胖管窄孔，三维近邻极多（Task 18） |
| `projective_plane` | 实射影平面 RP²（对跖） | closed_periodic | 不可定向、χ=1；**你的对跖点就是你**，唯一使用 `orbit_min` 距离策略的图（Task 18） |
| `planar_landscape` | 经典平面图曲面 | bounded_plane | 有界 100x100，带边界钳制 |

**命令行切图**

```powershell
.\.venv\Scripts\python.exe -m src.main --serve --map torus_genus1
.\.venv\Scripts\python.exe -m src.main --serve --map ellipsoid_genus0 --debug
.\.venv\Scripts\python.exe -m src.main --play --map double_torus --seed 7
.\.venv\Scripts\python.exe -m src.main --play --map klein_bottle --seed 12345
.\.venv\Scripts\python.exe -m src.main --play --map knot_garden --seed 12345
.\.venv\Scripts\python.exe -m src.main --serve --map projective_plane --debug
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

## 第一人称流形视角、雷达小地图与障碍物（Task 10）

主画布改为**第一人称切空间视角**：玩家贴在曲面上向前看，`up` 取曲面法向，
因此在切平面内维护朝向角 `yaw` 并构造正交视线标架 `{forward, right, up}`；
前方地形会随曲率向下弯曲 / 向上隆起，呈现置身弯曲世界的透视。

**控制**（前端）：

| 按键 | 作用 |
| :--- | :--- |
| `W` / `S`（或 ↑/↓） | 沿当前朝向**前进 / 后退** |
| `A` / `D`（或 ←/→） | **原地转向**（改变 `yaw`） |
| 鼠标拖拽主视窗 | 转向 |
| `1` / `2` / `3` / `4` | 测距尺 / 测角仪 / 高斯曲率 / 指向器 |
| `G` / `Esc` | 打开 / 关闭全知上帝视角 |

**局部雷达小地图（右上角 HUD）**

- **彻底移除全局探索记忆与迷雾揭图**：不再记录历史足迹、不保留走过的区域；
- 雷达只渲染以玩家为中心、固定小半径 `R_radar` 的**即时局部切片**，以及
  视距内的**障碍物红点**与附近标记点；雷达随 `yaw` 旋转（朝向始终朝上）；
- 因此无法通过盲目扫图"涂满地图"来找出口，必须依赖测量工具推理。

**两阶段世界生成与障碍物系统**（`src/the_curved_world/obstacles.py`）

1. 先独立生成连续且 C-infinity 光滑的封闭流形底层曲面；
2. 再按种子在曲面上**离散散布静态障碍物**（`boulder` / `rift` / `pillar`），
   每个障碍物记录参数坐标 `(u, v)`、三维位置与碰撞半径。

- **安全边距**：出生点与隐藏出口周围强制清空（默认 9.0 环境距离），不会堵死出口或开局卡死；
- **确定性**：同一 `(地图, 种子)` 生成的障碍物完全一致；
- **碰撞**：用**环境三维距离**判定（自然处理周期接缝），撞上时阻止穿透并尝试沿参数轴滑动，
  返回 `collided: true`（前端提示 `blocked by obstacle`）。

**信息边界**：`/api/state/player` 只返回**渲染补丁范围内**的障碍物（`vision_radius` 以内），
绝不返回远端障碍物、出口坐标或真实距离。

**接口**

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/action/move` | `{"action":"step","direction":"forward"|"backward"|"strafe_left"|"strafe_right","steps":n}` 或 `{"action":"turn","angle":d}` |
| GET | `/api/state/player` | 追加 `yaw`、`forward_3d` / `right_3d` / `up_3d`、视野内 `obstacles`、补丁三维网格 `X/Y/Z` |
| GET | `/api/state/debug` | 全局网格 + 全部障碍物 + 出口（仅全知模式 / `--debug`） |

## 实心流形、法向悬浮视点、坡度阻力与滑动碰撞（Task 11）

**法向外推悬浮视点（防穿模）**

- 第一人称相机不再落在零厚度曲面上，而是沿**向外**单位法向抬升：
  `P_camera = r(u,v) + h_eye · n(u,v)`（默认 `h_eye = 2.0`），近裁剪面始终在曲面外侧；
- `ClosedManifold.normal()` 统一返回**向外**法向量：环面族用符号修正，
  双覆盖的椭球按点判定翻转，退化极点 1e-4 参数微扰后取值（零测度点仍保持良定义）；
- `ExplorationGame.camera_position()` 暴露相机点，`project_to_tangent()` 把任意位移投影回切平面，
  保证玩家只沿外表面切空间移动。

**坡度阻力模型**

- `calculate_slope_penalty(u, v, du, dv)`：`slope = Δz / ||Δr_tangent||`；
- 上坡（`slope > 0`）：`effective_step = step / (1 + κ · slope²)`（默认 κ = 3.0）；
- 下坡 / 平地（`slope ≤ 0`）：不受阻，`effective_step = step`；本阶段无惯性，保持确定性；
- 最近一次坡度与速度缩放通过 `/api/state/player` 的 `slope` 字段暴露给 HUD。

**障碍物滑动碰撞（tangent sliding）**

- `ObstacleField.resolve_collision(current_uv, next_uv, player_radius)`：
  计算穿透向量 → 去掉径向分量 → 把剩余位移映回参数空间 → 沿障碍物轮廓平滑滑动；
  切线映射只是一阶近似，因此会朝（无碰撞的）当前位置回退直到确实在障碍物之外；
- `POST /api/action/move` 返回 `collided: true`，前端提示 `blocked by obstacle`；
- `/api/state/player` 新增 `camera_position_3d` / `eye_height` / `slope` / `collided` /
  `local_obstacles`（仅 `R_view` 内，绝不泄露全图障碍物与出口）。

## 渲染平滑化、草地着色与程序化低模自然物（Task 12）

- **高分屏**：Canvas 物理像素与 CSS 尺寸绑定（`width = rect.width * dpr`）+ `ctx.scale(dpr, dpr)`，消除边缘模糊；
- **60FPS 常驻渲染循环**：`requestAnimationFrame` 主循环 + `RenderEngine`（`view.cam` / `view.yaw`），
  相机位置与朝向按 `alpha = 0.18` 做 LERP / 最短角插值，行走不再阶跃；
- **草地生态着色**：基底自然草绿 `#3d7e34 → #58a542`，按高度泛黄、按坡度（由第一基本形式 E/G 推得）转苔藓/裸土暗绿；
  网格线改为半透明微光，兼顾数学线框感与自然沉浸感；
- **程序化低模自然物**：`drawLowPolyTree`（深褐树干 + 3 层墨绿四棱锥树冠）、
  `drawLowPolyRock`（6 边形不规则块体 + 苔绿顶面）；障碍物按深度由远及近绘制（画家算法）；
- **障碍物生态分类**：`Obstacle.kind ∈ {tree, rock}`，按种子 60% 树木 / 40% 岩石；雷达上树木=深绿点、岩石=灰褐点；
- **尺度平滑调优**：默认环面主半径 `30 → 45`（+50%）、管半径 `10 → 14`，高阶微扰振幅下调（1.4/1.1/0.7 → 0.95/0.75/0.45）使坡度更连续；
  局部切空间网格采样 `33×33 → 49×49`；`detector_scale 16→24`、`min_separation 18→27`、捕获半径 `3.0→4.5`；
- **安全边界不变**：`/api/state/player` 仍不返回出口坐标、真实距离或视距外障碍物；碰撞滑动、法向眼高、安全区逻辑保持不变。

## 360° 自由视角与第一人称手持工具栏（Task 13）

- **Pointer Lock 360° look**：点击画布锁定鼠标，`mousemove.movementX/Y` 直接驱动视线；
  yaw 无限制连续旋转，pitch 限制在 ±1.48 rad（±85°）避免万向节锁；每帧按 alpha=0.18 插值；
- **视线与移动解耦**：相机 forward = cos(pitch)·forward_tangent + sin(pitch)·n；
  但 W/S/A/D 始终沿**地表切平面**前进/后退/侧移，贴地滑行不受抬头低头影响；
- **底部物品栏（5 槽）**：1 罗盘(探测器) · 2 曲率仪 · 3 测角仪 · 4 末影光标 · 5 拓扑信标；
  数字键 `1`-`5`、鼠标滚轮或点击槽位切换；左键使用；
- **手持拟物模型**：右下角程序化 Canvas viewmodel（黄铜罗盘/曲率陀螺仪/测角器/能量球/测绘短杖），
  带呼吸与行走摆动（bobbing）；罗盘指针随信号升降震颤、外圈泛蓝光；
- **世界内特效（worldFX）**：使用末影光标会在视界内生成**飞行的 3D 光球粒子**（沿切平面方位 + 法向俯仰飞出并消散）；
  使用信标会在脚下生成**自发光棱柱**（呼吸光效）；
- **安全边界不变**：光球/信标仅由本地已有的量化方位与局部状态驱动，服务端从不提前传输出口坐标。

## 宏观平缓流形、客户端物理接管与柔性碰撞（Task 14）

- **宏观超大平缓流形**：默认环面 `ring 45 → 130`、`tube 14 → 45`；高阶微扰降至 0.45/0.35/0.20 且降阶，
  百米视距内局部高斯曲率约 1e-4 量级（微小但严格非零），地表如温和草原；
  `detector_scale 24 → 60`、`min_separation 27 → 70`、`capture_radius 4.5 → 12.0` 同步放大；
- **客户端零延迟物理接管**：`InputController` 维护 `keysDown`，60FPS 帧循环内直接积分本地位移
  （切平面方向 × speed × dt），画面无网络回拉；**低频同步**：停止移动或每 250ms 通过新增的
  `POST /api/action/sync_position` 上报本地 (u,v)，服务端回传曲率/坡度/探测器读数/视距内障碍物，
  并保留世界状态审计与胜利判定（`POST /api/action/move` 完全兼容 CLI 与既有测试）；
- **柔性连续滑动碰撞**：本地每帧遍历视距内障碍物做球体距离判定，穿透时沿法向外推、
  仅保留切向分量 → 撞树可顺边"蹭"过，不卡死；上坡阻力继续生效；
- **远景空气雾效**：超过 `0.7 × R_view` 的网格与障碍物颜色向淡青灰天空色渐变，
  隐藏局部采样边界，呈现开阔无垠的草原感。

## 无缝二维俯视切空间地图、硬碰撞与微地貌晕渲（Task 15）

> 背景：Task 13 的第一人称伪 3D 视锥在浏览器里不平滑、穿模多。Task 15 彻底移除第一人称投影，
> 回归"玩家恒定居中的纯二维局部俯视地图"，但保留后端全部微分几何、探测器与信息边界。

- **纯 2D 局部切空间俯视**：`web/app.js` 的 `drawTopDownWorld()` 取代 `drawFirstPerson()`；
  玩家以"圆点 + 朝向箭头"永远绘制在画布中心；`web/index.html` 删除右上角雷达 `#radar-canvas`
  （主视图本身就是局部地图）；
- **周期相对包裹的无缝滚动**：地物一律用相对参数差
  `Δu = wrap(u_obj − u_player)`、`Δv = wrap(v_obj − v_player)` 投影到屏幕；可视半径
  `patch.radius ≈ 1.38 < π`，任何可见地物都不会落在 `wrap` 的 ±π 跳变点上，
  越过周期接缝时画面不闪、不跳、不撕裂；有界地图（`planar_landscape`）自动改用线性差值；
- **微地貌晕渲（不泄露全局拓扑）**：对服务端局部补丁 `z` 做双线性采样，叠加**半透明等高线**
  （对 `z` 分层做 marching-squares）与**高程调色**（低处深绿、高处黄绿），并用有限差分法向量
  与固定光照方向做**漫反射明暗**；只在局部可见，无法据此推断甜甜圈/球/双孔全局形状；
- **上坡阻尼与坡度 HUD**：沿朝向用 `slope = Δz / ‖dr_tangent‖` 求局部坡度，
  `v_eff = v_base / (1 + κ·slope²)`（κ=3，与 `GameplayConfig.slope_damping` 一致），下坡/平地全速；
  仪表盘保留轻量坡度读数；
- **刚性圆盘硬碰撞**：障碍物半径按**自身所在位置的局部度量**换算成参数半径，玩家为半径
  `player_radius` 的圆盘；每帧若尝试位移进入圆盘，就把位移沿碰撞法向截断（不允许渗透），
  保留切向分量 → 撞树/岩石被硬挡住，并沿边缘顺滑滑开、不卡死；
- **60FPS 本地控制 + 低频同步**：本地 `requestAnimationFrame` 以 WASD 连续积分，
  每 ~200ms 或停止时 `POST /api/action/sync_position` 上报 `(u,v)`；
  服务端 `GET /api/state/player` / `POST /api/action/move` / `sync_position` 契约保持不变；
- **沉浸式热栏保留并 2D 化**：`1` 罗盘（扩散共振波纹）、`2` 曲率仪（凸/凹/平的局部读数卡）、
  `3` 测角仪、`4` 末影光标（从中心沿服务端量化方位射出淡出光球拖尾）、
  `5` 标记信标（脚下发光图钉）；全部只使用已有的局部/量化数据，服务端从不提前传输出口坐标或真实距离。
## 增大障碍物体积、通关结算弹窗与提交封装（Task 16）

- **更大的自然障碍物（按地图尺度调参）**：默认 `WorldConfig.obstacle_radius` 1.2 -> 3.5、
  `obstacle_safe_margin` 6.0 -> 12.0；四张内置地图同步放大（并保证生成必然成功、出生点与出口安全距离严格成立）：

  | 地图 | 障碍数量 | 半径（原 -> 新） | 安全边距（原 -> 新） |
  | :--- | :--- | :--- | :--- |
  | `torus_genus1` | 30 | 4.0 -> 4.2 | 32 -> 45 |
  | `ellipsoid_genus0` | 8 | 1.3 -> 2.4 | 7 -> 12 |
  | `double_torus` | 16 | 1.3 -> 4.5 | 7 -> 12 |
  | `planar_landscape` | 18 | 1.8 -> 4.5 | 8 -> 16 |

- **所见即所撞的前端半径**：`web/app.js` 把障碍物三维半径按其**所在位置**的局部度量换算成参数半径，
  绘制半径与硬碰撞圆盘共用同一 `obstacleParam`（最小像素半径 7 -> 12），并额外绘制玩家的碰撞体半径环；
- **通关结算弹窗 `#victory-modal`**：当服务端返回 `won: true` 时弹出毛玻璃结算弹窗（轻量庆祝微光动画），
  展示步数、探测器读数次数、标记数、耗时、地图、拓扑与种子；提供 **Continue Free Roam**（关闭弹窗、
  顶部 HUD 出现 `Cleared` 徽章，可继续测量/截图）与 **Return to Lobby**（关闭弹窗并重新呼出启动大厅）两个出口；
- **纯英文 UI**：新增的弹窗与按钮文案全部为英文，避免编码乱码与中文字符测试报警；
- **回归测试**：新增 `tests/test_obstacle_scale.py` 固定新尺度并验证四张地图在多个种子下仍能生成、
  且障碍物与出生点/出口的安全距离始终 >= `obstacle_safe_margin`；
- **提交封装**：`scripts/package_submission.py` 新增 `--output` 参数（默认仍是 `submission/`），
  可把 `src/`、`web/`、`tests/`、`docs/`、README、AI_USAGE、ai-logs、截图与 DEMO_LINK 打包为可复现产物；
  按 `AGENTS.md` 第 5.6 条，本轮以 `codex/*` 分支提交，由用户在主仓库手动合并。

## 克莱因瓶关卡：不可嵌入、不可定向的封闭世界（Task 17）

新增第 5 张地图 `klein_bottle`，按既有插件规范注册（只加了一个 `KleinBottle` 模型 + 一条注册项，
**未改动**世界生成器、探测器和信息边界的任何主逻辑）：

```powershell
.\.venv\Scripts\python.exe -m src.main --serve --map klein_bottle --debug
.\.venv\Scripts\python.exe -m src.main --play  --map klein_bottle --seed 12345
```

### 实现的是什么（不含糊）

克莱因瓶**不可能嵌入 R³**，所以本关给出的是一张**浸入**（immersion）——经典 figure-8 浸入：

```
P(u, v) = R + t ( cos(u/2) sin v - sin(u/2) sin 2v )
Q(u, v) = t ( sin(u/2) sin v + cos(u/2) sin 2v )
r(u, v) = ( P cos u, P sin u, Q )          # R = 90, t = 31
```

`r_u / r_v / r_uu / r_uv / r_vv` 全部**解析求出**（利用手推恒等式 `P_u = -Q/2`、`Q_uu = -Q/4`），
运行时不做数值差分；一阶偏导与中心差分误差 < 2.1e-8，二阶 < 2.4e-6。

| 事实 | 实测 |
| :--- | :--- |
| 处处正则（真浸入） | `min(E G - F²) ≈ 1.27e6`，退化点比例 **0** |
| **必然自交** | `r(u, 0) = r(u, pi) = (R cos u, R sin u, 0)`：z=0 平面内半径 R 的圆被覆盖**两次**，两处法向不平行（横截交叉） |
| **不可定向** | 沿 u 环绕一周后法向反向：`n(u + 2pi, v) = -n(u, -v)`，误差 ~2.8e-16；本关**没有全局"外侧"** |
| 高斯-博内 | χ = 0，故 `∬K dA = 0`——数值实测 **0.0000**（与环面同） |
| 表面积（数值） | ≈ 1.66e5（R=90, t=31） |

### chart 周期不再是 2π × 2π（本任务的工程重点）

`r(u + 2pi, v) = r(u, -v)`：u 方向平移 2π **不是恒等变换**，而是把 v 镜像。
如果照旧按 `wrap_parameter` 把 u 独立折回 `[-pi, pi)`，玩家每跨过一次缝，局部图就会整体镜像一次——那是可见的穿帮。

解决方案是把"chart 如何识别自己的点"收敛成 manifold 的**公开接口**，各层只查询、不假设：

| 接口 | 环面 / 椭球 / 双孔近似 | 克莱因瓶 |
| :--- | :--- | :--- |
| `chart_periods()` | `(2pi, 2pi)` | `(4pi, 2pi)`：平移周期是 4π，平移 2π 会翻转 v |
| `wrap(u, v)` | 独立折回 `[-pi, pi)` | 按 4π/2π 折回（**纯平移**，曲面上完全不可见，不做翻转归一化） |
| `chart_copies()` | 1 份 | 2 份（每个曲面点在 chart 中有 `(u, v)` 与 `(u + 2pi, -v)` 两份坐标） |
| `chart_relative()` | 等价于 `wrap_difference` | 在**两份**坐标中挑最近的一份，跨缝"近处仍然近" |

调用方相应改为查询 surface：`gameplay._clamp`、`ObstacleField.resolve_collision`（滑动碰撞回溯）、
`/api/state/player` 新增的 `twisted` / `orientable` / `chart_periods` 字段，
以及前端 `web/app.js` 的 `chartDelta` / `localize` / 硬碰撞包裹（同一套周期 + 副本规则）。

**实测（连续移动，步长 0.25）**

| 检查 | 结果 |
| :--- | :--- |
| 沿 u / v / 对角各走 400 步 | 坐标始终在 `[-2pi, 2pi) × [-pi, pi)`，`clamped` 恒为 False |
| 跨缝连续性 | 跨过 u = ±2π 时单步三维位移 ≤ `|r_u| × 步长`（无瞬移）；`wrap` 前后三维坐标差 < 1e-9 |
| 前端相对包裹 | `chartDelta` 把另一份坐标识别为零位移（node 侧单测通过，含"隔缝邻居"用例） |

### 玩法上与诚实说明

- 探测器仍是**环境三维欧氏距离**（与其它地图口径完全一致）。在自交圆上两个**不同**的曲面点三维重合，
  因此探测器在那里给出**相同**读数；`signal = 1` 当且仅当玩家恰好位于出口的三维位置。
- 障碍物碰撞同样按**环境三维距离**判定。这意味着自交圆对应的两条参数线 `v = 0` 与 `v = pi` 附近
  （每侧各约 0.074，两者合计约占 v 周期的 4.7%，由 `(障碍半径 + 玩家半径) / (t√5)` 精确给出）
  另一支曲面上的障碍物也满足碰撞判据：后端 `move` 路径会阻挡，
  而前端按局部 chart 做硬碰撞、并把该障碍物画在 chart 上的远处（视口之外）。
  **所以这一薄带内"看不见却被挡 / 穿过去"是可能的**——这是自交浸入模型在 R³ 中的固有边界，
  本版如实标注，不用特判把它藏起来。
- 上帝视角（`/api/state/debug`）为克莱因瓶覆盖 `sample_grid`：绘制 `[0, 2pi]²` 基本域，
  其 u=0 与 u=2π 两条边曲线是**同一条曲线按 v 反向**（`r(0, -v) = r(2pi, v)`），因此画面是闭合的，
  自交处按画家算法正常显示。

### 上帝视角修复：切图后不再显示上一张地图（Task 17 修正）

**症状**：在上帝视角已打开的情况下从大厅换图，3D 面板仍显示**上一张**地图的网格——
换成克莱因瓶后看起来"克莱因瓶的 3D 图没有绘制"。

**根因**：`setGodView(true)` 在"已经处于该状态"时直接 `drawGodView()` 重绘**缓存**的
`state.debugState`，从不重新请求 `/api/state/debug`；而 `/api/session/new` 已经重建了世界。
用无头浏览器实测（planar_landscape → klein_bottle）：切换后画布像素与切换前**逐位相同**，
而当前会话的模型已经是 `figure-8 Klein bottle`。

**修复**（`web/app.js`）：

- 新增 `refreshGodView()`：**总是**重新 GET `/api/state/debug` 再重绘；
- `setGodView()` 在"已是目标状态且可见"时也走 `refreshGodView()`；`toggleGodView()` 复用同一函数；
- `enterWorld()` 在重建世界时清空 `state.debugState`，杜绝任何陈旧网格被重绘。

**顺带修正的可见性问题**（否则"画了但看不见"）：

| 问题 | 修正 |
| :--- | :--- |
| 上帝画布用固定的 760x520 属性尺寸绘制，再由 CSS 拉伸到面板宽度（最高约 1400px）→ 明显模糊 | `drawGodView` 改用 `frameCanvas(canvas)`，按 CSS 尺寸 × DPR 绘制（与主地图一致） |
| 画布宽高比 1.46 且占满整行 → 面板高达约 950px，3D 图基本落在屏幕外 | 属性改为 `1000x500`（2:1），CSS `#god-canvas { max-width: 1000px; margin: 0 auto; }` |
| 归一化后曲面只占画布约 42% | 投影填充系数 `0.42 -> 0.68`（`|rx| <= 0.707` 的上界保证任意 yaw 下都不裁切） |
| 按 `G` 后仍需手动滚动才看得到 3D 面板 | 打开时 `scrollIntoView({block: 'start'})`（瞬时，确保按下即可见） |

**回归验证**（无头 Edge，1600x1000）：planar_landscape → klein_bottle 切换后，
画布实际绘制包围盒与当前会话的投影包围盒**完全一致**（`163,832,136,358`），
`scrollY = maxScroll`，上帝画布 CSS 尺寸 `1000x500`。Python 侧 176 项测试保持全通过。

## 四张新地图：打结环面 / 瓶形克莱因瓶 / 椭圆曲线 / 射影平面（Task 18）

```powershell
.\.venv\Scripts\python.exe -m src.main --play  --map knot_garden --seed 12345
.\.venv\Scripts\python.exe -m src.main --play  --map klein_bottle_traditional --seed 12345
.\.venv\Scripts\python.exe -m src.main --serve --map elliptic_curve --debug
.\.venv\Scripts\python.exe -m src.main --serve --map projective_plane --debug
```

### 1. 打结环面 `knot_garden`（拓扑平凡，嵌入不平凡）

管道沿 (2,3) 环面结走：`theta = 2u, phi = 3u`，
`K(u) = ((R + a cos phi) cos theta, (R + a cos phi) sin theta, a sin phi)`，
再用载环面自身的正交标架（外法向 `N` 与 `phi` 切向 `E`）造管：

```
r(u, v) = K(u) + rho ( cos v N(u) + sin v E(u) )
```

标架不做法向归一化（没有 Frenet 退化），因此一二阶偏导全部初等解析。

| 事实 | 实测 |
| :--- | :--- |
| 拓扑 | 仍是**环面**：可定向、χ=0、∬K dA = **−3.6e-15** |
| 正则性 | `min(EG−F²) = 36864 > 0`，退化点比例 0 |
| 嵌入性 | 构造期校验 `tube_radius < 股间距/2`；本图股间中心距 20.0，取 rho=8 |
| 玩法核心 | 两股在三维里最近约 **12.0**，而沿曲面要走半圈（≈200）；`detector_scale = 30`，所以探测器在两股上读数几乎一样 |

这正是"环境距离 ≠ 曲面距离"的极致版本：打结的**不是曲面而是嵌入**，所以数学上它还是一只甜甜圈。

### 2. 经典瓶形克莱因瓶 `klein_bottle_traditional`

采用维基百科给出的经典"瓶子"参数化（脖子穿过瓶身），并重参数化为本引擎的 chart 契约：

```
U = 2u,  w = v - pi/2   =>   r(U + 2pi, w) = r(U, -w)
```

| 事实 | 实测 |
| :--- | :--- |
| 与公开公式一致性 | 与逐字抄写的参考实现最大偏差 **8.9e-16** |
| 正则性（真浸入） | `min(EG−F²) = 0.0094 > 0`，退化点比例 0 |
| χ=0 | ∬K dA = **−3.4e-16** |
| 必然自交 | 参数相距 2.18 的两点三维重合（脖子穿过瓶身），误差 < 0.01 |
| 与 Task 17 的关系 | 正则同伦类：figure-8 浸入是**手性**的，经典瓶形是**非手性**的；两者合起来覆盖三类中的两类 |

偏导的推导不在纸面硬推：轮廓写成 `(cos u, sin u)` 的多项式字典，由 `_poly_derivative` **符号求导**得到，再按 `d/du = (1/2) d/dU` 缩放——依然不运行时数值差分。

### 3. 椭圆曲线 `elliptic_curve`（复分析的黎曼曲面）

世界是**Clifford 环面的球极投影**，即环半径:管半径恰为 `sqrt(2):1` 的旋转环面。球极投影是共形的，所以这是一个**共形模型**：

| 事实 | 实测 |
| :--- | :--- |
| 共形周期 | `W = integral r dv/(R + r cos v) = 2 pi r/sqrt(R^2 - r^2)`，与数值积分相对误差 **0** |
| 共形模数 | `tau = i * r/sqrt(R^2 - r^2)`；本图取 R/r = sqrt2 时 **tau = i**（正方形格 ℂ/(ℤ+iℤ)） |
| 其它半径 | (3,1) → 0.353553i、(5,2) → 0.436436i，公式与数值积分逐位一致 |
| 拓扑 | χ=0，∬K dA = 3.1e-15；`min(EG−F²) = 5.9e5 > 0` |
| 玩法 | 管粗孔小（孔半径 = 0.414 × 管半径），三维近邻极多 |

**诚实边界（写进类文档与测试）**：这只是**共形**模型，不是等距嵌入——R³ 中根本不存在完备的平坦闭曲面（Hilbert）；本图的曲率是普通环面曲率（外正内负），只是总积分为 0。另外**紧黎曼曲面上不存在非常值全纯函数**，所以这里的"复分析"体现在共形结构，而不是某个全纯高度函数。

### 4. 实射影平面 `projective_plane`（对跖世界，距离定义单独配置）

RP² = 球面 / 对跖。椭球 chart 本来就双重覆盖球面（`r(u+pi, -v) = r(u, v)`），再商掉对跖映射即可：

```
r(u + pi, pi - v) = -r(u, v)
```

两个恒等式都是精确对称，前提是径向调制**关于 v 偶且关于 pi/2 对称**（即 `cos(2k v)`，等价于偶数阶、相位 pi/2 的谐波）——否则商空间根本不是 RP²，构造期直接报错。

| 事实 | 实测 |
| :--- | :--- |
| chart 层数 | **4 层**：`(u,v)`、`(u+pi,-v)`（同一三维点）、`(u+pi,pi-v)`、`(u,v+pi)`（都是对跖点） |
| 三维实现 | 4 层折叠成 **2** 个互为对跖的三维点（`orbit_positions` 返回 2 个） |
| 高斯-博内 | RP² 自身 χ=1 → 2π；chart 覆盖球面两次、世界两次 → 原始积分 **8π**（实测 25.1168 vs 8π = 25.1327） |
| 不可嵌入 | 与克莱因瓶不同：这里的 chart 映射是**覆盖映射**（2 对 1 到椭球上），不自交 |

**距离定义单独配置（本任务唯一的引擎改动）**：`WorldConfig.distance_mode`

| 取值 | 含义 | 谁在用 |
| :--- | :--- | :--- |
| `"euclidean"`（默认） | 两个三维实现之间的直线距离 | 其余**全部**地图，行为与改动前逐位一致 |
| `"orbit_min"` | 对双方的 chart 副本取最小 | 只有 `projective_plane` |

它的效果可以实测：出口与它的对跖 chart 点在世界距离上为 **0.0**（同一个地方），而两者三维相距 **84.6**；探测器在两个实现上读数都是 **1.000000**；从任一个实现 `sync_position` 都判定胜利；标记测距、障碍物碰撞/可见性、滑动碰撞、出口放置（`min_separation`）全部走同一策略。其它地图的 `distance_mode` 都是 `euclidean`，并有回归测试逐图比对"世界距离 == 朴素三维距离"。

### chart 副本契约升级（数据驱动）

Task 17 时前端把"翻转的孪生坐标"写死成 `(u + 2pi, -v)`；RP² 有 4 层、瓶形克莱因瓶的扭转也不同，写死不再成立。现在由内核下发：

```
"chart_copies": [[du, dv, flip_v], ...]      # 每层一个三元组
"chart_periods": [p_u, p_v]
```

前端 `chartCopies()` 直接照抄，`chartDelta()` 在这些副本中挑最近的——因此"对跖点落在玩家脚下"这种 RP² 语义在前端也是自动正确的（已在 node 侧用真实 payload 逐图核对）。

## 目录结构

```
AI Empowered/
├── AGENTS.md                 # 协作规范（只读）
├── screenshots/  demo/       # 隔离区
├── submission/               # 最终提交内容（推送到 Group 仓库）
├── src/
│   ├── main.py               # 命令行入口
│   └── the_curved_world/     # 核心包
│       ├── config.py         # 配置与校验（含 distance_mode 距离策略）
│       ├── geometry.py       # 光滑曲面几何 + world_distance（距离策略入口）
│       ├── manifold.py       # 封闭流形（环面/椭球/双孔近似/克莱因瓶 x2/打结环面/椭圆曲线/射影平面）
│       ├── detector.py       # 距离敏感探测器（特权）
│       ├── observations.py   # 玩家可见接口（信息边界）
│       ├── world.py          # 世界状态、生成器、调试视图
│       ├── gameplay.py       # 探索玩法引擎（与界面无关）
│       ├── obstacles.py      # 两阶段障碍物散布与接缝碰撞
│       ├── maps/             # 地图注册表与内置地图（插件式）
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
| `web/index.html` / `web/style.css` / `web/app.js` | Web 前端：二维局部俯视切空间地图（Task 15）、迷雾与地形晕渲、仪表盘、上帝视角（调试） |
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
| `src/the_curved_world/manifold.py` | `ClosedManifold` 基类 + 变形环面 / 变形椭球 / 双孔近似 / 克莱因瓶(figure-8) / 瓶形克莱因瓶 / 打结环面 / 椭圆曲线 / 射影平面；解析一阶二阶偏导与 K；chart 周期与副本契约 |
| `tests/test_closed_manifold.py` | 三套模型的解析偏导精度、正则性、周期环绕、高斯-博内积分与信息边界 |
| `src/the_curved_world/maps/`（`__init__.py` + `builtin.py`） | `MapMetadata` + `MapRegistry` + `@register_map`；9 张内置地图与 `world_config_for` |
| `tests/test_map_registry.py` | 注册、按 id 构造、非法 id、元数据完整性、装饰器扩展 |
| `src/the_curved_world/obstacles.py` | `Obstacle` / `ObstacleField`：两阶段散布、安全边距、周期接缝碰撞（走 manifold 的 wrap/chart_relative），并遵循距离策略 |
| `tests/test_obstacles.py`、`tests/test_first_person.py` | 障碍物确定性/安全边距/接缝碰撞；标架正交性与相对移动 |
| `tests/test_obstacle_scale.py` | Task 16 放大后的障碍物尺度、九图生成成功与出生点/出口安全边距 |
| `tests/test_klein_bottle.py` | Task 17：figure-8 浸入的正则性、2π 平移镜像 v、自交圆、法向反向、χ=0、跨缝无瞬移与信息边界 |
| `tests/test_knotted_torus.py` | Task 18：打结环面的解析偏导、χ=0、嵌入性校验（股间距）与"两股三维很近"实测 |
| `tests/test_bottle_klein.py` | Task 18：与公开瓶形公式逐点一致（8.9e-16）、扭转识别、自交、χ=0、网格闭合 |
| `tests/test_elliptic_curve.py` | Task 18：共形模数 τ=i 与数值积分互证、非平坦性、窄孔近邻、非法形变被拒 |
| `tests/test_projective_plane.py` | Task 18：两个对合恒等式、4 层 chart、8π/2π 高斯-博内、`orbit_min` 距离策略与其它地图的回归 |

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
| 第一人称切空间视角 + 视线标架（Task 10） | `gameplay.py`、`web/app.js` | ✅ 已完成（Task 15 起主视图改为二维俯视） |
| 局部雷达小地图（无迷雾/无历史记忆）（Task 10） | `web/app.js` | ✅ 已完成（Task 15 已移除，主视图即局部地图） |
| 两阶段障碍物生成与碰撞（Task 10） | `src/the_curved_world/obstacles.py`、`world.py` | ✅ 已完成 |
| 无缝二维俯视切空间地图（Task 15） | `web/app.js`、`web/index.html`、`web/style.css` | ✅ 已完成 |
| 周期相对包裹的无缝滚动（Task 15） | `web/app.js` | ✅ 已完成 |
| 微地貌等高线 + 高程/漫反射晕渲（Task 15） | `web/app.js` | ✅ 已完成 |
| 刚性圆盘硬碰撞 + 切向滑动（Task 15） | `web/app.js`、`src/the_curved_world/obstacles.py` | ✅ 已完成 |
| 坡度 HUD 与上坡阻尼（Task 11/15） | `web/app.js`、`src/the_curved_world/gameplay.py` | ✅ 已完成 |
| 60FPS 本地控制 + ~200ms 位置同步（Task 14/15） | `web/app.js`、`src/the_curved_world/server.py` | ✅ 已完成 |
| 移除右上角雷达，主视图即局部地图（Task 15） | `web/index.html`、`web/style.css`、`web/app.js` | ✅ 已完成 |
| 增大障碍物体积与安全边距（Task 16） | `src/the_curved_world/config.py`、`maps/builtin.py` | ✅ 已完成 |
| 所见即所撞的 2D 障碍物像素半径（Task 16） | `web/app.js` | ✅ 已完成 |
| 通关结算弹窗 + 自由漫游 / Cleared HUD（Task 16） | `web/index.html`、`web/app.js`、`web/style.css` | ✅ 已完成 |
| 障碍物尺度与安全边距回归测试（Task 16） | `tests/test_obstacle_scale.py` | ✅ 已完成 |
| 克莱因瓶浸入模型（解析微分几何，Task 17） | `src/the_curved_world/manifold.py` | ✅ 已完成 |
| 非平凡 chart 周期与副本识别（`chart_periods` / `chart_copies` / `chart_relative`，Task 17） | `manifold.py`、`gameplay.py`、`obstacles.py` | ✅ 已完成 |
| 跨周期缝的移动与碰撞走 manifold 接口（Task 17） | `gameplay.py`、`obstacles.py`、`server.py` | ✅ 已完成 |
| 前端同口径相对包裹（`twisted` / `chart_periods`，Task 17） | `web/app.js`、`server.py` | ✅ 已完成 |
| 克莱因瓶地图注册与大厅标注（Task 17） | `maps/builtin.py`、`maps/__init__.py`、`web/app.js` | ✅ 已完成 |
| 浸入正则性 / 自交 / 法向反向 / 跨缝连续性测试（Task 17） | `tests/test_klein_bottle.py` | ✅ 已完成 |
| 打结环面关卡（管道沿 (p,q) 环面结，Task 18） | `src/the_curved_world/manifold.py`、`maps/builtin.py` | ✅ 已完成 |
| 经典瓶形克莱因瓶浸入（Task 18） | `manifold.py`、`maps/builtin.py` | ✅ 已完成 |
| 椭圆曲线关卡（共形模型，τ=i 实测，Task 18） | `manifold.py`、`maps/builtin.py` | ✅ 已完成 |
| 实射影平面对跖世界（Task 18） | `manifold.py`、`maps/builtin.py` | ✅ 已完成 |
| 可配置距离策略 `distance_mode`（orbit_min，Task 18） | `config.py`、`geometry.py`、`world.py`、`detector.py`、`gameplay.py`、`obstacles.py` | ✅ 已完成 |
| 数据驱动的 chart 副本契约（`chart_copies` 下发，Task 18） | `manifold.py`、`server.py`、`web/app.js` | ✅ 已完成 |
| 四张新地图的诚实性测试（公式比对 / 嵌入性 / 共形模数 / 轨道距离，Task 18） | `tests/test_knotted_torus.py`、`test_bottle_klein.py`、`test_elliptic_curve.py`、`test_projective_plane.py` | ✅ 已完成 |

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
- **克莱因瓶是浸入而非嵌入**：R³ 中必然自交，且不可定向，因此 (a) 自交圆上两个不同曲面点三维重合，
  探测器与环境距离碰撞**无法区分**它们；(b) 没有全局“外侧”，`normal()` 只是局部一致的解析法向；
  (c) 自交圆两侧各约 0.074 的薄带内，另一支曲面上的障碍物可能在**视口之外**却满足后端碰撞判据（详见 Task 17 小节）。
- **打结环面同理但更极端**：结在嵌入里而不在拓扑里（χ 仍为 0）；两股表面最近约 12 而 `detector_scale = 30`，
  所以探测器对两股读数几乎相同——这是设计意图，不是缺陷。
- **椭圆曲线只是共形模型**：R³ 中不存在完备平坦闭曲面（Hilbert），本图曲率外正内负；"复分析"体现在
  共形结构上，而不是某个全纯高度函数（紧黎曼曲面上不存在非常值全纯函数）。
- **RP² 的距离必须取轨道最小**：`orbit_min` 是唯一改变距离语义的策略，只对 `projective_plane` 开启，
  其余地图保持 `euclidean` 并有逐图回归测试。
- **真亏格 2 仍缺**：`double_torus` 只是外观近似；真亏格 2 需要亏格 2 参数域或隐式曲面引擎（见「计划扩展」）。
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