# CityClean-Agent v0.1 开发规格

## 一、项目基本信息

我们正在参加中国研究生人工智能创新大赛开放赛道赛题一。

项目暂定名：

**CityClean-Agent**

**面向城市突发环卫事件的自主研判与动态调度智能体**

当前阶段不要追求界面，不要加入未经要求的技术栈。

目标是首先构建一个完全可以在本地 CPU 环境运行的 MVP。

开发环境：

- Windows
- 24GB RAM
- 无独立显卡
- Python 优先
- LLM 通过远程 API 调用
- 最终主要使用 DeepSeek 系列及其他国产模型
- 不依赖视觉模型
- 不训练任何模型

---

## 二、项目核心思想

系统不是让 LLM 直接进行车辆路径规划。

职责必须严格划分。

### 1. LLM

负责：

- 理解非结构化城市事件；
- 判断事件类型、风险等级和处置优先级；
- 生成结构化治理目标和约束。

LLM 不负责：

- 直接计算车辆路线；
- 计算最短路径；
- 计算车辆容量；
- 计算确定性的距离和时间；
- 判断数学约束是否真正成立。

### 2. OR-Tools

根据城市状态、待执行任务和治理策略完成车辆动态调度。

### 3. Verifier

独立检查方案是否违反硬约束。

Verifier 不调用 LLM。

### 4. CitySim

模拟方案执行后城市环境的变化。

系统形成：

```text
感知
→ 研判
→ 优化
→ 验证
→ 执行
→ 环境反馈
→ 再规划
```

闭环。

---

## 三、v0.1 范围

只支持四种突发事件。

### 1. WASTE_OVERFLOW

垃圾点即将或已经满溢。

### 2. VEHICLE_BREAKDOWN

环卫车辆故障。

### 3. ROAD_CLOSURE

道路封闭。

### 4. URGENT_TASK

市民投诉、大型活动等产生临时紧急任务。

暂时禁止主动加入：

- RAG
- 向量数据库
- 多智能体框架
- MCP
- 地图 API
- 图像识别
- 实时 IoT
- 强化学习
- 本地大模型
- 微调
- Kubernetes
- 微服务拆分

坚持最小实现。

---

## 四、核心实体

优先使用 dataclass 或 Pydantic Model。

### WastePoint

```text
- id
- node_id
- capacity
- current_load
- generation_rate
- waste_type
- zone_type
- priority
```

如有需要，可以保留 `x`、`y` 用于后续可视化，但核心距离和路径计算应基于道路网络，而不是直接使用二维坐标计算欧氏距离。

### Vehicle

```text
- id
- current_node_id
- capacity
- current_load
- status
- speed
- assigned_tasks
```

### TransferStation

```text
- id
- node_id
- capacity
```

### Road

```text
- id
- from_node
- to_node
- distance
- travel_time
- status
```

### CityState

```text
- current_time
- waste_points
- vehicles
- transfer_stations
- road_network
- active_events
- tasks
- active_plan
```

道路网络应作为距离、通行时间和道路可达性的统一计算来源。

---

## 五、事件模型

统一使用：

### CityEvent

```text
- event_id
- event_type
- timestamp
- location
- description
- affected_entities
- severity
- deadline
- metadata
```

需要支持事件动态注入。

`CityEvent` 表示：

> 城市中发生了什么。

事件不应直接等同于 Optimizer 执行的调度任务。

---

## 六、任务模型

增加统一任务对象：

### ServiceTask

```text
- task_id
- source_event_id
- target_id
- demand
- priority
- deadline
- status
```

`ServiceTask` 表示：

> 实际需要车辆执行什么任务。

例如：

```text
CityEvent：
学校附近垃圾点发生异常满溢

↓

ServiceTask：
在指定 deadline 前完成 W17 清运
```

Event 与 Task 必须分离。

任务状态的具体 Enum 和状态转换细节，可以在 Architecture Review 中进一步确定，但必须至少能够区分：

- 尚未完成的任务；
- 已完成任务。

动态重规划时，已经完成的任务不得再次进入新的调度计划。

---

## 七、LLM 输出

LLM 永远不能输出车辆的具体路线。

LLM输出类似：

### PolicyDecision

```json
{
  "event_type": "...",
  "risk_level": 1,
  "reasoning_summary": "...",
  "affected_area": [],
  "response_deadline": 20,
  "priority_targets": [],
  "policy_profile": "URGENT_RESPONSE",
  "constraints": []
}
```

所有字段必须经过 Pydantic 校验。

