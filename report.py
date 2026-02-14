#!/usr/bin/env python3
"""
Process the results directory and generate a results table.

Reads result.json files from the results/ directory and produces:
  - A console table
  - A Markdown table (results_table.md)
  - A CSV file (results_table.csv)
"""

import argparse
import json
import sys
from pathlib import Path


RESULTS_DIR = Path("results")


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
                results.append({
                    "model": model_name,
                    "exam": exam_name,
                    "passed": data.get("passed", False),
                    "error": data.get("error"),
                })
    return results


def build_table(results: list[dict]) -> tuple[list[str], list[str], dict]:
    """Build the data structures for the results table.

    Returns: (models, exams, scores_dict)
    where scores_dict[(model, exam)] = True/False/None
    """
    models = sorted(set(r["model"] for r in results))
    exams = sorted(set(r["exam"] for r in results))

    scores = {}
    for r in results:
        scores[(r["model"], r["exam"])] = r["passed"]

    return models, exams, scores


def print_console_table(models: list[str], exams: list[str], scores: dict):
    """Print a formatted table to the console."""
    # Column widths
    model_col_w = max(len("Model"), max((len(m) for m in models), default=5))
    exam_col_w = max(len(e) for e in exams) if exams else 10
    score_col_w = 7

    # Header
    header = f"{'Model':<{model_col_w}}"
    for exam in exams:
        header += f" | {exam:^{exam_col_w}}"
    header += f" | {'Score':^{score_col_w}}"

    sep = "-" * len(header)

    print(sep)
    print(header)
    print(sep)

    # Rows
    for model in models:
        row = f"{model:<{model_col_w}}"
        passed_count = 0
        total_count = len(exams)
        for exam in exams:
            result = scores.get((model, exam))
            if result is True:
                cell = "PASS"
                passed_count += 1
            elif result is False:
                cell = "FAIL"
            else:
                cell = "N/A"
            row += f" | {cell:^{exam_col_w}}"
        row += f" | {passed_count}/{total_count}  "
        print(row)

    print(sep)


def generate_markdown(models: list[str], exams: list[str], scores: dict) -> str:
    """Generate a Markdown results table."""
    lines = []
    lines.append("# calcolatori-bench Results\n")

    # Table header
    header_cells = ["Model"] + exams + ["Score"]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    # Rows
    for model in models:
        passed_count = 0
        cells = [model]
        for exam in exams:
            result = scores.get((model, exam))
            if result is True:
                cells.append("✅")
                passed_count += 1
            elif result is False:
                cells.append("❌")
            else:
                cells.append("—")
        cells.append(f"{passed_count}/{len(exams)}")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def generate_csv(models: list[str], exams: list[str], scores: dict) -> str:
    """Generate a CSV results table."""
    lines = []
    header = ["Model"] + exams + ["Score"]
    lines.append(",".join(header))

    for model in models:
        passed_count = 0
        cells = [model]
        for exam in exams:
            result = scores.get((model, exam))
            if result is True:
                cells.append("PASS")
                passed_count += 1
            elif result is False:
                cells.append("FAIL")
            else:
                cells.append("N/A")
        cells.append(f"{passed_count}/{len(exams)}")
        lines.append(",".join(cells))

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Process calcolatori-bench results")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR,
                        help="Path to results directory (default: results/)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output Markdown file (default: results_table.md)")
    parser.add_argument("--csv", type=Path, default=None,
                        help="Output CSV file (default: results_table.csv)")
    args = parser.parse_args()

    results = load_results(args.results)
    if not results:
        print("No results found. Run evaluate.py first.")
        sys.exit(0)

    models, exams, scores = build_table(results)

    # Console output
    print_console_table(models, exams, scores)

    # Markdown output
    md_path = args.output or Path("results_table.md")
    md_content = generate_markdown(models, exams, scores)
    md_path.write_text(md_content)
    print(f"\nMarkdown table written to {md_path}")

    # CSV output
    csv_path = args.csv or Path("results_table.csv")
    csv_content = generate_csv(models, exams, scores)
    csv_path.write_text(csv_content)
    print(f"CSV table written to {csv_path}")

    # Summary
    print(f"\nTotal models: {len(models)}")
    print(f"Total exams:  {len(exams)}")
    for model in models:
        passed = sum(1 for e in exams if scores.get((model, e)) is True)
        print(f"  {model}: {passed}/{len(exams)}")


if __name__ == "__main__":
    main()
