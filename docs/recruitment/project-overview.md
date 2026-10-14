# CityClean-Agent 项目说明

投递版本：2026-10-14。适用岗位：Agent 应用开发、Python 后端、软件研发。

## 项目定位

CityClean-Agent 是面向城市环卫突发事件的智能决策仿真与评测平台。面对垃圾满溢、道路封闭、车辆故障和紧急清运，系统将治理研判、车辆调度、方案校验和执行反馈串成可观察的闭环。

当前展示使用固定随机种子的合成路网与运营数据。默认无需模型或地图 API Key，普通 CPU 即可运行。真实 DeepSeek 研判为可选能力，需要显式配置并主动调用。

项目由刘东海独立开发。此前参赛版本获得“华为杯”第八届中国研究生人工智能创新大赛国家三等奖，个人独立组队参赛。获奖信息依据作者提供；当前投递版本包含后续工程完善，不等同于原参赛版本。

## 解决的问题

- **资源有限时的治理取舍**：在候选风险点、车辆容量与目标预算约束下，明确优先治理目标。
- **策略和数值计算的职责分离**：模型输出结构化策略，路线、距离、容量和 ETA 交给确定性算法。
- **扰动后的闭环执行**：仿真推进期间注入道路封闭或车辆故障，重新计算并校验方案。
- **结果可复核**：界面展示输入事实、策略、路线、约束校验和车辆时间线；评测保留成功及失败案例。

## 整体架构

```text
React / TypeScript 工作台
          |
FastAPI / Pydantic 版本化接口
          |
合成场景与风险事实 -> 规则 / DeepSeek 治理研判
          |              |
          +------ PolicyDecision 契约 ------+
                                         |
                              确定性策略参数映射
                                         |
                              OR-Tools 车辆调度
                                         |
                              独立 PlanVerifier
                                         |
                              CitySim 执行与反馈
                                         |
                          事件注入 -> 动态重规划
```

| 模块 | 职责 | 主要源码 |
|---|---|---|
| 研判 Agent | 风险、目标、响应时限和治理策略；校验模型输出 | `src/cityclean_agent/agent/` |
| Policy / Domain | 决策契约、策略参数映射、任务和道路模型 | `src/cityclean_agent/policy/`、`src/cityclean_agent/domain/` |
| Optimizer | 车辆分配、路线与容量/时间约束求解 | `src/cityclean_agent/optimizer/` |
| Verifier | 独立重算可达性、容量、必要任务时限、重复分配和 ETA 一致性 | `src/cityclean_agent/verifier/` |
| CitySim / Workflow | 状态推进、事件应用、方案安装与重规划 | `src/cityclean_agent/simulator/`、`src/cityclean_agent/workflow.py` |
| API / 前端 | 合成实验接口、运营操作台、地图与时间线 | `src/cityclean_agent/api/`、`frontend/src/` |
| Benchmark / Tests | 固定场景对照、Gold 错误分析和对抗验证 | `src/cityclean_agent/benchmark/`、`tests/`、`knowledge_base/` |

源码路径均相对于投递包内的 `04-source/CityClean-Agent/`。CitySim 维护仿真状态；模型不直接修改城市状态。不可行或校验失败的方案不会作为成功结果进入执行层。

## 可以直接体验的功能

1. 生成可复现的合成路网、风险点和车辆，调整场景种子与资源预算。
2. 运行规则研判；可选配置 DeepSeek，在同一输入上进行 A/B 比较。
3. 生成车辆调度，观察任务分配、路线、负载和独立校验结果。
4. 启动执行仿真，以 5 分钟步长推进，观察车辆和任务状态。
5. 注入道路封闭、车辆故障、垃圾量突增或紧急清运，观察重规划结果与失败边界。

默认产品入口使用实时生成的合成场景；历史模型轨迹与比赛 fixture 仅用于显式离线评测或独立历史演示入口。

## 评测结果与解释

2026-10-14 在当前代码重新运行固定 Benchmark：9 个场景、3 种条件，共 27 次执行。

| 条件 | 策略来源 | 各场景任务完成率的算术平均 | 全部任务完成的场景 |
|---|---|---:|---:|
| 静态，不重规划 | 不选择新策略 | 59.8% | 2/9 |
| 固定均衡策略重规划 | 固定 BALANCED | 75.9% | 6/9 |
| 事件策略重规划 | 确定性 MockEventAgent | 79.6% | 7/9 |

上述结果反映这组固定场景中重规划的作用，第三行不是 DeepSeek 结果。真实模型冻结 Gold 评测覆盖 40 个审核案例：38 次成功调用、2 次 provider error；成功调用中的策略准确率为 60.53%，宏平均 F1 为 0.5216。结构化契约成功不等于治理判断正确。

详细统计口径、单个真实模型案例的距离代价及错误分析见 `docs/evaluation-at-a-glance.md` 和 `knowledge_base/reports/`。默认复现命令不会调用外部模型。

## 技术与工程实践

- Python、FastAPI、Pydantic；通过契约约束模块输入输出。
- LangChain DeepSeek；将模型输出限制为可校验的治理决策。
- Google OR-Tools；在 CPU 上进行车辆路径与调度求解。
- React 19、TypeScript、Vite、Ant Design；展示场景、策略、路线与执行反馈。
- Pytest；离线测试覆盖领域模型、求解器、校验器、API 和跨模块流程。
- Docker Compose、Nginx；提供同源页面/API 的本地启动入口。

## 当前边界

当前版本未接入真实政府运营数据。天地图只提供可选底图，不参与路径求解。默认权威 Runtime 与设施仓储未装配，相应接口明确显示 unavailable/503；这不影响合成实验链。仿真会话保存在内存，重启后丢失；认证、多人隔离和生产持久化尚未实现。道路不可达、剩余容量不足或紧急时限不可满足时，系统可能返回不可行，需要人工处理。

当前实现没有采用 RAG、多智能体编排或 LangGraph。`docs/product-architecture.md` 中这些内容是后续路线，不应写成已实现成果。

## 阅读与复现入口

- 首先观看投递包中的 `03-demo.mp4`，再查看《启动说明》。
- 完整代码、锁定的前端依赖和离线评测资源在 `04-source/CityClean-Agent/`。
- GitHub：<https://github.com/q001108/CityClean-Agent>，默认分支 `codex/free-development`。整理时仓库为私有，外部访问需要仓库权限；投递包可独立阅读和运行。
- 精确源码版本、文件校验值和验证记录见投递包根目录 `manifest.json`、`SHA256SUMS.txt` 及源码内 `docs/recruitment/verification.md`。
