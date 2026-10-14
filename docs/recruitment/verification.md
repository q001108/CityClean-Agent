# 投递版本验证记录

验证日期：2026-10-14。验证对象：当前 `codex/free-development` 分支的合成 Demo 与本次新增投递打包流程。精确提交由投递包根目录 `manifest.json` 记录，避免文档自引用提交号。

## 已完成验证

| 检查 | 实际结果 |
|---|---|
| 原有后端基线测试 | 256 passed，4 项第三方弃用警告 |
| 新增打包保护与集成测试 | 11 passed，包含真实临时 Git 仓库、忽略本机 `.env`、摘要验证、拒绝覆盖与脏工作区 |
| 合并后的完整测试 | 267 passed，4 项第三方弃用警告；Windows 使用 `PYTHONUTF8=1` |
| 打包脚本静态编译 / Git 差异检查 | `py_compile` 和 `git diff --check` 通过 |
| 前端 TypeScript 与生产构建 | `npm run build` 通过；存在单个压缩 chunk 大于 500 kB 的提醒 |
| 固定 Benchmark | 9 个场景 × 3 种条件，共 27 次执行；完成率均值为 59.8% / 75.9% / 79.6%，完全完成场景数为 2/9 / 6/9 / 7/9 |
| Microsoft Edge 浏览器演示 | 规则研判 → 10 个任务分配 → 独立校验通过 → 启动执行 → 推进到 08:05 → 封闭 `SE-002-F` → 重规划成功，路线 4 条变 2 条 |
| 无地图 Key 展示 | 合成路网、风险点、路线、车辆和封闭道路均可见；未调用天地图 |
| PDF 排版 | 两份 A4 PDF，各 3 页；使用 Poppler 渲染并逐页检查中文、表格、命令和分页 |
| 视频 | 原始 WebM 转为 H.264 / yuv420p MP4，1366 × 768、25 fps、73.32 秒，无音轨；完整解码通过，并抽查四个阶段画面 |
| Compose 配置 | `docker compose config --quiet` 通过 |

浏览器中默认设施接口出现 503，与未装配设施仓储的已知边界一致；页面明确显示该状态，不影响合成实验。无 Key 验收没有发生地图 SDK 异常或实时模型调用。

## 环境版本

| 环境 / 依赖 | 验证版本 |
|---|---|
| Conda 环境 | `langchain1.2` |
| Python / Node.js / npm | 3.12.13 / 24.15.0 / 11.12.1 |
| FastAPI / Pydantic / Uvicorn | 0.135.1 / 2.12.5 / 0.46.0 |
| langchain-deepseek / OR-Tools | 1.0.1 / 9.15.6755 |
| Pytest / HTTPX / python-dotenv | 9.0.3 / 0.28.1 / 1.2.1 |
| Streamlit（历史入口依赖） | 1.62.0 |
| React / React DOM / Ant Design | 19.2.8 / 19.2.8 / 6.6.1 |
| TypeScript / Vite / React 插件 | 5.9.3 / 8.2.2 / 5.2.0 |
| Docker Client / Compose | 29.6.1 / 5.3.0 |

前端完整版本锁在 `frontend/package-lock.json`。后端 `pyproject.toml` 保留原有版本范围，此表是已测试的环境快照，不是所有平台的依赖锁。

## 本次未验证与限制

- **容器重新构建与启动未完成**：本机 Docker Desktop 4.82.0 在启动 Inference manager 时遇到 `dockerInference` socket 无法访问错误，Engine 未启动；WSL 的 docker-desktop 状态为 Stopped。没有据此修改项目 Compose、清空 Docker 数据或重置环境。此前演示素材来自既有 Compose 合成 Demo；本次实时浏览器验收使用本地源码启动路径。
- **未重新调用真实 DeepSeek**：当前测试与视频均为规则 / 离线模式。真实模型指标来自仓库冻结报告，不冒充本次在线实测；模型账号权限、费用与服务可用性未重新验证。
- **真实地图与生产接入未验收**：投递默认流程使用无 Key 合成路网；权威 Runtime、设施仓储装配、认证、多人隔离和生产持久化不在当前默认产品能力内。
- **Windows 编码差异**：直接只给测试父进程加 `-X utf8` 时，两个原有 CLI 子进程测试因 GBK / UTF-8 解码差异失败。通过给进程环境设置 `PYTHONUTF8=1` 后完整测试通过；没有修改或削弱测试断言。

## 打包与版本核对

`scripts/package_recruitment.py` 从干净的已提交 HEAD 导出源码，临时关闭导出的 CRLF 转换，以保留 Git 中的源码字节；不修改 Git 配置。脚本排除本机未跟踪/忽略文件，拒绝敏感路径与常见凭据格式，并逐项验证 ZIP 内容与 SHA-256 摘要。具体文件数量、大小、提交号和完整摘要由最终包内 manifest 与包旁 `.zip.sha256` 提供。

源码与投递资料同步到 GitHub 当前默认分支 `codex/free-development`。整理时仓库为私有；可使用离线投递包向招聘方展示和提供源码，不要求对方访问仓库。
