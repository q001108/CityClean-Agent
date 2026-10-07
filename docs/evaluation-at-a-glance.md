# CityClean 一页评测结果与失败边界

本页用于校招展示，不是生产效果承诺。所有城市运行状态与任务均为合成数据；除注明的冻结真实模型调用外，结果由确定性离线仿真得到。

## 1. 固定场景：重规划是否有用

在当前代码上运行 `python -m cityclean_agent.benchmark`，得到 9 个固定场景 × 3 种条件，共 27 次执行。下表的任务完成率是**各场景完成率的算术平均**，不是跨场景任务数加权平均。

| 条件 | 治理策略来源 | 平均任务完成率 | 全部任务完成的场景 |
|---|---|---:|---:|
| 静态，不重规划 | 不选择新策略 | 59.8% | 2/9 |
| 固定均衡策略重规划 | 固定 `BALANCED` | 75.9% | 6/9 |
| 事件策略重规划 | 确定性 `MockEventAgent` | 79.6% | 7/9 |

这说明在**这组固定场景**中，重规划比静态执行完成更多任务。第三行不是 DeepSeek 结果，不能据此声称“大模型提升 19.8 个百分点”。实现见 [BenchmarkRunner](../src/cityclean_agent/benchmark/runner.py)；运行会将逐场景结果写入默认忽略的 `artifacts/evaluations/benchmark_comparison_results.json`。

## 2. 真实模型冻结轨迹：收益伴随距离代价

[v0.2 冻结轨迹](../knowledge_base/traces/v02_urgent_timing_trace.json)记录了 2026-08-26 显式调用 `deepseek-v4-flash` 的 provenance；[离线回放 fixture](../knowledge_base/demo/fixtures/complaint_urgent_v2.json)在相同初始状态、事件和时间约束下比较三种执行条件。这里只是**一个合成紧急清运案例**，不能外推为总体优势。

| 条件 | 任务完成率 | 紧急任务完成率 | 已完成任务平均响应时间 | 总行驶距离 |
|---|---:|---:|---:|---:|
| 真实 DeepSeek 策略 + 重规划 | 100% | 100% | 11.67 分钟 | 51 |
| 固定均衡策略 + 重规划 | 100% | 100% | 13.33 分钟 | 2 |
| 静态，不重规划 | 66.67% | 0% | 12.50 分钟 | 1 |

真实策略在该案例中缩短了已完成任务的平均响应时间，但总行驶距离远高于固定均衡策略；静态方案距离短，也有任务未完成，不能把短距离单独解读为更优。距离数值沿用仿真指标的原始单位，不冒充真实城市公里数。

## 3. 治理研判：契约成功不等于判断正确

[冻结 Gold 错误分析](../knowledge_base/reports/governance_error_analysis_v0.1.md)覆盖 40 个审核案例，其中 38 次成功调用、2 次 provider error，结构化契约成功率为 **95%**。在 38 个成功案例中：策略分类准确率 **60.53%**、宏平均 F1 **0.5216**；响应时限落在 Gold 可接受范围内的比例仅 **31.58%**。在 16 组 Gold 要求策略变化的成对语境中，仅 **5 组**两端策略均判断正确。

典型失败：`rc02-blocks-two-routes` 的 Gold 策略为 `URGENT_RESPONSE`、风险 4，模型输出 `BALANCED`、风险 2。项目因此展示结构化输入、外部决策结果与错误分析，不把隐藏思维链当作可验证证据。Verifier 检查的是**调度方案硬约束**，不证明治理策略合理。

## 复现与适用边界

```powershell
conda activate langchain1.2
python -m cityclean_agent.benchmark
python -m pytest -q
```

默认命令不调用 DeepSeek。Gold 统计来自已冻结的历史评测报告；重新采集真实模型结果必须显式提供凭据并承担 API 费用。[Verifier 对抗测试](../tests/verifier/test_adversarial_evaluation.py)覆盖已设计的约束案例，但不能证明所有现实道路、容量和时间窗情况都已覆盖。系统未接入真实运营数据，也没有生产认证、持久化服务或 SLA。
