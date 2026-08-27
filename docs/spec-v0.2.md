# CityClean-Agent v0.2 开发规格

## 一、版本定位

v0.2 在 v0.1 已完成的城市事件治理与动态调度闭环之上，增加：

1. 面向市民投诉的自然语言交互展示；
2. 真实 DeepSeek API 结果的可追溯冻结回放；
3. 从投诉、事件结构化、治理研判到执行反馈的完整叙事；
4. 与消融实验一致的模式对照入口；
5. 基于已验证事实的大模型最终总结。

v0.2 的目标不是把项目改造成通用聊天机器人，也不是让 LLM 取代 OR-Tools、Verifier 或 CitySim。

本版本面向：

- 中国研究生人工智能创新大赛现场展示；
- 论文或答辩中的工作流说明；
- 真实模型实验结果的可复现演示；
- 消融实验差异的直观呈现。

v0.1 中未被本文件明确修改的规则继续有效。

---

## 二、当前基线

v0.2 开发开始前，项目已经具备：

- `CityEvent → PolicyDecision → TaskBuilder → OR-Tools → Verifier → CitySim → Metrics` 闭环；
- 四类事件：`WASTE_OVERFLOW`、`VEHICLE_BREAKDOWN`、`ROAD_CLOSURE`、`URGENT_TASK`；
- 确定性 Event Agent 与真实 DeepSeek Event Agent；
- 严格结构化的 `PolicyDecision`；
- 动态重规划和独立验证；
- 固定随机种子与离线 Benchmark；
- React + TypeScript + Vite 比赛展示前端；
- 真实后端结果生成的 JSON fixture；
- 真实 DeepSeek API Gold、自然语言和端到端实验结果。

当前项目配置和冻结实验记录中的模型标识为：

```text
deepseek-v4-flash
```

模型标识必须从实际运行或冻结轨迹的 provenance 中读取。前端不得仅凭代码默认值声称某次展示使用了特定模型。

当前冻结治理评测结果为：

```text
Gold cases: 40
Successful calls: 38
Contract success rate: 95.00%
Policy accuracy: 60.53%
Macro-F1: 0.5216
Paired context accuracy: 31.25%
Provider failures: 2
```

这些结果是 v0.1 冻结评测事实，不代表模型在所有城市或真实生产环境中的泛化能力。

---

## 三、v0.2 核心目标

### 1. 展示 LLM 的“治理大脑”作用

评委应能够看见：

```text
市民投诉
→ 信息理解与确认
→ 结构化 CityEvent
→ DeepSeek 治理研判
→ PolicyDecision
→ 确定性策略映射
→ OR-Tools 调度
→ Verifier 独立验证
→ CitySim 执行
→ Metrics 环境反馈
→ 大模型生成最终说明
```

LLM 的价值主要体现在：

- 理解非结构化投诉语境；
- 区分常规、敏感和紧急治理场景；
- 选择有限、可解释的治理策略；
- 生成风险等级、优先目标和简短治理理由；
- 将已验证的执行事实转换成面向市民或管理者的最终说明。

### 2. 保持确定性模块的权威边界

LLM 仍然不得：

- 计算车辆路线；
- 生成实际道路轨迹；
- 计算最短路径、距离、容量或 ETA；
- 直接生成 Optimizer 浮点权重；
- 宣布一个未经 Verifier 检查的方案安全可执行；
- 修改 CitySim 的最终事实；
- 在最终总结中创造不存在的指标或执行结果。

### 3. 展示真实实验而非伪造对话

任何被标记为：

```text
真实 DeepSeek API
真实模型回复
真实闭环执行
```

的内容，都必须来自实际运行并保存的冻结轨迹。

人工编写的讲解文字、场景标题或演示脚本必须与模型回复区分，不能伪装成真实模型输出。

---

## 四、v0.2 范围

v0.2 必须完成：

