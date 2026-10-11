# AI 使用记录 (AI_USAGE.md)

> 记录比赛过程中与 AI 编程助手（Codex）的每次交互与产出。
> 规范依据：`AGENTS.md`。每次交互后追加一行记录，不虚构未发生的操作。

## 交互日志

| 日期 | 交互内容 / 目标 | AI 执行的操作 | 涉及文件 | 结果 |
| :--- | :--- | :--- | :--- | :--- |
| 2026-10-11 | 配置本地 Python 环境 | 基于本机 Python 3.13.2 创建 `.venv` 并引导 pip（24.3.1） | `.venv/` | ✅ 完成 |
| 2026-10-11 | 初始化项目目录结构 | 建立只读隔离区与读写开发区，编写基础配置与文档 | `README.md`、`docs/architecture.md`、`pyproject.toml`、`Makefile`、`.gitignore` | ✅ 完成 |
| 2026-10-11 | 调整提交流程（Group 仓库） | README 改为 Group 仓库地址；删除测试文件 `testsubmit`；`AGENTS.md` 增补第 5 节推送规范 | `README.md`、`AGENTS.md` | ✅ 完成 |
| 2026-10-11 | **Task 1 — 数学世界引擎** | 安装 numpy/pytest/matplotlib；实现曲面几何、世界生成、探测器与信息边界；单元测试 | `src/the_curved_world/{config,geometry,detector,observations,world}.py`、`tests/test_{geometry,world_generation,detector}.py` | ✅ 24 项测试通过 |
| 2026-10-11 | **Task 2 — 探索玩法** | 扩展观测（信号/标签/趋势）；实现移动/日志/标记/测量/胜利与终端界面（含输入校验） | `src/the_curved_world/{observations,gameplay,cli}.py`、`tests/test_{gameplay,cli}.py` | ✅ 48 项测试通过 |
| 2026-10-11 | 调整默认探测器尺度（经用户授权） | 将默认 `detector_scale` 由 1.0 调至 2.5，改善信号动态范围 | `src/the_curved_world/config.py` | ✅ 完成 |
| 2026-10-11 | **Task 3 — 3D 可视化与调试视图** | 实现 `build_scene()`（复用同一曲面、网格缓存）与 `MatplotlibRenderer`；玩家视图不泄露隐藏状态、开发者视图显式显示出口/距离/种子；新增 `view` 命令与 `--render/--view` | `src/the_curved_world/render.py`、`{gameplay,cli}.py`、`src/main.py`、`tests/test_render.py` | ✅ 55 项测试通过 |
| 2026-10-11 | **Task 9 — 地图注册表与启动大厅** | 新增 maps.py（MapMetadata + MapRegistry + @register_map 装饰器 + 4 张内置地图 + world_config_for）；服务端新增 GET /api/maps 与 POST /api/session/new，debug 接口按模式严格门禁；前端新增毛玻璃启动大厅（选图/模式/种子）与「新世界/选图」按钮；新增 --map 参数；补充注册表与会话切换测试 | src/the_curved_world/{maps,server,config,geometry}.py、src/main.py、web/{index.html,app.js,style.css}、tests/test_map_registry.py、tests/test_server.py | ✅ 130 项测试全部通过 |
| 2026-10-11 | **Task 8 — 封闭紧致流形重构** | 新增 manifold.py（ClosedManifold 基类 + 变形环面/变形椭球/双孔近似，解析一阶二阶偏导与高斯曲率）；默认世界改为亏格 1 变形环面，边界钳制改为周期环绕；探测器仍用环境三维距离；前端周期迷雾、环绕足迹与封闭三维上帝视角；补充 test_closed_manifold.py | src/the_curved_world/{manifold,config,world,gameplay,server,render}.py、web/app.js、tests/test_closed_manifold.py | ✅ 119 项测试全部通过 |
| 2026-10-11 | **Task 7 — 大尺度流形与微分几何工具链** | 参数域扩到 [-50,50]^2、曲面改为 4 尺度正弦 + 8 混合高斯丘；新增第一基本形式 (E,F,G)/面积元；实现高斯-博内测地三角测角仪与有限次量化切平面指向器；前端改为玩家居中局部切空间视图、按度量畸变网格、按住连续行走与 1/2/3/4 热键；补充大尺度与工具链测试 | src/the_curved_world/{config,geometry,gameplay,server}.py、web/{index.html,style.css,app.js}、tests/test_large_scale.py | ✅ 103 项测试全部通过 |
| 2026-10-11 | **Task 6 — Web 交互与双视角渲染** | 新增仅用标准库的本地 HTTP/静态服务 server.py（GameSession + 四个接口）；新增原生 HTML5/ES6 前端 web/（玩家局部视图 + 迷雾、仪表盘、上帝视角、三角内角和工具）；新增切平面角度与测地三角内角和内核；保持信息边界并新增注入内容扫描测试 | src/the_curved_world/{server,geometry,gameplay}.py、src/main.py、web/{index.html,style.css,app.js}、tests/test_server.py | ✅ 93 项测试全部通过 |
| 2026-10-11 | **Task 5 — 交互式实时游玩** | 渲染器改为就地更新（曲面图元持久化 + 动态图元替换）；新增 `session.py` 阻塞式交互主循环（`[CurvedWorld]> ` 提示符 + 状态摘要）、`--play` 入口、`scan`/`curvature` 命令与 WASD 快捷移动、解析高斯曲率；补充 mock 输入流测试 | `src/the_curved_world/{render,session,cli,geometry,gameplay}.py`、`src/main.py`、`tests/test_session.py` | ✅ 82 项测试全部通过 |
| 2026-10-11 | **Task 4 — 验证与可复现 Demo** | 实现固定种子 Demo 场景 `run_demo()` 与 `--demo-scenario`；补充数学审计、信息泄露审计、端到端 Demo 测试；清理未用导入；撰写最终验证报告并更新文档 | `src/the_curved_world/demo.py`、`src/main.py`、`tests/test_{math_audit,information_boundary,demo}.py`、`docs/final_report.md`、`README.md`、`docs/architecture.md` | ✅ 70 项测试全部通过（含 Task 1-3） |