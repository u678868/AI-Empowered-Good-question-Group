# 架构与目录规范

## 1. 目标

明确项目分区、模块职责与协作边界，并保证 `README.md` 状态表与代码实际进度同步。

## 2. 目录分区

| 分区 | 目录 / 文件 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| 隔离区 | `screenshots/`、`demo/`、`submission/`、`AGENTS.md` | 只读 | 参赛材料与规范文件 |
| 开发区 | `src/`、`web/`、`tests/`、`docs/`、`scripts/`、`temp/`、`README.md`、`AI_USAGE.md`、构建配置 | 读写 | 源码、前端、测试、文档、工具脚本与配置 |

## 3. 模块分层（实际实现）

```
src/main.py                      入口：终端游戏 / --demo / --demo-scenario / --render / --view / --serve
src/the_curved_world/
  config.py        配置数据类与校验（Domain / WaveComponent / GaussianHill / SurfaceConfig / WorldConfig）
  geometry.py      SmoothSurface（height / position / gradient / normal / contains / sample_grid）+ ambient_distance
  manifold.py      ClosedManifold 基类 + 变形环面 / 变形椭球 / 双孔近似 / 克莱因瓶 / 射影平面等；
                   chart 识别接口（chart_periods / wrap / chart_copies / chart_relative）
  differential.py  第一/第二基本形式、面积元、Levi-Civita 平行移动与渐近方向
  detector.py      Detector（特权：signal / distance）+ DetectorConfig
  observations.py  信息边界：ObservationConfig / PlayerObservation / PlayerObserver / PlayerView
  world.py         WorldState（特权）/ DebugView / WorldGenerator
  obstacles.py     两阶段障碍物生成、周期接缝碰撞与切线滑动
  gameplay.py      ExplorationGame：移动、观测、日志、标记、测量、绳索接口、胜利与计分
  quest.py         五大学派几何任务链：QuestManager + 各 GeometricQuest 与推导 payload
  scanner.py       测地三角测量、曲率预检、双向 Gauss-Bonnet 可行性检查
  ropes.py         有限绳池、节点图、外接圆拉取（BDP 测地圆）
  render.py        PlotMode / RenderConfig / SurfaceMeshCache / Scene / build_scene / MatplotlibRenderer
  session.py       阻塞式交互主循环（终端游玩）
  demo.py          run_demo()：可复现的完整 Demo 场景
  cli.py           GameCLI：命令解析、呈现、视图切换
  server.py        标准库本地 HTTP/静态服务：GameSession + /api/* 接口与特权门禁
  maps/            地图注册表与 9 张内置地图（MapMetadata / MapRegistry / @register_map）
web/               index.html / app.js / style.css / vendor/katex（离线公式资源）
scripts/           scan_guardrails.py（红线扫描）/ package_submission.py（镜像与邮件压缩包）
tests/             36 个测试模块，共 269 项用例
```

**分层依赖方向（单向）：** `cli` / `session` / `render` / `demo` / `server` -> `gameplay` -> `quest` / `ropes` / `scanner` / `obstacles` -> `world` -> `observations` / `detector` -> `manifold` / `geometry` / `differential` -> `config`；前端 `web/` 只经 `/api/*` 读取玩家可见载荷。

关键约束：

- 玩家侧对象（`PlayerView` / `PlayerObserver` / `PlayerObservation` / `Marker` / `LogEntry`）**结构上无法访问出口**。
- 出口与精确距离只能经显式 `debug_view()` 获取，且仅在 `--view debug` 下渲染。
- 渲染层的曲面**始终**取自仿真的同一个 `SmoothSurface`。
- **参数空间的周期性折回必须问 surface**：用 `surface.wrap(u, v)` / `chart_relative(...)`，
  不得硬编码 `2*pi`。环面族是 `(2pi, 2pi)`，克莱因瓶是 `(4pi, 2pi)`（平移 2π 会翻转 v），
  射影平面是 `(2pi, 2pi)` 但每个点有 **4 层** chart（见 `manifold.py` 模块文档）。
- **chart 副本必须由内核下发**：`chart_copy_transforms()` -> `((du, dv, flip_v), ...)`，
  经 `/api/state/player` 的 `chart_copies` 字段抵达前端；前端不得写死某一种扭转。
- **距离语义只有一处开关**：`WorldConfig.distance_mode`（`euclidean` 默认 / `orbit_min` 用于商空间，
  目前只有 `projective_plane`）。所有距离相关的代码（探测器、胜利判定、测距、指向器、
  障碍物碰撞与可见性、出口放置）都必须走 `world_distance(...)` 或 `WorldState.ambient_distance(...)`，
  不得直接调用 `ambient_distance(点, 点)`。

## 4. 开发约定

- 遵循 `AGENTS.md` 的原子化提交与 Conventional Commits 规范。
- 每次向 `src/` 新增核心模块后，同步更新 `README.md` 的「核心文件清单」与「功能状态表」。
- 严禁虚构功能：未完成项必须标注为 `未实现` 或 `[wip] 开发中`。