1. 一个投诉闭环主演示场景；
2. 投诉消息、结构化事件、治理决策、执行步骤和最终总结的统一展示契约；
3. 真实 DeepSeek API 轨迹的离线冻结与 provenance；
4. Full、Fixed、Static 三种消融条件的对照入口；
5. 基于同一初始状态、同一事件和同一随机种子的公平比较；
6. 真实 API 失败时不影响比赛主演示；
7. 1920×1080 下可运行、可截图、可复现的比赛页面；
8. 对精选案例和全量实验结果的明确区分。

v0.2 可以在不改变核心架构的前提下增加：

- 很小的 complaint intake 模块；
- 很小的 trace/provenance 模块；
- 很小的 final summary 模块；
- 新的只读前端 fixture contract；
- 对应的 pytest 和 Playwright 验收。

---

## 五、v0.2 非目标

本版本不做：

- 通用开放域聊天机器人；
- 面向任意城市、任意地点的真实生产投诉平台；
- 浏览器直接持有或调用 DeepSeek API Key；
- 比赛现场必须依赖网络的主演示；
- GIS、地图 API 或真实道路导航；
- 语音、图片或视频投诉识别；
- RAG、向量数据库或知识库问答；
- 多智能体框架；
- MCP；
- 模型微调；
- 强化学习；
- 实时 IoT；
- 新增微服务或 Kubernetes；
- 展示模型隐藏思维链；
- 自动宣称项目已经在真实城市生产部署。

Live API 可以继续通过显式 opt-in 的开发脚本生成新轨迹，但浏览器现场自由输入和实时 API 调用不属于 v0.2 完成条件。

---

## 六、投诉接入边界

### 1. 当前能力边界

现有自然语言评测使用的是：

```text
已结构化 CityEvent
+ natural_language_description
→ DeepSeekEventAgent
→ PolicyDecision
```

它证明模型能够利用投诉描述作为治理语境，但不等价于已经实现：

```text
任意多轮市民对话
→ 自动追问
→ 自动构造可信 CityEvent
```

v0.2 必须明确补上或限制这一层，不能只在前端伪造一段多轮聊天。

### 2. Complaint Intake 职责

Complaint Intake 负责：

- 保存用户和助手的展示消息；
- 从投诉文本提取候选事件类型；
- 提取位置描述和受影响对象描述；
- 判断是否缺少演示场景要求的关键信息；
- 必要时生成简短追问；
- 生成结构化投诉摘要；
- 将候选信息交给确定性 resolver 构造 `CityEvent`。

Complaint Intake 不负责：

- 车辆路线；
- 调度计划；
- 城市对象的自由创建；
- 将任意自然语言地点直接视为合法节点；
- 绕过现有 `CityEvent`、`PolicyDecision` 或 Verifier 合同。

Complaint Intake 可以通过一个小型、严格结构化的 DeepSeek adapter 实现，但不得引入多智能体框架。该 adapter 的输出模型必须与 `PolicyDecision` 分离，不能复用治理决策 Schema 充当投诉解析结果。

第一版投诉会话只要求支持短流程：

```text
用户投诉
→ 模型确认或最多一次必要追问
→ 用户补充（如需要）
→ 结构化事件确认
```

如果首条投诉已经包含当前固定场景所需信息，不得为了让页面看起来更像聊天而伪造一次无意义追问。

冻结主演示中每条 `MODEL_GENERATED` 助手消息都必须来自真实保存的 API 调用。

### 3. 确定性实体解析

v0.2 不使用 GIS、RAG 或外部地点服务。

投诉中的地点和对象只能映射到当前精选演示场景预先声明的实体别名。

例如：

```text
“活动出口” → WU
“学校门口垃圾点” → WO
```

未知地点或未知对象必须：

- 进入 `NEEDS_CLARIFICATION`；或
- 被拒绝为当前演示场景不支持。

不得让 LLM 虚构节点、WastePoint、Vehicle、Road 或 Task ID。

---

## 七、投诉会话模型