v0.1 可首先使用 MockLLM，不要一开始接真实 API。

### 关于优化权重

LLM 不直接生成任意浮点优化权重。

例如不要要求模型自行决定：

```text
response_time = 0.43
distance = 0.17
```

LLM 只输出有限、可解释的治理策略，例如：

```text
BALANCED
URGENT_RESPONSE
OVERFLOW_CONTROL
MINIMAL_RESCHEDULE
```

然后由确定性代码将这些策略映射为 Optimizer 使用的参数或权重。

具体策略数量和映射值保持简单，在 Architecture Review 中确定即可。

---

## 八、调度优化

使用 OR-Tools。

初期可以将问题简化为动态 CVRP。

Optimizer 至少接收：

```text
CityState
ServiceTask
PolicyDecision 对应的确定性策略参数
已有计划（如存在）
```

Optimizer 不读取自然语言，也不调用 LLM。

### 硬约束

至少考虑：

- 故障车辆不能执行任务；
- 车辆容量不能超限；
- 封闭道路不能通行；
- 每个任务不能被重复服务；
- 高优先级紧急任务需要满足 deadline；
- 不可达任务不能生成伪造的可执行路线。

能够直接表达在 OR-Tools 中的硬约束，应尽量直接加入 Optimizer。

Verifier 再进行独立二次检查。

### 软目标

v0.1 先保持简单。

可以围绕：

```text
total_distance
lateness_penalty
unserved_task_penalty
rescheduling_cost
```

构建目标函数。

未来正式实验再根据需要扩展。

以下指标主要作为 Metrics 统计，而不是强制全部塞进第一版优化目标：

```text
average_response_time
overflow_count
task_completion_rate
urgent_task_completion_rate
```

### 不可行方案

如果在硬约束下不存在可行方案，Optimizer 必须显式返回：

```text
INFEASIBLE
```

不得为了得到结果而生成违反硬约束的调度方案。

例如：

```text
所有车辆故障
所有可用道路封闭
关键任务物理上无法在 deadline 内完成
```

应被允许产生 `INFEASIBLE`。

此时系统输出明确原因，并停止无限重复重规划。

---

## 九、调度结果模型

Optimizer 不应返回无结构的列表。

至少定义：

### DispatchPlan

```text
- plan_id
- vehicle_routes
- unassigned_tasks
```

### VehicleRoute

```text
- vehicle_id
- task_sequence
```

必要的 ETA、车辆预计载重等字段，由 Architecture Review 判断是否需要加入。

v0.1 不应为了追求完整而提前设计过于复杂的计划 Schema。

---

## 十、CitySim

第一版不要使用专业仿真软件。

自己实现离散时间环境即可。

例如：

```text
每一个 simulation tick = 5 minutes
```

每个 tick 至少需要处理：

1. 已发生的外部事件；
2. 车辆按照当前计划移动；
3. 完成到达和服务；
4. 垃圾点继续产生垃圾；
5. 更新任务和车辆状态；
6. 检查是否出现新的满溢或超时；
7. 更新时间。

具体事件顺序可以在 Architecture Review 中微调，但一旦确定后应保持 deterministic。

CitySim 必须能够支持：

```text
reset()
step()
inject_event()
get_state()
calculate_metrics()
```

同样的初始状态、事件、计划和随机种子应尽可能产生相同结果。

---

## 十一、事件对环境的实际影响

事件不能只作为文本保存在 `active_events` 中。

例如：

### VEHICLE_BREAKDOWN

必须真正把对应车辆状态改为故障，并使其无法继续接受新的调度任务。

### ROAD_CLOSURE

必须真正修改道路状态，使 Optimizer 和 Verifier 都不能继续使用该道路。

### WASTE_OVERFLOW

必须对应真实 WastePoint 状态变化。

### URGENT_TASK

必须能够生成或提升对应 `ServiceTask` 的治理优先级。

---

## 十二、动态重规划

v0.1 至少支持一次完整的动态重规划过程：

```text
已有调度计划
↓
发生车辆故障或其他异常
↓
旧计划部分失效
↓
保留已经完成的任务和真实环境状态
↓
重新调度剩余任务
↓
生成新的 DispatchPlan
↓
Verifier 检查
↓
CitySim 继续执行
```

不得：

- 把已经完成的任务重新加入计划；
- 让车辆瞬间返回初始位置；
- 重置已经发生的垃圾量变化；
- 为了方便重新规划而重新初始化整个城市。

---

## 十三、Verifier

