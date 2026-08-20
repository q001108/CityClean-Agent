# AGENTS.md

# Repository Guidelines

## Project Purpose

CityClean-Agent 是面向城市突发环卫事件的自主研判与动态调度智能体。

项目核心目标是形成：

```text
环境感知
→ 事件研判
→ 调度优化
→ 方案验证
→ 仿真执行
→ 环境反馈
→ 必要时重新规划
```

的完整闭环，而不是构建普通聊天机器人或单纯的车辆路径规划程序。

## Project-Wide Rules

除非当前版本规格明确修改，否则遵守以下长期规则：

1. LLM 负责理解非结构化事件、判断治理优先级和生成结构化治理策略，不直接计算车辆路线、最短路径、容量、距离或确定性数值结果。

2. 调度和车辆路径优化由确定性算法负责，v0.1 优先使用 OR-Tools。

3. Verifier 必须独立于 LLM，用于检查调度方案是否违反硬约束。

4. CitySim 是模拟城市运行状态的真值来源，避免不同模块维护相互冲突的环境状态。

5. Benchmark 和仿真必须尽可能 deterministic，并支持固定随机种子。

6. 项目必须能够在普通 CPU 环境运行，不得把 CUDA、独立显卡或本地大模型作为必要依赖。

7. 未经当前规格或用户明确要求，不得主动加入 RAG、向量数据库、多智能体框架、MCP、地图 API、图像识别、强化学习、模型微调、微服务或 Kubernetes。

8. 不得擅自扩大当前任务范围。优先完成最小、正确、可测试的实现。

9. `docs/spec-v*.md` 定义对应版本的具体需求。若规格与现有实现发生冲突，应先指出问题，不要静默改变规格含义。

10. 新增设计应优先考虑可测试性、可解释性以及后续 Benchmark 和消融实验的需要，避免无实际需求的过度工程化。

## Local Development Environment

本项目本地开发统一使用 Conda 环境：

`langchain1.2`

运行 Python、pytest、安装依赖和执行项目命令时，应使用该环境。
不要使用系统默认 Python 或其他 Conda/Python 环境来绕过依赖问题。

## Project Structure & Module Organization

Keep importable Python code under `src/cityclean_agent/` and mirror that structure where appropriate under `tests/`.

Recommended layout:

```text
src/cityclean_agent/
    domain/
    simulator/
    agent/
    optimizer/
    verifier/
    benchmark/

tests/
assets/
scripts/
docs/
```

Put reusable prompts or small static data in `assets/`, developer utilities in `scripts/`, and design notes or version specifications in `docs/`.

Keep generated output, local datasets, caches, and virtual environments out of version control.

## Build, Test, and Development Commands

Prefer a `pyproject.toml` for dependency and project configuration.

A conventional local workflow is:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

Use:

```powershell
python -m cityclean_agent
```

for local execution once the package entry point exists.

Do not document commands that do not yet work from the repository root.

## Coding Style & Naming Conventions

Use four-space indentation, UTF-8 files, type hints for public interfaces, and concise docstrings for non-obvious behavior.

Use:

- `snake_case` for modules and functions;
- `PascalCase` for classes;
- `UPPER_SNAKE_CASE` for constants.

Keep agent tools and domain services small and explicit about inputs, outputs, and side effects.

If formatting or linting is introduced, configure it centrally in `pyproject.toml`.

Avoid unnecessary abstractions or framework layers added only for possible future requirements.

## Testing Guidelines

Use `pytest`.

Name files:

```text
test_*.py
```

and tests:

```text
test_<behavior>
```

Add unit tests for decision logic, simulation state transitions, optimization constraints, and verifier behavior.

Add integration tests for important cross-module flows.

Mock network calls and external services so the default test suite remains deterministic and does not require API credentials.

Every bug fix should include a regression test.

Do not weaken valid assertions simply to make tests pass.

## Commit & Pull Request Guidelines

There is no Git history from which to infer an existing convention.

Use short, imperative commit subjects such as:

```text
Add service task model
Implement simulator step
Fix duplicate task assignment
Add road closure regression test
```

Keep each commit focused.

Pull requests should explain the problem and solution, list verification commands, and call out configuration or API changes when relevant.

## Security & Configuration

Never commit API keys, tokens, credentials, or `.env` files.

Provide redacted examples in `.env.example`.

Validate required settings at startup when external services are enabled.

Avoid logging secrets, authorization headers, or sensitive location data.