v0.2 增加只面向投诉展示和轨迹生成的模型。

### ComplaintMessage

```text
- message_id
- role: USER | ASSISTANT
- content
- created_at
- source: USER_AUTHORED | MODEL_GENERATED | EDITORIAL
```

其中：

- `USER_AUTHORED` 表示用户提交或用户为实验主动编写的投诉；
- `MODEL_GENERATED` 必须来自真实保存的模型调用；
- `EDITORIAL` 只能用于页面讲解，不能伪装成对话内容。

### ComplaintIntakeResult

```text
- status: COLLECTING | NEEDS_CLARIFICATION | READY | REJECTED
- complaint_summary
- candidate_event_type
- location_text
- affected_entity_mentions
- missing_fields
- rejection_reason
```

### ComplaintSession

```text
- session_id
- scenario_id
- messages
- intake_result
- resolved_event
```

`resolved_event` 必须是经过确定性实体解析和 Domain 校验的现有 `CityEvent`。

第一版只要求支持固定精选场景的短会话。不要为了未来需求提前设计复杂会话状态机。

---

## 八、DeepSeek 治理研判

投诉成功解析为 `CityEvent` 后，继续使用现有 `DeepSeekEventAgent` 生成结构化 `PolicyDecision`。

必须保留现有约束：

- temperature = 0；
- 严格结构化输出；
- event_type 与结构化事件一致；
- priority target 必须存在于当前 CityState；
- response deadline 不早于当前模拟时间；
- policy_profile 只能来自固定枚举；
- 禁止 Optimizer 权重字段；
- reasoning summary 非空且长度受限；
- API、结构化输出或跨对象校验失败必须显式失败。

模型只看到治理所需的紧凑状态摘要，不直接读取完整内部对象或敏感配置。

页面可以展示：

- 结构化输入摘要；
- `PolicyDecision`；
- `reasoning_summary`；
- 有限的治理约束；
- 模型和轨迹 provenance。

页面不得展示或声称展示模型隐藏思维链。

---

## 九、真实 API 冻结轨迹

### 1. 默认策略

比赛主演示默认使用：

```text
RECORDED_REAL_API
```

含义是：

> 轨迹由真实 DeepSeek API 调用和真实 CityClean 后端闭环生成，之后冻结为只读 JSON，用于稳定回放。

这不是 Mock 数据，也不是比赛现场重新调用 API。

### 2. TraceProvenance

每条真实模型轨迹至少保存：

```text
- trace_id
- trace_source: RECORDED_REAL_API | LIVE_API | DETERMINISTIC
- model_id
- captured_at
- scenario_id
- dataset_version
- seed
- complaint_contract_version
- policy_contract_version
- frontend_contract_version
- input_hash
- success
- error_type
```

`model_id` 对 `RECORDED_REAL_API` 和 `LIVE_API` 必填；对纯确定性轨迹应为 `null`，不得填写一个未实际调用的模型名称。

不得保存：

- API Key；
- Access Token；
- Authorization Header；
- Cookie；
- 用户真实身份信息；
- 未脱敏的敏感投诉信息；
- Provider 私有响应内部字段，除非确有审计必要且经过脱敏。

### 3. 轨迹真实性

冻结轨迹必须由生成脚本从实际对象白名单投影产生，不能由前端手写业务结果。

生成后至少验证：

- JSON schema；
- event 与 decision 合同；
- optimizer 和 verifier 结果；
- final metrics；
- provenance 必填字段；
- 不含敏感信息。

相同冻结文件必须产生确定性相同的展示结果。

---

## 十、最终大模型总结

### 1. 定位

最终总结用于把已验证的系统事实转换为适合市民或管理者阅读的说明。

它不是新的治理决策，不参与调度，也不改变系统状态。

### 2. 输入边界

总结模型只能接收以下白名单事实：

