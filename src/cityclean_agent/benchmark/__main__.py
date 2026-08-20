"""Run every fixed v0.1 benchmark scenario and write JSON results."""

from pathlib import Path

from cityclean_agent.benchmark.runner import BenchmarkRunner, write_results


def main() -> None:
    """Execute the scenario bank and print a compact plain-text summary."""

    results = BenchmarkRunner().run_all()
    write_results(Path("benchmark_comparison_results.json"), results)
    print("scenario                  mode                     completion  urgent  avg_response  overflow  distance  status")
    for result in results:
        metrics = result.metrics
        print(
            f"{result.scenario_id:<25} "
            f"{result.benchmark_mode.value:<24} "
            f"{metrics.task_completion_rate:>10.2f} "
            f"{metrics.urgent_task_completion_rate:>7.2f} "
            f"{metrics.average_response_time:>13.2f} "
            f"{metrics.overflow_count:>9} "
            f"{metrics.total_distance:>9.2f} "
            f"{result.terminal_status}"
        )


if __name__ == "__main__":
    main()
