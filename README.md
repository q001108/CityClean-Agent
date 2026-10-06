# CityClean-Agent

CityClean-Agent 是一个面向城市环卫资源约束场景的智能决策仿真与评测平台。项目使用真实地图底图展示空间关系，使用可复现的合成运营数据构造风险场景，并将大模型治理研判与确定性调度、独立验证和执行仿真明确分离。

> 当前项目没有接入真实政府环卫业务数据。垃圾桶、车辆、传感器和运营事件均为合成数据，不代表实际设施或运行状态。

## 核心链路

```text
确定性风险事实
  -> 规则基线 / DeepSeek 治理研判
  -> PolicyDecision 契约校验
  -> OR-Tools 车辆调度
  -> 独立 Verifier 硬约束验证
  -> CitySim 执行仿真
  -> 道路封闭或车辆故障后的动态重规划
```

大模型只负责风险等级、优先治理目标、响应时限、治理策略和约束研判，不直接生成路线、容量、距离或 ETA。数值优化由 OR-Tools 完成，方案必须通过 Verifier 后才能进入 CitySim。

## 当前基线能力

- 固定随机种子的城市道路、垃圾桶、车辆和风险场景生成。
- 资源约束研判实验台：默认 30 个候选、4 辆车、最多治理 10 个点。
- 相同输入下的规则与 DeepSeek A/B 研判。
- 目标覆盖、敏感场所覆盖、平均风险、路线距离和时限违约对比。
- 车辆调度、容量和时间窗约束验证。
- 执行时间推进、道路封闭、车辆故障及动态重规划。
- 天地图底图与无 Key 降级展示。
- FastAPI 产品接口、React 产品工作台和独立历史演示入口。
- 固定 Benchmark、治理 Gold 评测、错误分析和 Verifier 对抗测试。

详细边界和已知限制见 [当前基线说明](docs/current-baseline.md)，产品化架构见 [产品架构路线](docs/product-architecture.md)。

## 技术栈

- Python 3.11+
- FastAPI、Pydantic
- LangChain DeepSeek
- Google OR-Tools
- React 19、TypeScript、Vite、Ant Design
- Pytest

## 本地运行

### Docker Compose 合成 Demo

启动 Docker Engine 后，在项目根目录执行：

```powershell
docker compose up -d --build
```

如果本机从官方 PyPI 下载 Linux 包超时，可仅对这次构建指定包源，再启动服务：

```powershell
docker compose build --build-arg PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple api
docker compose up -d
```

打开 `http://127.0.0.1:8088/`。页面与 `/api` 使用同一入口；可用
`http://127.0.0.1:8088/api/v1/health` 检查后端。查看状态使用
`docker compose ps`；停止本项目容器使用 `docker compose down`（不要添加
`-v`）。容器中的仿真会话只保存在进程内存，停止后不会保留。

默认无需 API Key，即可使用规则研判、合成调度和执行仿真。仅在主动使用
DeepSeek 研判时，才需要在启动 Compose 的宿主机环境提供
`DEEPSEEK_API_KEY`；不要把 Key 写入仓库或镜像。天地图 Key 可选：如需底图，
在构建前将 `VITE_TIANDITU_KEY` 设置为宿主机环境变量，再执行上述构建命令。
Vite 会将它写入浏览器静态产物，因此它不是服务端秘密；不配置时地图区域会
显示缺少密钥的提示，调度和仿真操作仍可使用，但不会显示底图与地图覆盖物。
不要将 `frontend/.env.local` 或根目录 `.env` 放入镜像。

此入口只绑定本机 `127.0.0.1:8088`，用于本地合成 Demo。默认应用不会注入
生产 Runtime 或设施仓储；相应状态仍显示 unavailable／503，不能当作真实城市
运营数据。当前 Compose 未配置公网访问、认证或持久化服务。

### 开发环境

项目规定使用 Conda 环境 `langchain1.2`。

### 1. 安装后端

```powershell
conda activate langchain1.2
python -m pip install -e ".[dev]"
```

如需调用真实 DeepSeek，将 `.env.example` 复制为 `.env` 并在本地填写 Key。不要提交 `.env`。

### 2. 启动 API

```powershell
python -m uvicorn cityclean_agent.api.app:app --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/api/v1/health`；API 文档：`http://127.0.0.1:8000/docs`。

默认 API 提供合成网络、研判、调度和执行仿真。权威 Runtime 和设施台账没有在默认应用中注入，对应接口会明确返回 unavailable/503，不会用比赛 fixture 或 Mock 数据伪装生产状态。

### 3. 启动前端

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

天地图 Key 是可选项。未配置时地图组件显示说明并降级；开发服务器默认代理 `/api` 到 `http://127.0.0.1:8000`。

- 产品工作台：`http://127.0.0.1:5173/`

历史演示不属于默认上线构建。仅在需要查阅冻结回放时运行：

```powershell
npm run dev:demo
```

然后访问 `http://127.0.0.1:5173/demo.html`。

## 验证

```powershell
conda activate langchain1.2
python -m pytest -q

cd frontend
npm run build
```

默认测试不会访问真实模型或要求 API Key。需要真实 DeepSeek 的评测脚本位于 `scripts/`，必须显式执行。

## 项目结构

```text
src/cityclean_agent/
  agent/       # 规则/DeepSeek 研判与契约
  api/         # FastAPI 产品接口
  benchmark/   # 固定场景与消融评测
  domain/      # 城市状态和任务领域模型
  facilities/  # 设施台账模型与 SQLite 仓储
  optimizer/   # OR-Tools 调度
  runtime/     # 权威 CitySim 运行边界
  simulator/   # 合成场景、执行会话与扰动
  verifier/    # 独立硬约束验证
frontend/      # React 产品工作台与历史演示
knowledge_base/ # 离线 Gold、历史轨迹、报告和演示 fixture
data/          # 仅本地运行时数据库，默认不提交
artifacts/     # 可再生成的评测输出和验收产物，默认不提交
docs/          # 规格、架构和评测说明
scripts/       # 显式运行的评测与轨迹工具
tests/         # 单元和跨模块回归测试
```

## 安全与真实性

- API Key 只保存在本地 `.env` 或部署平台 Secrets 中。
- 浏览器端天地图 Key 由 `frontend/.env.local` 提供，不写入仓库。
- 默认自动化测试不调用外部模型。
- 合成数据、冻结轨迹和真实模型调用状态在界面与响应中显式区分。
- 系统遇到不可行约束时返回不可执行或需要人工处理，不生成虚假成功方案。
- 上线产品默认不读取或打包 Gold 数据、历史轨迹、历史演示 fixture 或评测报告；它们只由显式评测和独立 `demo.html` 开发入口使用。
