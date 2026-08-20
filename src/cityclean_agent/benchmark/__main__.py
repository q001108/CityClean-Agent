"""Run every fixed v0.1 benchmark scenario and write JSON results."""

from pathlib import Path

from cityclean_agent.benchmark.runner import BenchmarkRunner, write_results
from cityclean_agent.presentation import BENCHMARK_MODE_LABELS, STATUS_LABELS, labeled


def main() -> None:
    """Execute the scenario bank and print a compact plain-text summary."""

    results = BenchmarkRunner().run_all()
    write_results(Path("benchmark_comparison_results.json"), results)
    print(
        "场景 ID                    调度模式                              "
        "任务完成率  紧急任务完成率  平均响应时间  满溢次数  总行驶距离  终态"
    )
    for result in results:
        metrics = result.metrics
        print(
            f"{result.scenario_id:<25} "
            f"{labeled(result.benchmark_mode.value, BENCHMARK_MODE_LABELS):<42} "
            f"{metrics.task_completion_rate:>12.2f} "
            f"{metrics.urgent_task_completion_rate:>14.2f} "
            f"{metrics.average_response_time:>14.2f} "
            f"{metrics.overflow_count:>8} "
            f"{metrics.total_distance:>10.2f} "
            f"{labeled(result.terminal_status, STATUS_LABELS)}"
        )


if __name__ == "__main__":
    main()
