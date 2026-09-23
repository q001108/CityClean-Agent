# CityClean-Agent Governance Gold Set v0.1

## 1. 定位
本数据集是 CityClean-Agent 自建的**合成治理决策评测集**，只用于测试，不用于训练。
共 40 条案例、20 个 paired groups。每个 pair 内结构化事件字段与 `state_context`
保持一致，仅改变自然语言 `description`，用于评估模型是否真正利用治理语境。

Gold 冻结后不得根据 DeepSeek 预测结果反向修改。若未来调 Prompt，应另建 dev set。

## 2. Gold 评价范围
只评价治理语义层：
- `policy_profile`
- `risk_level`
- `response_deadline`
- `priority_targets`

不评价路线、车辆分配、容量、最短路、ETA 或 OR-Tools 数学结果。

## 3. PolicyProfile 标注规范
| Profile | 规则 |
|---|---|
| `URGENT_RESPONSE` | 医院/学校等敏感区域、大型活动高人流、明显公共卫生/安全风险、关键服务中断或严格时效窗口；主要目标是快速响应。 |
| `OVERFLOW_CONTROL` | 垃圾满溢/积压本身是主要治理矛盾，需要提高服务优先级，但尚未升级为更高等级敏感场所紧急事件。 |
| `MINIMAL_RESCHEDULE` | 故障/封路需要调整，但备用资源或替代路径较充足；主要目标是恢复服务同时减少不必要改派。 |
| `BALANCED` | 没有明显单一治理目标占优，或事件对当前执行影响很低；在及时性、覆盖率和距离成本之间维持常规平衡。 |

冲突处理：若存在明确敏感场所/高人流/强时效风险，优先判 `URGENT_RESPONSE`；
否则满溢主导判 `OVERFLOW_CONTROL`，调度扰动主导判 `MINIMAL_RESCHEDULE`；
无明显单一目标则 `BALANCED`。

## 4. Risk Level
| Risk | 定义 |
|---:|---|
| 1 | 轻微：对当前运行几乎无实质影响。 |
| 2 | 局部：有限扰动，替代资源充足或暴露人群少。 |
| 3 | 明显：需要调度调整，已有一般投诉、积压或卫生影响。 |
| 4 | 较高：高人流、学校/活动场景、明显卫生风险、资源紧张或多任务受阻。 |
| 5 | 严重：医院/脆弱人群/关键通道，或强公共安全、健康、极严格时效压力。 |

每条同时给 `acceptable_risk_range`。推荐：MAE、Exact Accuracy、±1 Accuracy。

## 5. Response Deadline
`response_deadline_reference` / `response_deadline_range` 均为**绝对模拟分钟**。
正式指标以区间命中率为主，reference MAE 仅作辅助。
`None` 表示无需额外治理响应时限，可维持常规执行。
该字段是治理意图，不等价于 `ServiceTask.deadline` 的 OR-Tools 硬约束。

## 6. Priority Targets
只允许当前状态中存在的 WastePoint ID。
`WASTE_OVERFLOW` / `URGENT_TASK` 通常标受影响 WastePoint；
`VEHICLE_BREAKDOWN` / `ROAD_CLOSURE` 若无明确需要提升优先级的 WastePoint，则为空列表。
未来有真实多目标案例时再使用 Target Precision / Recall / F1。

## 7. 推荐指标
- PolicyProfile：Accuracy + Macro-F1
- Risk：MAE + Exact Accuracy + ±1 Accuracy
- Deadline：Acceptable-Range Accuracy；reference MAE 辅助
- Priority Targets：Precision / Recall / F1（有意义时）
- 工程合同：Contract Success Rate

## 8. 审阅与版本
当前全部 `review_status=approved`。
已由项目负责人审阅确认。若标签调整，应记录理由并提升数据集版本。
论文/答辩建议表述：**项目自建治理决策评测集，经项目组审阅确认**。

## 9. 数据统计
- Cases: 40
- Paired groups: 20
- Event types: 每类 10
- Policy distribution: {'OVERFLOW_CONTROL': 5, 'URGENT_RESPONSE': 20, 'BALANCED': 7, 'MINIMAL_RESCHEDULE': 8}
- Risk distribution: {1: 4, 2: 11, 3: 7, 4: 12, 5: 6}