- 已确认投诉摘要；
- 结构化 `CityEvent`；
- 已校验的 `PolicyDecision`；
- Optimizer 状态和任务序列摘要；
- Verifier 状态和 violations；
- CitySim 最终任务状态；
- 最终 Metrics；
- 明确标记的 INFEASIBLE 或失败原因。

总结模型不得接收 API Key、完整内部对象或无关敏感数据。

### 3. FinalNarrativeSummary

```text
- headline
- incident_summary
- governance_summary
- dispatch_summary
- verification_summary
- outcome_summary
- citizen_reply
- fact_refs
```

`fact_refs` 引用输入白名单中的事实 ID。

页面中的数值 Metrics 由确定性组件单独渲染。大模型总结不作为数值事实的唯一来源。

### 4. 校验与降级

最终总结必须经过：

- Pydantic 结构校验；
- fact reference 校验；
- 禁止新增任务、车辆、道路或指标字段；
- 禁止把 `FAIL`、`INFEASIBLE` 或非零 violations 改写为成功；
- 禁止声称执行了不存在的模块。

如果总结调用失败：

- 闭环结果仍然有效；
- 页面使用确定性模板生成简短结果说明；
- 不得把总结失败误报为整个治理流程失败。

比赛默认回放中使用的最终总结也必须来自冻结的真实调用，或明确标记为确定性模板。

---

## 十一、展示模式与消融实验

### 1. 前端入口

v0.2 页面应区分：

#### 闭环演示

展示一条真实 DeepSeek 冻结投诉轨迹及完整执行过程。

#### 消融对照

在同一场景下查看三个实验条件的差异。

#### 实验说明

展示精选案例声明、数据来源和全量冻结评测摘要。

Live API 现场输入可以保留为开发者 opt-in 能力，但不是主导航必需入口。

### 2. 三种对照条件

#### FULL_LLM_POLICY_REPLAN

```text
真实 DeepSeek PolicyDecision
+ 确定性策略映射
+ OR-Tools 重规划
+ Verifier
+ CitySim
```

#### FIXED_BALANCED_REPLAN

```text
固定 BALANCED 策略
+ OR-Tools 重规划
+ Verifier
+ CitySim
```

该模式移除 LLM 的事件治理策略选择，但保留重规划。

#### STATIC_NO_REPLAN

```text
应用相同事件和任务变化
+ 不执行动态重规划
+ CitySim 继续运行
```

该模式用于测量重规划本身的贡献。

### 3. 与现有 BenchmarkMode 的关系

现有：

```text
EVENT_POLICY_REPLAN
```

使用的是确定性 `MockEventAgent`，不能直接在页面中改名为 DeepSeek 模式。

只有满足以下条件时，结果才能标记为 `FULL_LLM_POLICY_REPLAN`：

1. 使用相同初始状态；
2. 使用相同事件字段和时间；
3. 使用相同随机种子；
4. PolicyDecision 来自有 provenance 的真实 DeepSeek 轨迹；
5. 后续 TaskBuilder、Optimizer、Verifier 和 CitySim 实际执行；
6. 结果由统一 trace adapter 生成。

如果真实 DeepSeek 选择的 policy profile 与确定性 Event Agent 相同，仍必须保留真实模型 provenance，不能仅凭结果相同进行身份替换。

### 4. 公平比较

三种条件必须共享：

- 初始 CityState；
- 外部事件；
- 事件时间；
- TaskBuilder 规则；
- CitySim tick；
- 随机种子；
- 最大模拟时间；
- Metrics 计算方式。

三个条件之间只允许存在规格定义的策略和重规划差异。

不得为让 Full 模式更好看而修改其他条件的输入或停止时间。

---

## 十二、主演示案例

### 1. v0.2 首选案例

首选：

```text
urgent_timing_tradeoff_live
```

投诉语境：

> 大型活动刚结束，出口处人流密集，需要尽快完成临时清运任务，以保障疏散通行和环境卫生。

选择理由：

