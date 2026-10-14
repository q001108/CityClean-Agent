# 校招投递资料

本目录将当前已实现能力整理为招聘方可阅读、运行和复核的项目作品，保持产品逻辑与历史评测资源原有结构。

## 文件

- `project-overview.md` / `.pdf`：整体项目说明。
- `getting-started.md` / `.pdf`：独立启动说明。
- `demo-guide.md`：视频条件与内容。
- `verification.md`：本次实际检查、版本与未验证项。
- `package-index.html`：投递包离线首页模板；打包时写入精确源码提交。

所有源码文档和附件随当前默认分支同步至 GitHub。ZIP 为生成产物，不提交回源码仓库。

## 重新打包

先完成测试、构建与源码提交，确认 Git 工作区干净。在源码根目录执行：

```powershell
conda activate langchain1.2
python scripts/package_recruitment.py
```

如需指定输出目录：

```powershell
python scripts/package_recruitment.py --output-dir "C:/Delivery/CityClean"
```

脚本仅使用 Python 标准库与 Git；从 `git archive HEAD` 导出完整提交快照，生成离线首页、PDF、MP4、源码目录、manifest 和 SHA-256 清单。已提交的 PDF 与视频直接复制，无需安装排版或转码工具。脚本拒绝脏工作区、敏感路径、常见凭据格式和覆盖既有投递包，并在完成后检验 ZIP 内容。

ZIP 中不包含 `.git`、本机 `.env`、浏览器状态、node_modules、缓存或运行数据库。`.env.example` 和前端 `package-lock.json` 保留。源码中的历史规格、Gold、轨迹及原始演示素材保留，便于技术评审复核。

打包脚本不负责提交、推送、更改仓库权限或发布 Release；本地包的 `source_commit` 可与 GitHub 分支提交独立核对。
