# Governance Error Analysis Report v0.1

## 1. Evaluation Overview

- Gold cases：40
- 模型：deepseek-v4-flash
- 成功调用：38
- Contract success rate：95.00%

本报告仅解释冻结评测结果；不包含 Prompt 调整、标签修改或系统修复建议。

## 2. Policy Classification Error Analysis

- Accuracy：60.53%
- Macro-F1：0.5216

### Confusion Matrix

行=Gold，列=Predicted。

| Gold \ Pred | BALANCED | URGENT_RESPONSE | OVERFLOW_CONTROL | MINIMAL_RESCHEDULE |
|---|---|---|---|---|
| BALANCED | 0 | 1 | 0 | 6 |
| URGENT_RESPONSE | 2 | 14 | 1 | 1 |
| OVERFLOW_CONTROL | 2 | 0 | 3 | 0 |
| MINIMAL_RESCHEDULE | 2 | 0 | 0 | 6 |

## 3. Policy Error Taxonomy

| 分类 | 数量 |
|---|---:|
| A. Risk escalation bias | 1 |
| B. Conservative delay handling | 2 |
| C. Overflow / urgent confusion | 1 |
| D. Context under-utilization | 11 |

| Case | Event | Gold | Predicted | Risk Gold/Pred | 归因 | 简短解释 |
|---|---|---|---|---|---|---|
| wo03-food-market | WASTE_OVERFLOW | URGENT_RESPONSE | OVERFLOW_CONTROL | 4/3 | C. Overflow / urgent confusion | 在满溢治理与紧急响应之间发生治理语义混淆。 |
| wo04-residential-single | WASTE_OVERFLOW | OVERFLOW_CONTROL | BALANCED | 3/3 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| wo05-commercial-spare | WASTE_OVERFLOW | OVERFLOW_CONTROL | BALANCED | 3/3 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| ut01-planned-community | URGENT_TASK | BALANCED | URGENT_RESPONSE | 2/2 | A. Risk escalation bias | 将均衡治理升级为紧急响应，体现治理等级上调。 |
| ut03-school-prep | URGENT_TASK | BALANCED | MINIMAL_RESCHEDULE | 2/2 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| ut05-night-additional | URGENT_TASK | BALANCED | MINIMAL_RESCHEDULE | 2/2 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| vb02-after-shift | VEHICLE_BREAKDOWN | BALANCED | MINIMAL_RESCHEDULE | 1/1 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| vb03-two-backups | VEHICLE_BREAKDOWN | MINIMAL_RESCHEDULE | BALANCED | 2/2 | B. Conservative delay handling | 未体现需要恢复既有调度的最小扰动重调度。 |
| vb03-capacity-tight | VEHICLE_BREAKDOWN | URGENT_RESPONSE | BALANCED | 4/2 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| vb05-no-active-assignment | VEHICLE_BREAKDOWN | BALANCED | MINIMAL_RESCHEDULE | 1/1 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| rc02-not-on-route | ROAD_CLOSURE | BALANCED | MINIMAL_RESCHEDULE | 1/1 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| rc02-blocks-two-routes | ROAD_CLOSURE | URGENT_RESPONSE | BALANCED | 4/2 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| rc04-industrial-alternative | ROAD_CLOSURE | MINIMAL_RESCHEDULE | BALANCED | 2/2 | B. Conservative delay handling | 未体现需要恢复既有调度的最小扰动重调度。 |
| rc04-school-dismissal | ROAD_CLOSURE | URGENT_RESPONSE | MINIMAL_RESCHEDULE | 4/3 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |
| rc05-peripheral-unused | ROAD_CLOSURE | BALANCED | MINIMAL_RESCHEDULE | 1/1 | D. Context under-utilization | 未充分体现描述变化对 Gold 治理策略的影响。 |

## 4. Risk Error Analysis

- Exact Accuracy：60.53%
- MAE：0.5789
- ±1 Accuracy：81.58%
- Under-estimation：15，按事件类型：ROAD_CLOSURE=5，URGENT_TASK=4，VEHICLE_BREAKDOWN=4，WASTE_OVERFLOW=2
- Over-estimation：0，按事件类型：无

风险偏差最大的案例（绝对偏差 ≥2）：

| Case | Event | Gold | Predicted | Absolute Error |
|---|---|---:|---:|---:|
| rc01-event-arterial | ROAD_CLOSURE | 4 | 2 | 2 |
| rc02-blocks-two-routes | ROAD_CLOSURE | 4 | 2 | 2 |
| rc03-hospital-access | ROAD_CLOSURE | 5 | 3 | 2 |
| ut02-hospital-entry | URGENT_TASK | 5 | 3 | 2 |
| ut03-school-dismissal | URGENT_TASK | 4 | 2 | 2 |
| vb03-capacity-tight | VEHICLE_BREAKDOWN | 4 | 2 | 2 |
| vb05-multiple-ordinary-assigned | VEHICLE_BREAKDOWN | 3 | 1 | 2 |

