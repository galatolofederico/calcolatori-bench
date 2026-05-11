#!/usr/bin/env python3
"""
Build a JSON file from the results directory for the leaderboard website.

Reads result.json files from results/<harness>/ subdirectories and produces a
leaderboard_data.json file that can be consumed by the static website.

Each subdirectory under results/ represents a harness (e.g. opencode).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path("results")
OUTPUT_FILE = Path("site/leaderboard_data.json")


def load_results(results_dir: Path, harness: str) -> list[dict]:
    """Load all result.json files for a specific harness under results/<harness>/."""
    results = []
    harness_dir = results_dir / harness
    if not harness_dir.exists():
        return results

    for model_dir in sorted(harness_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        model_info_path = model_dir / "model_info.json"
        display_name = model_name
        if model_info_path.exists():
            try:
                with open(model_info_path) as f:
                    model_info = json.load(f)
                    display_name = model_info.get("display_name", model_name)
            except (json.JSONDecodeError, IOError):
                pass
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
                        "harness": harness,
                        "model": model_name,
                        "display_name": display_name,
                        "exam": exam_name,
                        "passed": data.get("passed", False),
                        "error": data.get("error"),
                        "diff": data.get("diff", ""),
                        "output": data.get("output", []),
                        "expected": data.get("expected", []),
                        "boot_output": data.get("boot_output", ""),
                        "agent_output": data.get("agent_output", ""),
                        "duration_seconds": data.get("duration_seconds"),
                        "actual_turns": data.get("turns"),
                        "max_turns": data.get("max_turns"),
                    }
                )
    return results


def discover_harnesses(results_dir: Path) -> list[str]:
    """Discover harness subdirectories under results/."""
    harnesses = []
    if not results_dir.exists():
        return harnesses

    for entry in sorted(results_dir.iterdir()):
        if entry.is_dir() and any(
            sub.is_dir() for sub in entry.iterdir()
        ):
            harnesses.append(entry.name)
    return harnesses


def build_leaderboard_data(results: list[dict]) -> dict:
    """Build the leaderboard data structure with harness support.

    Models from different harnesses are treated as distinct entries, keyed
    by a compound model_key = f"{harness}:{model}".
    """
    harnesses = sorted(set(r["harness"] for r in results))
    exams = sorted(set(r["exam"] for r in results))

    # Build unique model entries (model + harness combos)
    model_keys = sorted(set(f"{r['harness']}:{r['model']}" for r in results))

    # Parse model keys into components
    model_info = {}  # model_key -> {harness, model, display_name}
    for mk in model_keys:
        harness, _, model = mk.partition(":")
        matching = [r for r in results if r["harness"] == harness and r["model"] == model]
        model_info[mk] = {
            "harness": harness,
            "model": model,
            "display_name": matching[0]["display_name"] if matching else model,
        }

    # Per-model stats keyed by compound key
    model_stats = {}
    for mk in model_keys:
        info = model_info[mk]
        harness = info["harness"]
        model = info["model"]
        model_results = [r for r in results if r["harness"] == harness and r["model"] == model]
        passed = sum(1 for r in model_results if r["passed"])
        total = len(model_results)
        total_steps = sum(r["actual_turns"] or 0 for r in model_results)
        max_steps = sum(r["max_turns"] or 100 for r in model_results)
        model_stats[mk] = {
            "display_name": info["display_name"],
            "harness": harness,
            "model": model,
            "passed": passed,
            "total": total,
            "percentage": round(passed / total * 100, 1) if total > 0 else 0,
            "total_steps": total_steps,
            "max_steps": max_steps,
        }

    exam_results = {}
    detailed_results = {}
    for exam in exams:
        exam_results[exam] = {}
        for mk in model_keys:
            info = model_info[mk]
            harness = info["harness"]
            model = info["model"]
            result = next(
                (r for r in results if r["harness"] == harness and r["model"] == model and r["exam"] == exam),
                None,
            )
            if result:
                exam_results[exam][mk] = {
                    "passed": result["passed"],
                    "error": result["error"],
                    "harness": result["harness"],
                }
                detailed_results.setdefault(mk, {})[exam] = {
                    "harness": result["harness"],
                    "passed": result["passed"],
                    "error": result["error"],
                    "diff": result["diff"],
                    "output": result["output"],
                    "expected": result["expected"],
                    "boot_output": result["boot_output"],
                    "agent_output": result["agent_output"],
                    "duration_seconds": result["duration_seconds"],
                    "actual_turns": result["actual_turns"],
                    "max_turns": result["max_turns"],
                }
            else:
                exam_results[exam][mk] = {
                    "passed": None,
                    "error": "No result",
                    "harness": None,
                }

    # Harness-level stats
    harness_stats = {}
    for harness in harnesses:
        harness_results = [r for r in results if r["harness"] == harness]
        harness_models = sorted(set(r["model"] for r in harness_results))
        harness_passed = sum(1 for r in harness_results if r["passed"])
        harness_total = len(harness_results)
        harness_stats[harness] = {
            "models": len(harness_models),
            "total_exams": len(harness_results),
            "passed": harness_passed,
            "percentage": round(harness_passed / harness_total * 100, 1) if harness_total > 0 else 0,
        }

    # Models per harness (for filter tabs)
    harness_models = {}
    for harness in harnesses:
        harness_models[harness] = [mk for mk in model_keys if model_info[mk]["harness"] == harness]

    sorted_models = sorted(
        model_keys,
        key=lambda mk: (model_stats[mk]["passed"], model_stats[mk]["total"]),
        reverse=True,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "harnesses": harnesses,
        "harness_stats": harness_stats,
        "harness_models": harness_models,
        "total_models": len(model_keys),
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

    harnesses = discover_harnesses(results_dir)
    if not harnesses:
        print("No harness directories found in results/.")
        leaderboard_data = {
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "harnesses": [],
            "harness_stats": {},
            "harness_models": {},
            "total_models": 0,
            "total_exams": 0,
            "models": [],
            "exams": [],
            "model_stats": {},
            "exam_results": {},
            "detailed_results": {},
        }
    else:
        all_results = []
        for harness in harnesses:
            results = load_results(results_dir, harness)
            all_results.extend(results)

        if not all_results:
            print("No results found. Run evaluate-opencode.py first.")
        leaderboard_data = build_leaderboard_data(all_results)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(leaderboard_data, f, indent=2)

    print(f"Leaderboard data written to {output_file}")
    print(f"  Harnesses: {leaderboard_data['harnesses']}")
    print(f"  Models: {leaderboard_data['total_models']}")
    print(f"  Exams:  {leaderboard_data['total_exams']}")

    if leaderboard_data["models"]:
        print("\nLeaderboard:")
        for i, mk in enumerate(leaderboard_data["models"], 1):
            stats = leaderboard_data["model_stats"][mk]
            display_name = stats.get("display_name", mk)
            harness = stats.get("harness", "")
            print(
                f"  {i}. {display_name} [{harness}]: "
                f"{stats['passed']}/{stats['total']} ({stats['percentage']}%)"
            )


if __name__ == "__main__":
    main()
