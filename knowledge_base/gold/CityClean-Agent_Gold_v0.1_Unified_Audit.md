# CityClean-Agent Governance Gold Set v0.1 — 统一规则审查

## 审查结论

- 总案例：40；统一审查通过 40/40。
- 保留不改：29 条。
- 建议修订：11 条（其中 11 条补强治理目标；`ut04-food-safety` 同时将 Risk 5 调整为 Risk 4）。
- PolicyProfile：本轮不修改任何 case。
- Deadline：本轮不修改；全部非空区间均为绝对模拟分钟、起点不早于 `current_time`，reference 均落在区间内。
- Priority targets：本轮不修改；Overflow/Urgent 指向既有 WastePoint，Breakdown/Road Closure 保持空列表。
- Paired-context 结构：20/20 pair 均保持结构化 event/state 一致，仅 description 及对应 Gold 治理标签可变化。

## 统一审查规则

1. **治理链完整性**：中高风险案例应能从 description 看出“事实 → 风险后果 → 需要保护的治理目标”，避免只靠医院/学校/体育场等敏感词触发高标签。
2. **防标签泄漏**：description 可以表达治理目标，但不直接写 `URGENT_RESPONSE`、Risk 数字、Gold deadline 或优化器权重。
3. **Risk 5 收紧**：仅保留给医院/脆弱人群/关键通道/明显严重健康安全或极强服务连续性压力；一般较高食品卫生风险归 Risk 4。
4. **Profile 与事件类型解耦**：同一 EventType 可因语境进入不同 Profile；不强制 `URGENT_TASK → URGENT_RESPONSE`、`ROAD_CLOSURE → MINIMAL_RESCHEDULE`。
5. **Deadline 非伪精确**：正式判断使用区间命中；reference 只辅助 MAE。该字段仍是治理意图，不等于 `ServiceTask.deadline` 硬约束。
6. **低风险案例不过度补写目标**：对 `BALANCED` / Risk 1–2 且“影响很低/替代资源充足”已经明确的案例，不机械添加治理口号。

## 本轮修订项

| Case | 修订 | 最终 Profile | 最终 Risk | 最终 Description |
|---|---|---|---:|---|
| wo01-hospital-entrance | 补强治理目标 | URGENT_RESPONSE | 5 | 同一垃圾点位于医院主要出入口附近，垃圾已经外溢并出现异味，患者和陪护人员持续经过，需要避免满溢继续影响入口通行与院区卫生环境。 |
| wo02-school-dismissal | 补强治理目标 | URGENT_RESPONSE | 4 | 学校放学高峰期间垃圾点达到容量上限，学生和家长大量聚集，并有家长投诉异味，需要避免垃圾积存影响校门通行和放学环境。 |
| wo05-festival-crowd | 补强治理目标 | URGENT_RESPONSE | 4 | 同一商业街正在举办节庆活动，垃圾点满溢且人流密集，现场保洁压力快速上升，需要避免积存垃圾持续影响活动区域通行与环境卫生。 |
| ut03-school-dismissal | 补强治理目标 | URGENT_RESPONSE | 4 | 学校放学时段临时产生大量包装垃圾，校门口学生与家长密集，保洁人员请求清运，以避免垃圾积存影响校门通行和放学秩序。 |
| ut04-food-safety | 补强治理目标；Risk 5→4 | URGENT_RESPONSE | 4 | 生鲜市场临时产生大量湿垃圾，靠近食品加工区并出现明显异味，管理方要求清运，以降低湿垃圾滞留对食品加工环境和市场卫生造成的影响。 |
| ut05-stadium-after-event | 补强治理目标 | URGENT_RESPONSE | 4 | 体育场大型赛事刚散场，出口周边临时垃圾快速增加，观众仍在持续离场，需要避免垃圾积存影响人员疏散、出口通行和现场环境。 |
| vb01-hospital-route | 补强治理目标 | URGENT_RESPONSE | 4 | 故障车辆的后续路线中包含医院周边高优先任务，虽然有备用车辆，但剩余处理窗口很紧，需要保障医院周边高优环卫服务按时恢复。 |
| vb04-sensitive-unfinished | 补强治理目标 | URGENT_RESPONSE | 5 | 故障车辆尚有一项与重点医疗场所相关的高优任务未完成，当前时效窗口很短，需要避免车辆故障造成该敏感区域环卫服务中断。 |
| rc01-event-arterial | 补强治理目标 | URGENT_RESPONSE | 4 | 大型活动散场期间主干道路段突然封闭，多条现有清运路线受阻，周边任务正在快速积压，需要保障散场区域清运服务连续性并避免积压扩大。 |
| rc03-hospital-access | 补强治理目标 | URGENT_RESPONSE | 5 | 封闭路段位于医院周边关键通道，当前有高优清运任务需要经过附近区域，安全管制可能持续，需要保障医院周边高优环卫服务不中断。 |
| rc04-school-dismissal | 补强治理目标 | URGENT_RESPONSE | 4 | 学校放学期间周边道路突然封闭，清运车辆与家长车辆混行，已有任务受到影响，需要避免清运调整进一步干扰放学通行与周边秩序。 |