## 5. Deadline Error Analysis

治理响应时限是治理意图指标，不等价于 OR-Tools 调度硬约束。

- Acceptable Accuracy：31.58%
- Reference MAE：20.3704
- Too aggressive：13
- Too relaxed：6
- Missing deadline：7
- Unexpected deadline：0

| Case | Event | Gold Range | Predicted | 分类 |
|---|---|---|---|---|
| wo03-industrial-night | WASTE_OVERFLOW | [50, 65] | 无 | Missing deadline |
| wo03-food-market | WASTE_OVERFLOW | [25, 35] | 15 | Too aggressive |
| wo04-eldercare-gate | WASTE_OVERFLOW | [15, 25] | 80 | Too relaxed |
| wo05-commercial-spare | WASTE_OVERFLOW | [55, 70] | 45 | Too aggressive |
| ut01-planned-community | URGENT_TASK | [50, 70] | 无 | Missing deadline |
| ut01-crowd-exit | URGENT_TASK | [30, 40] | 20 | Too aggressive |
| ut02-missed-pickup | URGENT_TASK | [45, 60] | 115 | Too relaxed |
| ut02-hospital-entry | URGENT_TASK | [30, 40] | 25 | Too aggressive |
| ut03-school-prep | URGENT_TASK | [65, 85] | 无 | Missing deadline |
| ut04-market-backroom | URGENT_TASK | [50, 65] | 110 | Too relaxed |
| ut04-food-safety | URGENT_TASK | [25, 35] | 50 | Too relaxed |
| ut05-night-additional | URGENT_TASK | [60, 80] | 无 | Missing deadline |
| vb01-backup-idle | VEHICLE_BREAKDOWN | [50, 70] | 20 | Too aggressive |
| vb01-hospital-route | VEHICLE_BREAKDOWN | [30, 40] | 20 | Too aggressive |
| vb02-peak-backlog | VEHICLE_BREAKDOWN | [55, 65] | 50 | Too aggressive |
| vb03-two-backups | VEHICLE_BREAKDOWN | [40, 55] | 无 | Missing deadline |
| vb03-capacity-tight | VEHICLE_BREAKDOWN | [25, 35] | 无 | Missing deadline |
| vb04-near-route-end | VEHICLE_BREAKDOWN | [60, 80] | 130 | Too relaxed |
| vb05-multiple-ordinary-assigned | VEHICLE_BREAKDOWN | [45, 60] | 20 | Too aggressive |
| rc01-local-alternative | ROAD_CLOSURE | [50, 70] | 80 | Too relaxed |
| rc01-event-arterial | ROAD_CLOSURE | [30, 40] | 25 | Too aggressive |
| rc02-blocks-two-routes | ROAD_CLOSURE | [40, 50] | 30 | Too aggressive |
| rc03-short-planned | ROAD_CLOSURE | [60, 80] | 50 | Too aggressive |
| rc03-hospital-access | ROAD_CLOSURE | [45, 55] | 40 | Too aggressive |
| rc04-industrial-alternative | ROAD_CLOSURE | [50, 65] | 20 | Too aggressive |
| rc05-single-critical-corridor | ROAD_CLOSURE | [35, 50] | 无 | Missing deadline |

## 6. Priority Target Analysis

- Precision：75.00%
- Recall：100.00%
- F1：0.8571
- Exact Set Accuracy：84.21%
- False positives：W21=2，W24=2，W33=2
- False negatives：无

## 7. Paired Context Analysis

- Total pairs：20
- Both-success pairs：18
- Gold profile changed pairs：16
- Predicted profile changed pairs：11
- Correct context adaptation：5
- Paired profile accuracy：31.25%

描述变化在 16 个可评 pair 中要求策略变化，但仅 5 个 pair 同时匹配两端 Gold profile，表明当前模型对上下文造成的治理策略切换利用不足。

## 8. Root Cause Classification

| 问题 | 数量 | 归因 |
|---|---:|---|
| Policy 误分类 | 15 | B. 模型治理偏好 |
| Risk 偏差 | 15 | D. 数值预测困难 |
| Deadline 误差 | 26 | D. 数值预测困难 |
| Priority Target 误差 | 6 | A. 输入信息不足 |
| Context 理解不足 | 11 | B. 模型治理偏好 |
| Provider failure | 2 | E. Provider 稳定性 |

合同失败案例：

- `wo01-hospital-entrance`：provider_error
- `wo05-festival-crowd`：provider_error

## 分析边界

本报告是对一次冻结 Gold 评测的测量性归因，不构成模型推理过程，也不提出自动修复。