## 10. 40 条 Gold 审阅表
| Case | Event | Description | Gold Profile | Risk | Deadline Range | Targets | Rationale |
|---|---|---|---|---:|---|---|---|
| wo01-routine-residential | WASTE_OVERFLOW | 普通居民区垃圾点刚达到容量上限，周边人流正常，暂未出现明显异味或集中投诉。 | OVERFLOW_CONTROL | 3 | 45–55 | W01 | 主要矛盾是满溢恢复，无高人流或敏感场所，应优先清运但无需升级为紧急响应。 |
| wo01-hospital-entrance | WASTE_OVERFLOW | 同一垃圾点位于医院主要出入口附近，垃圾已经外溢并出现异味，患者和陪护人员持续经过。 | URGENT_RESPONSE | 5 | 25–35 | W01 | 医院入口属于高敏感卫生场所，满溢已升级为明显健康与通行风险。 |
| wo02-school-weekend | WASTE_OVERFLOW | 学校周边垃圾点在周末达到容量上限，校园当前无集中活动，周边行人较少。 | OVERFLOW_CONTROL | 2 | 50–70 | W02 | 已满溢但处于低人流时段，可按常规满溢治理优先处理。 |
| wo02-school-dismissal | WASTE_OVERFLOW | 学校放学高峰期间垃圾点达到容量上限，学生和家长大量聚集，并有家长投诉异味。 | URGENT_RESPONSE | 4 | 35–45 | W02 | 放学高峰叠加未成年人高人流与投诉，治理时效应明显提前。 |
| wo03-industrial-night | WASTE_OVERFLOW | 工业园夜间垃圾点满溢，周边基本无行人，生产区有封闭围挡且备用车辆充足。 | OVERFLOW_CONTROL | 2 | 50–65 | W03 | 人群暴露低且资源充足，主要目标是恢复清运服务。 |
| wo03-food-market | WASTE_OVERFLOW | 同一满溢点紧邻正在营业的生鲜市场，湿垃圾气味明显，商户反映可能影响食品卫生。 | URGENT_RESPONSE | 4 | 25–35 | W03 | 生鲜市场卫生敏感，异味与湿垃圾使风险高于普通满溢。 |
| wo04-residential-single | WASTE_OVERFLOW | 居民区单个垃圾点刚刚满溢，附近其他点位仍有余量，暂无集中投诉。 | OVERFLOW_CONTROL | 3 | 40–55 | W04 | 典型单点满溢，需要优先清运但尚未出现更高等级公共卫生因素。 |
| wo04-eldercare-gate | WASTE_OVERFLOW | 同一垃圾点位于养老机构门口，满溢物散落到通行区域，老人出入受到影响。 | URGENT_RESPONSE | 5 | 15–25 | W04 | 养老机构属于脆弱人群敏感场所，散落垃圾已影响通行。 |
| wo05-commercial-spare | WASTE_OVERFLOW | 普通商业街垃圾点满溢，但当前客流平稳，附近有备用清运车辆可调。 | OVERFLOW_CONTROL | 3 | 55–70 | W05 | 有明确满溢治理需求，但客流和资源条件可控。 |
| wo05-festival-crowd | WASTE_OVERFLOW | 同一商业街正在举办节庆活动，垃圾点满溢且人流密集，现场保洁压力快速上升。 | URGENT_RESPONSE | 4 | 40–50 | W05 | 节庆高人流使普通满溢升级为时效敏感治理问题。 |
| ut01-planned-community | URGENT_TASK | 社区活动明天下午开始，工作人员提前申请一次临时清运，当前现场无拥堵和卫生暴露。 | BALANCED | 2 | 50–70 | W11 | 时效窗口宽且无即时风险，可在服务覆盖与行驶成本间保持平衡。 |
| ut01-crowd-exit | URGENT_TASK | 社区大型活动刚结束，出口处人流集中，临时垃圾快速堆积，需要尽快清运以避免影响疏散。 | URGENT_RESPONSE | 4 | 30–40 | W11 | 高人流疏散与快速积存形成明确时效压力。 |
| ut02-missed-pickup | URGENT_TASK | 居民反映该点位上一次清运遗漏，希望今天尽快补充清运，目前没有满溢或道路阻塞。 | URGENT_RESPONSE | 3 | 45–60 | W12 | 已进入临时优先任务且存在服务投诉，应加快处理但无重大公共风险。 |
| ut02-hospital-entry | URGENT_TASK | 医院急诊入口附近出现临时垃圾堆积，救护与患者通行频繁，院方要求立即处理。 | URGENT_RESPONSE | 5 | 30–40 | W12 | 急诊入口通行与卫生高度敏感，应以最高时效等级优先处置。 |
| ut03-school-prep | URGENT_TASK | 学校为次日运动会提前申请一次额外清运，当前学生已离校，现场环境正常。 | BALANCED | 2 | 65–85 | W13 | 任务有优先诉求但没有即时人群暴露，可平衡时效与路线成本。 |
| ut03-school-dismissal | URGENT_TASK | 学校放学时段临时产生大量包装垃圾，校门口学生与家长密集，保洁人员请求优先清运。 | URGENT_RESPONSE | 4 | 40–50 | W13 | 放学高峰的高人流与临时积存使任务具有明显时效敏感性。 |
| ut04-market-backroom | URGENT_TASK | 市场后场临时增加一批包装废弃物，作业区可暂存但商户希望本班次内完成清运。 | URGENT_RESPONSE | 3 | 50–65 | W14 | 明确临时优先请求，虽可短时暂存但仍需在较紧窗口内完成。 |
| ut04-food-safety | URGENT_TASK | 生鲜市场临时产生大量湿垃圾，靠近食品加工区并出现明显异味，管理方要求立即清运。 | URGENT_RESPONSE | 5 | 25–35 | W14 | 食品加工环境与湿垃圾异味构成较高卫生风险。 |
| ut05-night-additional | URGENT_TASK | 夜间低峰期临时增加一个清运请求，周边人流很少，现有车辆仍有充足余量。 | BALANCED | 2 | 60–80 | W15 | 低峰、低人流且资源充足，无需抢占式响应。 |
| ut05-stadium-after-event | URGENT_TASK | 体育场大型赛事刚散场，出口周边临时垃圾快速增加，观众仍在持续离场。 | URGENT_RESPONSE | 4 | 45–55 | W15 | 散场高人流与快速积存形成明确短时治理压力。 |
| vb01-backup-idle | VEHICLE_BREAKDOWN | 故障车辆承担的是普通路线，附近有两辆备用车空闲，剩余任务时间窗口较宽。 | MINIMAL_RESCHEDULE | 2 | 50–70 | — | 资源冗余充足，重点是平稳恢复并减少无谓改派。 |
| vb01-hospital-route | VEHICLE_BREAKDOWN | 故障车辆的后续路线中包含医院周边高优先任务，虽然有备用车辆，但剩余处理窗口很紧。 | URGENT_RESPONSE | 4 | 30–40 | — | 关键高优任务受故障直接影响，治理目标升级为快速恢复服务。 |
| vb02-after-shift | VEHICLE_BREAKDOWN | 车辆在完成当班主要任务后发生故障，当前没有关键任务依赖该车，剩余车辆容量充足。 | BALANCED | 1 | — | — | 故障对当前服务几乎无实质影响，不需要主动制造重调度。 |
| vb02-peak-backlog | VEHICLE_BREAKDOWN | 同一时段正处于清运高峰，故障车辆原本还承担多项未完成任务，其他车辆已有明显积压。 | URGENT_RESPONSE | 4 | 55–65 | — | 高峰积压与任务中断叠加，恢复时效成为主要治理目标。 |
| vb03-two-backups | VEHICLE_BREAKDOWN | 车辆途中故障，但调度中心附近有两辆备用车，剩余任务均为普通优先级。 | MINIMAL_RESCHEDULE | 2 | 40–55 | — | 备用资源充分，适合以最小扰动完成任务转移。 |
| vb03-capacity-tight | VEHICLE_BREAKDOWN | 车辆途中故障后只剩一辆可用车且剩余容量紧张，多项任务接近时限。 | URGENT_RESPONSE | 4 | 25–35 | — | 资源紧张且任务接近时限，需要优先保障快速恢复。 |
| vb04-near-route-end | VEHICLE_BREAKDOWN | 故障发生时该车辆已接近路线结束，剩余普通任务只有一项，其他车辆仍有余量。 | MINIMAL_RESCHEDULE | 2 | 60–80 | — | 影响范围有限，最小化改派即可恢复。 |
| vb04-sensitive-unfinished | VEHICLE_BREAKDOWN | 故障车辆尚有一项与重点医疗场所相关的高优任务未完成，当前时效窗口很短。 | URGENT_RESPONSE | 5 | 45–55 | — | 重点医疗场所任务受影响，故障已转化为高时效治理风险。 |
| vb05-no-active-assignment | VEHICLE_BREAKDOWN | 发生故障的是一辆当前未分配任务的备用车辆，现有路线均由其他车辆正常执行。 | BALANCED | 1 | — | — | 没有直接任务中断，短期无需重排现有路线。 |
| vb05-multiple-ordinary-assigned | VEHICLE_BREAKDOWN | 发生故障的车辆承担三项普通任务，但其余车辆仍可接管，暂无高优任务或敏感场所。 | MINIMAL_RESCHEDULE | 3 | 45–60 | — | 需要重调度但不存在高风险语境，应稳妥转移任务并减少改派。 |
| rc01-local-alternative | ROAD_CLOSURE | 一条局部支路临时施工封闭，替代道路充足，现有任务只需小幅绕行即可继续。 | MINIMAL_RESCHEDULE | 2 | 50–70 | — | 封路影响有限且有充分替代路线，宜最小化改派与路线扰动。 |
| rc01-event-arterial | ROAD_CLOSURE | 大型活动散场期间主干道路段突然封闭，多条现有清运路线受阻，周边任务正在快速积压。 | URGENT_RESPONSE | 4 | 30–40 | — | 高人流活动与主干道阻断叠加，要求快速恢复服务能力。 |
| rc02-not-on-route | ROAD_CLOSURE | 外围道路临时封闭，但当前所有清运车辆均未使用该路段，现有任务不受直接影响。 | BALANCED | 1 | — | — | 事件对当前计划无直接影响，不需要主动制造重调度扰动。 |
| rc02-blocks-two-routes | ROAD_CLOSURE | 同一道路封闭后同时切断两条正在执行的清运路线，未完成任务开始积压。 | URGENT_RESPONSE | 4 | 40–50 | — | 多条执行路线同时受阻，运营影响明显，应快速重新安排服务。 |
| rc03-short-planned | ROAD_CLOSURE | 已知施工导致道路短时封闭，调度中心提前获知信息，替代路线明确且预计很快恢复。 | MINIMAL_RESCHEDULE | 2 | 60–80 | — | 可预期、短时且替代路径明确，适合减少改派的最小重调度。 |
| rc03-hospital-access | ROAD_CLOSURE | 封闭路段位于医院周边关键通道，当前有高优清运任务需要经过附近区域，安全管制可能持续。 | URGENT_RESPONSE | 5 | 45–55 | — | 医院周边关键通道受阻且涉及高优任务，应视为高风险时效事件。 |
| rc04-industrial-alternative | ROAD_CLOSURE | 工业片区一条道路封闭，但车辆可通过相邻道路绕行，周边人流低且任务时间窗口较宽。 | MINIMAL_RESCHEDULE | 2 | 50–65 | — | 有明确绕行能力且无敏感人群压力，优先减少调度扰动即可。 |
| rc04-school-dismissal | ROAD_CLOSURE | 学校放学期间周边道路突然封闭，清运车辆与家长车辆混行，已有任务需要快速调整路线。 | URGENT_RESPONSE | 4 | 30–40 | — | 放学高峰叠加道路阻断和混行风险，应提高处置时效。 |
| rc05-peripheral-unused | ROAD_CLOSURE | 城市边缘道路临时封闭，当前没有清运路线经过，其他主干道路均正常。 | BALANCED | 1 | — | — | 对当前系统运行几乎无影响，保持常规策略即可。 |
| rc05-single-critical-corridor | ROAD_CLOSURE | 该道路虽然不处于高人流区域，但它是当前多个普通任务的主要通道，绕行会显著增加执行时间。 | MINIMAL_RESCHEDULE | 3 | 35–50 | — | 需要明确重调度，但无更高风险因素，适合以恢复服务并减少改派为主。 |