- 已有真实 DeepSeek API 闭环成功结果；
- PolicyDecision 为 `URGENT_RESPONSE`；
- Verifier 通过；
- 紧急任务最终完成；
- 与 Fixed 和 Static 存在可解释差异；
- 能展示“治理优先级与调度成本之间的权衡”，而不是只展示最短距离。

冻结结果表明：

```text
FULL_LLM_POLICY_REPLAN（真实 DeepSeek 冻结轨迹）:
  task completion = 100%
  urgent completion = 100%
  average response time = 11.67

FIXED_BALANCED_REPLAN:
  task completion = 100%
  urgent completion = 100%
  average response time = 13.33

STATIC_NO_REPLAN:
  task completion = 66.67%
  urgent completion = 0%
  urgent task remains unfinished
```

距离差异必须如实展示并解释为治理策略权衡，不能只展示对 Full 模式有利的指标。

### 2. 可选第二案例

可选：

```text
overflow_service_tradeoff_live
```

该案例适合放在压力场景或消融页面，因为 Event Policy 可以完成满溢治理任务，而 Fixed 和 Static 保留未完成任务。

该案例总距离较大，必须同时展示服务完成与距离成本，不能包装成无代价的全面提升。

### 3. 暂不作为消融主演示

```text
road_closure_context_live
```

该场景可以展示道路封闭闭环，但当前三个 Benchmark 条件的最终指标相同，不适合证明 LLM 或重规划的增量贡献。

### 4. 精选案例声明

页面必须标记：

```text
精选展示案例
```

并提供或链接冻结全量实验摘要。

不得用精选案例替代全量准确率、Macro-F1 或失败案例披露。

---

## 十三、前端叙事要求

### 1. 页面结构

v0.2 投诉闭环页面优先采用：

```text
投诉对话区
+ 事件/治理研判区
+ 执行工作流区
+ 城市逻辑拓扑
+ 最终反馈区
```

不要求五个区域同时以等面积展示。

应根据阶段突出当前最重要的信息：

- 投诉阶段突出用户描述和关键信息确认；
- 研判阶段突出结构化事件、风险和策略；
- 执行阶段突出 TaskBuilder、Optimizer、Verifier 和 CitySim；
- 最终阶段突出完成结果、Metrics 和最终回复；
- 消融阶段突出三种条件的关键差异。

### 2. 投诉窗口

投诉窗口必须显示：

- 用户实际提交内容；
- 真实模型回复或明确标记的模板回复；
- 对话当前状态；
- 结构化事件何时确认；
- 模型输出来源。

对话可以在面板内部滚动，但主要治理叙事应在 1920×1080 首屏内保持可理解。

不要展示长篇原始 JSON 或类似开发日志的内容作为主视觉。

### 3. 工作流窗口

至少展示：

```text
投诉接入
→ CityEvent
→ DeepSeek 研判
→ TaskBuilder
→ OR-Tools
→ Verifier
→ CitySim
→ 最终总结
```

模块状态至少包括：

```text
NOT_REACHED
RUNNING
SUCCESS
FAIL
INFEASIBLE
```

冻结回放可以逐帧展示状态，但不得伪造模块调用时间或流式 token。

### 4. 真实性标签

页面应使用紧凑标签区分：

- `真实 API 冻结轨迹`；
- `确定性稳定回放`；
- `实时 API`；
- `固定策略消融`；
- `无重规划消融`；
- `逻辑拓扑`；
- `任务序列，不代表实际道路轨迹`。

### 5. 第一眼问题

评委在五秒内应能回答：

1. 谁在投诉什么；
2. 系统识别成了什么事件；
3. 大模型选择了什么治理策略；
4. OR-Tools 做了什么；
5. Verifier 是否通过；
6. 最终是否完成；
7. Full 模式和消融条件有什么区别。

---

## 十四、Frontend Experience Contract v2

v0.2 不应破坏现有 `FrontendFixture 1.0` 和车辆故障 Demo。

