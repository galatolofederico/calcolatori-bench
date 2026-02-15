#!/usr/bin/env python3
"""
Build a JSON file from the results directory for the leaderboard website.

Reads result.json files from results/ and produces a leaderboard_data.json
file that can be consumed by the static website.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path("results")
OUTPUT_FILE = Path("site/leaderboard_data.json")


def load_results(results_dir: Path) -> list[dict]:
    """Load all result.json files from the results directory."""
    results = []
    if not results_dir.exists():
        return results

    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        for exam_dir in sorted(model_dir.iterdir()):
            if not exam_dir.is_dir():
                continue
            exam_name = exam_dir.name
            result_file = exam_dir / "result.json"
            if result_file.exists():
                with open(result_file) as f:
                    data = json.load(f)
                results.append(
                    {
                        "model": model_name,
                        "exam": exam_name,
                        "passed": data.get("passed", False),
                        "error": data.get("error"),
                        "diff": data.get("diff", ""),
                        "output": data.get("output", []),
                        "expected": data.get("expected", []),
                        "boot_output": data.get("boot_output", ""),
                        "agent_output": data.get("agent_output", ""),
                        "duration_seconds": data.get("duration_seconds"),
                    }
                )
    return results


def build_leaderboard_data(results: list[dict]) -> dict:
    """Build the leaderboard data structure."""
    models = sorted(set(r["model"] for r in results))
    exams = sorted(set(r["exam"] for r in results))

    model_stats = {}
    for model in models:
        model_results = [r for r in results if r["model"] == model]
        passed = sum(1 for r in model_results if r["passed"])
        total = len(model_results)
        model_stats[model] = {
            "passed": passed,
            "total": total,
            "percentage": round(passed / total * 100, 1) if total > 0 else 0,
        }

    exam_results = {}
    detailed_results = {}
    for exam in exams:
        exam_results[exam] = {}
        for model in models:
            result = next(
                (r for r in results if r["model"] == model and r["exam"] == exam), None
            )
            if result:
                exam_results[exam][model] = {
                    "passed": result["passed"],
                    "error": result["error"],
                }
                detailed_results.setdefault(model, {})[exam] = {
                    "passed": result["passed"],
                    "error": result["error"],
                    "diff": result["diff"],
                    "output": result["output"],
                    "expected": result["expected"],
                    "boot_output": result["boot_output"],
                    "agent_output": result["agent_output"],
                    "duration_seconds": result["duration_seconds"],
                }
            else:
                exam_results[exam][model] = {
                    "passed": None,
                    "error": "No result",
                }

    sorted_models = sorted(
        models,
        key=lambda m: (model_stats[m]["passed"], model_stats[m]["total"]),
        reverse=True,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_models": len(models),
        "total_exams": len(exams),
        "models": sorted_models,
        "exams": exams,
        "model_stats": model_stats,
        "exam_results": exam_results,
        "detailed_results": detailed_results,
    }


def main():
    parser_args = sys.argv[1:]
    results_dir = Path("results")
    output_file = Path("site/leaderboard_data.json")

    i = 0
    while i < len(parser_args):
        if parser_args[i] == "--results" and i + 1 < len(parser_args):
            results_dir = Path(parser_args[i + 1])
            i += 2
        elif parser_args[i] == "--output" and i + 1 < len(parser_args):
            output_file = Path(parser_args[i + 1])
            i += 2
        else:
            i += 1

    results = load_results(results_dir)
    if not results:
        print("No results found. Run evaluate.py first.")
        leaderboard_data = {
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "total_models": 0,
            "total_exams": 0,
            "models": [],
            "exams": [],
            "model_stats": {},
            "exam_results": {},
            "detailed_results": {},
        }
    else:
        leaderboard_data = build_leaderboard_data(results)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(leaderboard_data, f, indent=2)

    print(f"Leaderboard data written to {output_file}")
    print(f"  Models: {leaderboard_data['total_models']}")
    print(f"  Exams:  {leaderboard_data['total_exams']}")

    if leaderboard_data["models"]:
        print("\nLeaderboard:")
        for i, model in enumerate(leaderboard_data["models"], 1):
            stats = leaderboard_data["model_stats"][model]
            print(
                f"  {i}. {model}: {stats['passed']}/{stats['total']} ({stats['percentage']}%)"
            )


if __name__ == "__main__":
    main()