## 40 条逐案审查表

| Case | Status | Profile | Risk | Deadline Range | 审查说明 |
|---|---|---|---:|---|---|
| wo01-routine-residential | KEEP | OVERFLOW_CONTROL | 3 | 45–55 | 标签、风险、时效与描述一致；无需修改。 |
| wo01-hospital-entrance | REVISE | URGENT_RESPONSE | 5 | 25–35 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| wo02-school-weekend | KEEP | OVERFLOW_CONTROL | 2 | 50–70 | 标签、风险、时效与描述一致；无需修改。 |
| wo02-school-dismissal | REVISE | URGENT_RESPONSE | 4 | 35–45 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| wo03-industrial-night | KEEP | OVERFLOW_CONTROL | 2 | 50–65 | 标签、风险、时效与描述一致；无需修改。 |
| wo03-food-market | KEEP | URGENT_RESPONSE | 4 | 25–35 | 标签、风险、时效与描述一致；无需修改。 |
| wo04-residential-single | KEEP | OVERFLOW_CONTROL | 3 | 40–55 | 标签、风险、时效与描述一致；无需修改。 |
| wo04-eldercare-gate | KEEP | URGENT_RESPONSE | 5 | 15–25 | 标签、风险、时效与描述一致；无需修改。 |
| wo05-commercial-spare | KEEP | OVERFLOW_CONTROL | 3 | 55–70 | 标签、风险、时效与描述一致；无需修改。 |
| wo05-festival-crowd | REVISE | URGENT_RESPONSE | 4 | 40–50 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| ut01-planned-community | KEEP | BALANCED | 2 | 50–70 | 标签、风险、时效与描述一致；无需修改。 |
| ut01-crowd-exit | KEEP | URGENT_RESPONSE | 4 | 30–40 | 标签、风险、时效与描述一致；无需修改。 |
| ut02-missed-pickup | KEEP | URGENT_RESPONSE | 3 | 45–60 | 标签、风险、时效与描述一致；无需修改。 |
| ut02-hospital-entry | KEEP | URGENT_RESPONSE | 5 | 30–40 | 标签、风险、时效与描述一致；无需修改。 |
| ut03-school-prep | KEEP | BALANCED | 2 | 65–85 | 标签、风险、时效与描述一致；无需修改。 |
| ut03-school-dismissal | REVISE | URGENT_RESPONSE | 4 | 40–50 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| ut04-market-backroom | KEEP | URGENT_RESPONSE | 3 | 50–65 | 标签、风险、时效与描述一致；无需修改。 |
| ut04-food-safety | REVISE | URGENT_RESPONSE | 4 | 25–35 | 补足食品加工环境治理目标；原 Risk 5 与“较高卫生风险”不完全匹配，收紧为 Risk 4。 |
| ut05-night-additional | KEEP | BALANCED | 2 | 60–80 | 标签、风险、时效与描述一致；无需修改。 |
| ut05-stadium-after-event | REVISE | URGENT_RESPONSE | 4 | 45–55 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| vb01-backup-idle | KEEP | MINIMAL_RESCHEDULE | 2 | 50–70 | 标签、风险、时效与描述一致；无需修改。 |
| vb01-hospital-route | REVISE | URGENT_RESPONSE | 4 | 30–40 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| vb02-after-shift | KEEP | BALANCED | 1 | — | 标签、风险、时效与描述一致；无需修改。 |
| vb02-peak-backlog | KEEP | URGENT_RESPONSE | 4 | 55–65 | 标签、风险、时效与描述一致；无需修改。 |
| vb03-two-backups | KEEP | MINIMAL_RESCHEDULE | 2 | 40–55 | 标签、风险、时效与描述一致；无需修改。 |
| vb03-capacity-tight | KEEP | URGENT_RESPONSE | 4 | 25–35 | 标签、风险、时效与描述一致；无需修改。 |
| vb04-near-route-end | KEEP | MINIMAL_RESCHEDULE | 2 | 60–80 | 标签、风险、时效与描述一致；无需修改。 |
| vb04-sensitive-unfinished | REVISE | URGENT_RESPONSE | 5 | 45–55 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| vb05-no-active-assignment | KEEP | BALANCED | 1 | — | 标签、风险、时效与描述一致；无需修改。 |
| vb05-multiple-ordinary-assigned | KEEP | MINIMAL_RESCHEDULE | 3 | 45–60 | 标签、风险、时效与描述一致；无需修改。 |
| rc01-local-alternative | KEEP | MINIMAL_RESCHEDULE | 2 | 50–70 | 标签、风险、时效与描述一致；无需修改。 |
| rc01-event-arterial | REVISE | URGENT_RESPONSE | 4 | 30–40 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| rc02-not-on-route | KEEP | BALANCED | 1 | — | 标签、风险、时效与描述一致；无需修改。 |
| rc02-blocks-two-routes | KEEP | URGENT_RESPONSE | 4 | 40–50 | 标签、风险、时效与描述一致；无需修改。 |
| rc03-short-planned | KEEP | MINIMAL_RESCHEDULE | 2 | 60–80 | 标签、风险、时效与描述一致；无需修改。 |
| rc03-hospital-access | REVISE | URGENT_RESPONSE | 5 | 45–55 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| rc04-industrial-alternative | KEEP | MINIMAL_RESCHEDULE | 2 | 50–65 | 标签、风险、时效与描述一致；无需修改。 |
| rc04-school-dismissal | REVISE | URGENT_RESPONSE | 4 | 30–40 | Gold 本身合理；补足风险后果/治理目标，降低敏感地点关键词 shortcut。 |
| rc05-peripheral-unused | KEEP | BALANCED | 1 | — | 标签、风险、时效与描述一致；无需修改。 |
| rc05-single-critical-corridor | KEEP | MINIMAL_RESCHEDULE | 3 | 35–50 | 标签、风险、时效与描述一致；无需修改。 |

## 修订后分布

- PolicyProfile：{'OVERFLOW_CONTROL': 5, 'URGENT_RESPONSE': 20, 'BALANCED': 7, 'MINIMAL_RESCHEDULE': 8}
- Risk：{1: 4, 2: 11, 3: 7, 4: 13, 5: 5}

## 冻结建议

当前文件仍标记为 audited draft。项目负责人审阅本轮 11 条修订后，如无异议，可将其冻结为正式 `Governance Gold Set v0.1`，之后不要依据 DeepSeek 预测结果反向改 Gold；Prompt 调优应另建 dev set。