优先新增独立的 experience contract，或通过明确版本字段进行向后兼容扩展。

建议结构：

```json
{
  "schema_version": "2.0",
  "experience": {
    "experience_id": "...",
    "title": "...",
    "scenario_id": "...",
    "selected_case": true,
    "mode": "FULL_LLM_POLICY_REPLAN"
  },
  "provenance": {},
  "complaint_session": {},
  "city_event": {},
  "policy_decision": {},
  "execution_frames": [],
  "final_metrics": {},
  "final_summary": {},
  "ablation_comparison": []
}
```

具体字段必须由实际 Python 对象白名单投影产生。

不得为了前端方便复制并维护第二套互相冲突的 CityState、DispatchPlan 或 Metrics 真值。

现有车辆故障 Demo 应继续使用其当前稳定 contract，不要求为 v0.2 立即迁移。

---

## 十五、失败与降级

### 1. Complaint Intake 失败

返回：

```text
NEEDS_CLARIFICATION
```

或：

```text
REJECTED
```

不得构造虚假 CityEvent。

### 2. DeepSeek 调用失败

必须记录明确的错误类型，例如：

```text
PROVIDER_ERROR
CONTRACT_ERROR
VALIDATION_ERROR
```

生成轨迹时不得静默替换为一个看似真实的 DeepSeek 决策。

比赛稳定回放应继续使用已经验证的冻结轨迹。

### 3. Optimizer INFEASIBLE

显示真实 `INFEASIBLE` 和原因，停止继续执行非法计划。

### 4. Verifier FAIL

不得安装计划，不得让 CitySim 假装执行成功。

### 5. Final Summary 失败

使用确定性模板总结现有事实，不影响闭环结果。

---

## 十六、安全与隐私

投诉演示默认使用：

- 用户主动编写的合成投诉；或
- 已获得许可且完成脱敏的文本。

禁止在 fixture、日志、截图或仓库中保存：

- 真实姓名；
- 手机号；
- 精确家庭住址；
- 身份证信息；
- API Key；
- Provider Token；
- Authorization Header；
- 其他可识别个人身份的信息。

前端不得读取 `.env`。

API Key 只能由 Python 端显式 opt-in 脚本从环境变量读取。

生成轨迹前应执行脱敏和敏感字段白名单检查。

---

## 十七、测试要求

### 1. Complaint Intake

至少测试：

- 支持场景能够生成 READY；
- 缺少位置时进入 NEEDS_CLARIFICATION；
- 未知实体不能进入 CityEvent；
- 不支持事件能够被拒绝；
- 消息来源标识正确；
- 多次运行冻结输入保持确定性结果。

### 2. DeepSeek 轨迹

至少测试：

- provenance 必填字段；
- 不含凭据；
- event 与 decision 合同一致；
- 未知 priority target 被拒绝；
- Provider failure 被显式记录；
- 默认测试不访问网络。

### 3. Final Summary

至少测试：

- 只能引用白名单事实；
- 不能把 FAIL 改写为 PASS；
- 不能把 INFEASIBLE 改写为成功；
- 不能增加不存在的车辆、任务和指标；
- 模型失败时使用确定性模板。

### 4. 消融公平性

至少测试：

- 三种模式初始状态等价且对象独立；
- 事件字段一致；
- TaskBuilder 变化一致；
- 相同随机种子；
- Static 模式不调用重规划；
- Fixed 模式固定为 BALANCED；
- Full 模式使用真实 provenance 对应的 PolicyDecision；
- 结果可重复生成。

### 5. 前端

至少验证：

- `npm run build` 成功；
- 1920×1080 六个或实际定义的关键阶段截图；
- 模式切换无状态残留；
- Full、Fixed、Static 标签和结果不串联；
- 真实轨迹 provenance 可见；
- 任务完成率按百分比展示；
- Console、pageerror 和业务 failed requests 为 0；
- 默认稳定回放不依赖网络；
- 浏览器不接触 API Key。

