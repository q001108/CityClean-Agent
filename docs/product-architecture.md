# CityClean Agent 产品化架构路线

## 目标与边界

产品入口不加载比赛 fixture、冻结轨迹或消融实验结果。历史比赛页面只保留在独立的 `/demo` 动态入口，不能作为 Agent 运行事实来源。

长期事实边界保持不变：

- LLM / Agent 负责非结构化理解、策略研判和工具选择。
- CityState 的实时来源必须显式定义；当前仍由 CitySim 提供，未来可由经过验证的外部状态适配器替换。
- 路线、容量、距离和 ETA 等确定性结果由 Optimizer 计算。
- Verifier 独立检查硬约束；未经验证的方案不得进入执行层。
- 天地图是显示层，不是调度真值或道路导航计算器。

## 当前技术基线

本机 `langchain1.2` Conda 环境已核实：

- LangChain 1.2.12
- LangChain Core 1.2.18
- LangChain DeepSeek 1.0.1
- LangGraph 1.1.2
- LangChain MCP Adapters 0.2.1

项目当前只直接声明 `langchain-deepseek`，尚未把 LangGraph 或 MCP 作为产品运行依赖。只有相应产品切片开始实现时才更新依赖，不提前堆叠框架。

## 目标运行链

```text
Input Adapter
  → deterministic intake / entity resolution
  → optional policy knowledge retrieval
  → EventDecisionAgent
  → TaskBuilder
  → OR-Tools Optimizer
  → independent Verifier
  → optional human approval interrupt
  → CitySim or external execution adapter
  → observable runtime snapshot
```

LangGraph 只负责编排、状态、检查点、流式事件和人工中断；不得把现有确定性算法重写成 LLM 工具。

## 分阶段推进

### Phase 1：产品入口与稳定边界

- 默认前端入口改为产品工作台。
- 历史比赛页面移动到 `/demo`，通过动态 import 隔离。
- 产品地图只显示真实底图；收到 Runtime CitySnapshot 前不绘制实体。
- 用 `EventDecisionAgent` Protocol 统一 Mock、DeepSeek 和后续 LangChain/LangGraph 节点的接口。

### Phase 2：Runtime API

- 已定义版本化的 `CityEventRequest`、`CitySnapshotResponse` 和 `WorkflowRunResponse` 契约。
- 已提供单进程 FastAPI，连接现有 `process_event`，不复制第二套 CityState。
- 已提供健康状态、Runtime 状态、城市快照和结构化事件四个端点。
- 前端已通过 API 展示真实运行状态并提交结构化事件，不在浏览器生成业务结果。
- Runtime 快照可携带道路节点经纬度，并据此生成车辆、收运点和调度路径；前端不得自行编造业务坐标。
- Runtime 状态显式区分 `test` 与 `production` 数据源，防止本地测试数据被误认为生产事实。
- 默认应用不注入比赛 fixture；未配置权威状态源时，状态明确为 `unavailable`，快照和事件端点返回 503。
- `CityRuntime` 必须显式注入 `EventDecisionAgent`，避免产品路径隐式回退到 Mock Agent。

本地启动 API 外壳：

```powershell
conda run -n langchain1.2 python -m uvicorn cityclean_agent.api.app:app --host 127.0.0.1 --port 8000
```

该命令只启动未配置状态源的安全默认应用。接入可用 Runtime 时，应由应用装配层向 `create_app` 注入 `CityRuntime(CitySim(...), event_agent=...)`；真实状态源和真实 Agent 尚未配置时，不应为了让页面显示“可用”而加载比赛数据或 Mock Agent。

### Phase 3：LangGraph 编排

- 用 StateGraph 编排事件接入、研判、调度、验证和结果发布。
- 使用 checkpointer 和 `thread_id` 持久化单次事件处理。
- 对会产生外部副作用的工具或执行动作设置 interrupt / 人工批准。
- 保持 Optimizer、Verifier、CitySim 为普通确定性节点。

### Phase 4：工具调用

- 优先将仓库内稳定、确定性的只读查询封装为 LangChain `@tool`。
- 工具必须声明输入输出、超时、错误和副作用级别。
- 写操作使用显式授权、幂等键和审计记录，不能由模型直接操作内部对象。

### Phase 5：RAG

- 仅索引法规、应急预案、作业规范和已批准知识。
- 检索结果必须带来源，作为研判上下文而非城市实时事实。
- 小规模文档先使用简单检索器；证明确有必要后再引入向量数据库。

### Phase 6：MCP

- 仅对确需独立进程或跨系统复用的工具使用 MCP。
- 从白名单、只读 MCP 服务开始，并为工具名加服务前缀。
- Web 服务场景优先 HTTP transport；本地 stdio 仅用于受控开发环境。
- 凭据由服务端运行环境提供，不进入模型消息、前端或仓库。

## 官方依据

- LangChain v1 推荐使用 `create_agent` 统一模型、工具、中间件和结构化输出。
- LangGraph 官方定位是混合确定性步骤与 LLM 步骤的低层编排层，提供持久化、流式执行和 human-in-the-loop。
- LangChain MCP Adapters 提供 `MultiServerMCPClient`；其官方示例明确提醒在 Web 服务中先判断普通工具是否已经足够，再选择 stdio MCP。

参考：

- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/langgraph/overview
- https://github.com/langchain-ai/langchain-mcp-adapters