实现独立 Verifier。

至少检查：

```text
vehicle_available
capacity_valid
road_accessible
deadline_valid
duplicate_assignment
unreachable_task
```

返回：

### VerificationResult

```json
{
  "valid": true,
  "violations": []
}
```

Verifier 不允许使用 LLM。

Optimizer 应主动满足能够表达的硬约束。

Verifier 负责独立二次验证，而不是替 Optimizer 修复方案。

---

## 十四、Metrics

从第一版开始把 Metrics 独立出来。

至少预留：

```text
task_completion_rate
urgent_task_completion_rate
overflow_count
average_response_time
total_distance
rescheduling_count
constraint_violation_count
total_cost
```

如果某些指标 v0.1 暂时无法准确实现，可以先保留接口，不必为了全部实现而增加大量复杂逻辑。

---

## 十五、Benchmark

代码架构必须支持批量运行随机场景。

例如未来能够实现：

```python
run_scenario(seed=123)
run_scenario(seed=456)
```

相同 seed 应尽可能产生相同场景。

以后需要比较：

### Baseline A：固定规则

例如最近可用车辆优先。

### Baseline B：LLM 直接决策

该模式只作为实验 Baseline。

正式系统禁止 LLM 直接规划车辆路线，但 Benchmark 可以让 LLM 直接输出车辆—任务分配或访问顺序，再由 Verifier 测量其约束违规情况。

### Baseline C：纯 OR-Tools

使用固定策略参数，不使用 LLM 事件理解。

### Proposed System

```text
LLM
+
确定性策略映射
+
OR-Tools
+
Verifier
+
CitySim
```

Benchmark 的目的不是 v0.1 就完成全部实验，而是保证当前代码结构以后能够支持这些实验。

---

## 十六、工程结构

统一采用标准 src-layout。

推荐：

```text
CityClean-Agent/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── docs/
│   └── spec-v0.1.md
│
├── src/
│   └── cityclean_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── domain/
│       ├── simulator/
│       ├── agent/
│       ├── optimizer/
│       ├── verifier/
│       └── benchmark/
│
├── tests/
├── assets/
└── scripts/
```

如果 Architecture Review 认为需要增加一个很小的 `policy/` 或 `metrics/` 模块，可以提出理由后增加。

不要过度工程化。

暂时不要实现前端和 API 服务。

---

## 十七、主程序

正式本地运行入口统一为：

```powershell
python -m cityclean_agent
```

CLI Demo 可以通过 `__main__.py` 或内部 demo module 实现。

---

## 十八、v0.1 完成标准

v0.1 最终需要完成：

1. 项目目录设计；
2. 核心数据模型；
3. CityEvent 与 ServiceTask 分离；
4. CitySim 最小实现；
5. 四种事件动态注入；
6. Mock Event Agent；
7. 确定性的治理策略参数映射；
8. OR-Tools 最小调度器；
9. DispatchPlan；
10. Verifier；
11. 动态重规划；
12. Metrics 基础实现；
13. Benchmark 基础结构；
14. pytest；
15. 一个 CLI Demo。

最终需要能够执行：

```powershell
python -m cityclean_agent
```

并看到类似：

```text
正常运行
→ 生成初始计划
→ CitySim 推进
→ 注入车辆故障
→ 旧计划受到影响
→ Agent 产生治理策略
→ OR-Tools 对剩余任务重新调度
→ Verifier 检查
→ CitySim 继续运行
→ 输出新的 Metrics
```

如果调度问题无解，则应明确输出：

```text
INFEASIBLE
```

及原因，而不是生成非法计划。

---

## 十九、Codex 开发原则

本文件定义的是：

> v0.1 最终需要达到的状态。

不要求 Codex 第一次任务就一次性实现全部内容。

首次任务只进行 Architecture Review。

首次 Architecture Review 应重点检查：

1. 目录结构；
2. 核心 Domain Model；
3. Event 与 ServiceTask 的关系；
4. CitySim 的状态所有权；
5. DispatchPlan 结构；
6. Optimizer 与 Verifier 边界；
7. 动态重规划的数据流；
8. INFEASIBLE 的处理；
9. pytest 测试策略；
10. 当前规格中是否仍存在关键歧义。

首次 Architecture Review 阶段不要实现业务代码。

架构确认后，再按模块逐步实现。

每完成一个模块都运行相关测试，不要一次性生成整个项目后再测试。

不要擅自扩大需求。

如果发现规格存在真正影响实现的设计问题，先指出问题和最小修改建议。