Playwright 默认使用 Microsoft Edge 和有意义的命名 Session。

---

## 十八、实现顺序

### Phase 1：规格与案例冻结

1. 确认 `urgent_timing_tradeoff_live` 为主演示；
2. 确认投诉文本和允许的实体别名；
3. 确认展示消息中哪些来自用户、模型和编辑说明；
4. 冻结同场景三种消融输入；
5. 记录实验和数据版本。

### Phase 2：数据契约与轨迹生成

1. 实现 ComplaintSession 和 TraceProvenance；
2. 实现确定性实体解析；
3. 实现真实 API 轨迹生成脚本；
4. 实现 Frontend Experience Contract v2；
5. 生成并验证只读 fixture。

### Phase 3：最终总结

1. 定义 `FinalNarrativeSummary`；
2. 实现白名单输入；
3. 实现结构校验和 fact refs；
4. 实现确定性降级模板；
5. 冻结主演示真实总结。

### Phase 4：前端投诉闭环

1. 增加投诉对话区；
2. 增加结构化事件确认；
3. 增加 Agent 工作流状态；
4. 复用逻辑拓扑、Optimizer、Verifier 和 Metrics 展示；
5. 增加最终回复；
6. 保持现有车辆故障 Demo 可用。

### Phase 5：消融入口

1. 增加 Full、Fixed、Static 选择；
2. 展示相同输入与不同结果；
3. 同时展示收益和成本；
4. 增加精选案例和全量评测声明。

### Phase 6：比赛级 QA

1. 构建验证；
2. 端到端交互验证；
3. 1920×1080 截图；
4. Console / Network 检查；
5. 数据真实性审计；
6. 脱敏检查；
7. 离线环境稳定回放。

每个 Phase 单独实现和验证。不要一次性重写现有后端和前端。

---

## 十九、v0.2 完成标准

v0.2 完成时必须满足：

1. 至少一个用户主动编写的投诉场景形成完整冻结轨迹；
2. 模型消息确实来自真实 API，或被明确标记为模板；
3. 投诉能够形成经过确定性解析的 `CityEvent`；
4. DeepSeek 输出经过现有 `PolicyDecision` 合同验证；
5. LLM 未直接生成路线、距离、容量或优化权重；
6. OR-Tools、Verifier 和 CitySim 继续作为确定性事实来源；
7. 最终总结只能引用已验证事实，并有确定性降级；
8. 比赛默认使用离线冻结轨迹，不依赖 Provider 可用性；
9. Full、Fixed、Static 使用相同输入并可公平比较；
10. 现有 Mock `EVENT_POLICY_REPLAN` 未被冒充为 DeepSeek；
11. 精选案例有明确声明，并保留全量评测摘要；
12. 现有车辆故障 Demo 行为不被破坏；
13. 默认 pytest 不访问网络；
14. 前端构建和 1920×1080 E2E 通过；
15. fixture、日志和截图不含凭据或个人敏感信息；
16. 项目仍可在普通 CPU 环境运行。

如果任何真实 API 调用失败，v0.2 仍必须能够通过冻结轨迹完成比赛主演示。

---

## 二十、开发原则

v0.2 的开发必须遵循：

- 先规格和契约，后前端；
- 先单场景闭环，后扩展案例；
- 先冻结真实证据，后设计视觉；
- 不伪造模型对话；
- 不隐藏不利指标；
- 不把精选案例描述为全量表现；
- 不让 LLM 侵入 Optimizer、Verifier 和 CitySim 的确定性职责；
- 不为了现场炫技让主演示依赖网络；
- 不引入当前目标不需要的框架和基础设施；
- 每个 bug 修复增加回归测试；
- 所有新增网络测试显式 opt-in；
- 所有新设计优先考虑可测试性、可解释性和后续论文实验复用。

发现规格与现有代码或冻结实验结果冲突时，必须先报告冲突，不得静默修改实验含义。
