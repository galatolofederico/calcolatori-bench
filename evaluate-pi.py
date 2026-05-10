#!/usr/bin/env python3
"""
calcolatori-bench: LLM benchmark for the Calcolatori Elettronici course.

Evaluates LLM agents (via pi) on exam exercise 2 (nucleo kernel exercises).
For each model x exam combination, spawns a Docker container, runs the agent,
then verifies the output.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional

ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

DOCKER_IMAGE = "calcolatori-bench"
RESULTS_DIR = Path("results/pi")
EXAMS_DIR = Path("exams")
MODELS_CONFIG = Path("models.toml")

MAX_ITERATIONS = 50


def interpolate_env_vars(value: str) -> str:
    """Interpolate environment variables in a string value.
    Supports ${VAR_NAME} syntax. Falls back to empty string if var is not set.
    """

    def replace_var(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return ENV_VAR_PATTERN.sub(replace_var, value)


def interpolate_dict_env_vars(d: dict) -> dict:
    """Recursively interpolate environment variables in dict values."""
    result = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = interpolate_env_vars(value)
        elif isinstance(value, dict):
            result[key] = interpolate_dict_env_vars(value)
        else:
            result[key] = value
    return result


def load_models(config_path: Path) -> list[dict]:
    """Load model configurations from TOML file with env var interpolation."""
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    models = config.get("model", [])
    return [interpolate_dict_env_vars(m) for m in models]


def load_api_key(model: dict) -> str:
    """Load API key for a custom model from model config (with env var interpolation)."""
    api_key = model.get("api_key", "")
    if not api_key:
        raise ValueError(f"Custom model '{model['name']}' requires 'api_key' in config")
    return api_key


def discover_exams(exams_dir: Path) -> list[Path]:
    """Discover all exam directories that contain es2.zip and testo.pdf."""
    exams = []
    for d in sorted(exams_dir.iterdir()):
        if d.is_dir() and (d / "es2.zip").exists() and (d / "testo.pdf").exists():
            exams.append(d)
    return exams


def sanitize_path(name: str) -> str:
    """Sanitize a name for use in filesystem paths (replace colons, etc.)."""
    return re.sub(r"[^\w\-.]", "_", name)


def result_dir(model_name: str, exam_name: str) -> Path:
    """Get the results directory for a model x exam combination."""
    return RESULTS_DIR / sanitize_path(model_name) / exam_name


def is_cached(model_name: str, exam_name: str) -> bool:
    """Check if we already have results for this combination."""
    rd = result_dir(model_name, exam_name)
    return (rd / "result.json").exists()


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text content from a PDF file using pdftotext."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"  WARNING: pdftotext failed for {pdf_path}: {result.stderr}")
        return ""
    return result.stdout


def generate_pi_models_json(model: dict, api_key: str) -> dict:
    """Generate a models.json configuration for pi's custom provider.

    pi uses ~/.pi/agent/models.json for custom model configuration.
    The format is:
    {
      "providers": {
        "custom": {
          "baseUrl": "...",
          "api": "openai-completions",
          "apiKey": "...",
          "models": [{"id": "..."}]
        }
      }
    }
    """
    model_id = model["model_id"]
    base_url = model["base_url"]

    # Determine compat settings from model config
    compat = {}
    if model.get("compat"):
        compat = model["compat"]

    provider_config = {
        "baseUrl": base_url,
        "api": "openai-completions",
        "apiKey": api_key,
        "models": [{"id": model_id}],
    }

    if compat:
        provider_config["compat"] = compat

    return {"providers": {"custom": provider_config}}


def normalize_output(text: str) -> list[str]:
    """Extract and normalize USR lines from output for comparison.

    Applies: grep "USR" | sed -E 's/USR\\s+[0-9]+\\s+/USR /'
    Then strips the "USR " prefix so we can compare with es2.out.0.

    Note: AUTOCORR=1 must be set at compile time (adds -DAUTOCORR which
    redirects video output to the log as USR level lines) AND at runtime
    (enables -nographic in the boot script so output goes to stdout).
    """
    lines = []
    for line in text.splitlines():
        if "USR" in line:
            # Apply the sed transformation: strip "USR <number> " prefix
            normalized = re.sub(r"USR\s+[0-9]+\s+", "USR ", line.strip())
            # Strip the "USR " prefix to match es2.out.0 format
            if normalized.startswith("USR "):
                normalized = normalized[4:]
            if normalized:
                lines.append(normalized)
    return lines


def load_expected_outputs(exam_dir: Path) -> list[list[str]]:
    """Load all expected output variants (es2.out.0, es2.out.1, ...)."""
    variants = []
    for f in sorted(exam_dir.glob("es2.out.*")):
        text = f.read_text()
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        variants.append(lines)
    return variants


def compare_output(actual_lines: list[str], expected_variants: list[list[str]]) -> bool:
    """Check if actual output matches any expected variant."""
    for expected in expected_variants:
        if actual_lines == expected:
            return True
    return False


def check_docker_image():
    """Check if the required Docker image exists."""
    result = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True, text=True
    )
    return result.returncode == 0


def build_docker_image():
    """Build the Docker image from container/Dockerfile.pi."""
    print("==> Building Docker image...")
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            DOCKER_IMAGE,
            "-f",
            "container/Dockerfile.pi",
            ".",
        ],
        capture_output=False,
        timeout=30 * 60,
    )
    if result.returncode != 0:
        print("ERROR: Failed to build Docker image")
        sys.exit(1)
    print("==> Docker image built successfully")


def count_turns_from_jsonl(jsonl_text: str) -> int:
    """Count the number of turns from pi's JSON mode output.

    Each turn_end event represents one completed turn (LLM call + tool use).
    """
    count = 0
    for line in jsonl_text.strip().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "turn_end":
                count += 1
        except json.JSONDecodeError:
            continue
    return count


def run_exam(
    model: dict,
    exam_dir: Path,
    api_key: str,
    timeout_agent: int = 300,
    max_iterations: int = 50,
) -> dict:
    """Run a single model x exam evaluation.

    Returns a dict with keys: passed, output, expected, diff, error
    """
    model_name = model["name"]
    exam_name = exam_dir.name
    model_id = model["model_id"]
    base_url = model["base_url"]

    print(f"\n{'=' * 60}")
    print(f"  Model: {model_name}")
    print(f"  Exam:  {exam_name}")
    print(f"{'=' * 60}")

    rd = result_dir(model_name, exam_name)
    rd.mkdir(parents=True, exist_ok=True)

    # Extract PDF text
    print("  -> Extracting testo.pdf...")
    pdf_text = extract_pdf_text(exam_dir / "testo.pdf")
    if not pdf_text:
        return {
            "passed": False,
            "output": "",
            "expected": "",
            "diff": "",
            "error": "Failed to extract PDF",
        }

    # Generate pi models.json config
    pi_models_json = generate_pi_models_json(model, api_key)
    models_json_path = rd / "models.json"
    with open(models_json_path, "w") as f:
        json.dump(pi_models_json, f, indent=2)

    # Construct the agent prompt
    prompt = f"""You are solving Exercise 2 (es2) from a Calcolatori Elettronici exam.

The exercise involves modifying kernel (nucleo) source code. The modifications are marked with "ESAME" in the source files, and the parts where you need to insert your solution are marked with "SOLUZIONE".

Here is the exam text:
---
{pdf_text}
---

Instructions:
1. Read the source files in the current directory to understand the exercise.
2. Look for files containing "ESAME" and "SOLUZIONE" markers.
3. Implement the solution by replacing the "SOLUZIONE" markers with your code.
4. Run `make` to compile the code. Fix any compilation errors.
5. IMPORTANT: NEVER run `boot` directly. ALWAYS use `timeout 10s boot` to test your solution.
6. The environment variable AUTOCORR=1 is already set. This causes video output to appear in the log as lines starting with "USR". Check those lines to verify correctness.
7. If there are errors, analyze them and fix your solution.
8. Repeat steps 4-7 until the solution works correctly.

CRITICAL RULES:
- NEVER use the `git` command for any reason during execution. Do not run git status, git diff, git log, git commit, or any other git subcommands.
- ALWAYS use `timeout 10s boot` instead of `boot` - this is critical to avoid hanging!
"""

    # Create a container and run the evaluation
    container_name = re.sub(r"[^a-zA-Z0-9_.-]", "-", f"bench-pi-{model_name}-{exam_name}")

    # Clean up any existing container with same name
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    print("  -> Starting container...")

    # Build a script to run inside the container
    prompt_escaped = prompt.replace("'", "'\\''")

    inner_script = f"""#!/bin/bash
set -e

cd /work

# Extract es2.zip
unzip -o /tmp/es2.zip
cd /work/es2/nucleo

# Create .gitignore to only track relevant source files
cat > .gitignore << 'GITIGNORE'
# Ignore everything by default
*

# But track source files
!*.cpp
!*.s
!*.h
!*.asm
!*.c
!.gitignore

# Don't ignore directories (needed for git to traverse)
!*/
GITIGNORE

# Initialize git repo to track changes
git init
git config user.email "agent@bench.local"
git config user.name "Agent"
git add -A
git commit -m "initial state" --allow-empty

# Add all files to track
git add -A
git commit -m "before agent" --allow-empty

# Set up pi models.json config
mkdir -p ~/.pi/agent
cp /tmp/models.json ~/.pi/agent/models.json

# Run pi agent in JSON mode
cd /work/es2/nucleo

pi --mode json \\
  --no-session \\
  --no-context-files \\
  --no-extensions \\
  -e /opt/pi-extensions/max-iterations.ts \\
  --max-iterations {max_iterations} \\
  --model custom/{model_id} \\
  '{prompt_escaped}' 2>&1 | tee /tmp/agent_output.log || true

# Save the diff
git diff > /tmp/solution.diff
git add -A
git diff --cached >> /tmp/solution.diff

# Now run the verification (AUTOCORR=1 is set in the container env)
# AUTOCORR=1 must be set at both compile time (adds -DAUTOCORR to redirect
# video output to log as USR level) and runtime (enables -nographic in boot)
export AUTOCORR=1
make clean 2>&1 || true
make 2>&1 || echo "MAKE_FAILED"
timeout 10s boot > /tmp/boot_output.txt 2>&1 || true

# Extract and normalize USR lines, then strip the "USR " prefix
# to match the format of es2.out.0
grep "USR" /tmp/boot_output.txt | sed -E 's/USR\\s+[0-9]+\\s+/USR /' | sed 's/^USR //' > /tmp/normalized_output.txt 2>/dev/null || true

# Create artifact zip of es2 folder
cd /work
zip -r /tmp/es2_artifact.zip es2 2>/dev/null || true

echo "===DONE==="
"""

    script_path = rd / "run_inner.sh"
    with open(script_path, "w") as f:
        f.write(inner_script)

    start_time = time.time()

    try:
        # Start the container
        print("  -> Running agent in container (this may take a while)...")
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--name",
                container_name,
                "-e",
                "AUTOCORR=1",
                "-v",
                f"{(exam_dir / 'es2.zip').resolve()}:/tmp/es2.zip:ro",
                "-v",
                f"{models_json_path.resolve()}:/tmp/models.json:ro",
                "-v",
                f"{script_path.resolve()}:/tmp/run_inner.sh:ro",
                DOCKER_IMAGE,
                "bash",
                "/tmp/run_inner.sh",
            ],
            text=True,
            timeout=timeout_agent,
        )
        duration_seconds = time.time() - start_time

        # Copy artifacts out of the container
        for artifact in [
            "solution.diff",
            "boot_output.txt",
            "normalized_output.txt",
            "agent_output.log",
            "es2_artifact.zip",
        ]:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{container_name}:/tmp/{artifact}",
                    str(rd / artifact),
                ],
                capture_output=True,
            )

    except subprocess.TimeoutExpired:
        print(f"  -> TIMEOUT after {timeout_agent}s")
        (rd / "error.txt").write_text(f"Agent timed out after {timeout_agent}s")
        for artifact in [
            "solution.diff",
            "boot_output.txt",
            "normalized_output.txt",
            "agent_output.log",
            "es2_artifact.zip",
        ]:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{container_name}:/tmp/{artifact}",
                    str(rd / artifact),
                ],
                capture_output=True,
            )
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        diff_text = ""
        diff_path = rd / "solution.diff"
        if diff_path.exists():
            diff_text = diff_path.read_text()
        boot_output = ""
        boot_path = rd / "boot_output.txt"
        if boot_path.exists():
            boot_output = boot_path.read_text()
        agent_output = ""
        agent_output_path = rd / "agent_output.log"
        if agent_output_path.exists():
            agent_output = agent_output_path.read_text()
        normalized_output_path = rd / "normalized_output.txt"
        actual_text = (
            normalized_output_path.read_text()
            if normalized_output_path.exists()
            else ""
        )
        actual_lines = [
            l.strip() for l in actual_text.strip().splitlines() if l.strip()
        ]
        expected_variants = load_expected_outputs(exam_dir)
        turns = None
        if agent_output:
            turns = count_turns_from_jsonl(agent_output)
        result_data = {
            "passed": False,
            "output": actual_lines,
            "expected": expected_variants[0] if expected_variants else [],
            "boot_output": boot_output,
            "agent_output": agent_output,
            "diff": diff_text,
            "duration_seconds": timeout_agent,
            "turns": turns,
            "max_turns": max_iterations,
            "error": f"Timeout after {timeout_agent}s",
        }
        with open(rd / "result.json", "w") as f:
            json.dump(result_data, f, indent=2)
        return result_data
    finally:
        # Clean up container
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    # Read the normalized output
    normalized_output_path = rd / "normalized_output.txt"
    if normalized_output_path.exists():
        actual_text = normalized_output_path.read_text()
    else:
        actual_text = ""

    # Parse actual output lines (USR prefix already stripped in container script)
    actual_lines = []
    for line in actual_text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            actual_lines.append(stripped)

    # Load expected outputs
    expected_variants = load_expected_outputs(exam_dir)

    # Compare
    passed = compare_output(actual_lines, expected_variants)

    print(f"  -> Result: {'PASS ✓' if passed else 'FAIL ✗'}")
    if not passed:
        print(f"  -> Actual output:   {actual_lines}")
        if expected_variants:
            print(f"  -> Expected output: {expected_variants[0]}")

    # Save diff
    diff_text = ""
    diff_path = rd / "solution.diff"
    if diff_path.exists():
        diff_text = diff_path.read_text()

    # Read boot output
    boot_output = ""
    boot_path = rd / "boot_output.txt"
    if boot_path.exists():
        boot_output = boot_path.read_text()

    # Read agent output
    agent_output = ""
    agent_output_path = rd / "agent_output.log"
    if agent_output_path.exists():
        agent_output = agent_output_path.read_text()

    # Count turns from pi's JSON output
    turns = None
    if agent_output:
        turns = count_turns_from_jsonl(agent_output)

    result_data = {
        "passed": passed,
        "output": actual_lines,
        "expected": expected_variants[0] if expected_variants else [],
        "boot_output": boot_output,
        "agent_output": agent_output,
        "duration_seconds": round(duration_seconds, 2),
        "turns": turns,
        "max_turns": max_iterations,
        "diff": diff_text,
        "error": None,
    }

    with open(rd / "result.json", "w") as f:
        json.dump(result_data, f, indent=2)

    return result_data


def run_eval_dry_run(args):
    """Run evaluation pipeline without pi - for testing infrastructure."""
    model_name = "dry-run"

    exams = discover_exams(EXAMS_DIR)
    if not exams:
        print("ERROR: No exams found")
        sys.exit(1)

    if args.exam:
        exams = [e for e in exams if e.name == args.exam]
        if not exams:
            print(f"ERROR: Exam '{args.exam}' not found")
            sys.exit(1)

    print(f"Eval dry-run mode - skipping pi execution")
    print(f"Exams:  {[e.name for e in exams]}")

    if not check_docker_image():
        print(f"ERROR: Docker image '{DOCKER_IMAGE}' does not exist.")
        print("Run 'python evaluate-pi.py --build' to build it.")
        sys.exit(1)

    results_summary = []
    for exam in exams:
        exam_name = exam.name

        print(f"\n{'=' * 60}")
        print(f"  Exam:  {exam_name} (dry-run)")
        print(f"{'=' * 60}")

        rd = result_dir(model_name, exam_name)
        rd.mkdir(parents=True, exist_ok=True)

        container_name = f"bench-pi-dry-run-{exam_name}".replace(".", "-")
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

        print("  -> Starting container...")

        inner_script = """#!/bin/bash
set -e

cd /work

unzip -o /tmp/es2.zip
cd /work/es2/nucleo

cat > .gitignore << 'GITIGNORE'
*
!*.cpp
!*.s
!*.h
!*.asm
!*.c
!.gitignore
!dry-run.cpp
!*/
GITIGNORE

git init
git config user.email "agent@bench.local"
git config user.name "Agent"
git add -A
git commit -m "initial state" --allow-empty

git add -A
git commit -m "before agent" --allow-empty

# Create dummy file to generate a diff
cat > dry-run.cpp << 'DRYRUN'
// This is a dry-run placeholder file
// Created to test git diff functionality
int dry_run_marker = 42;
DRYRUN

echo "=== DRY-RUN: Skipping pi execution ==="

git diff > /tmp/solution.diff
git add -A
git diff --cached >> /tmp/solution.diff

export AUTOCORR=1
make clean 2>&1 || true
make 2>&1 || echo "MAKE_FAILED"
timeout 10s boot > /tmp/boot_output.txt 2>&1 || true

grep "USR" /tmp/boot_output.txt | sed -E 's/USR\\s+[0-9]+\\s+/USR /' | sed 's/^USR //' > /tmp/normalized_output.txt 2>/dev/null || true

# Create artifact zip of es2 folder
cd /work
zip -r /tmp/es2_artifact.zip es2 2>/dev/null || true

echo "===DONE==="
"""

        script_path = rd / "run_inner.sh"
        with open(script_path, "w") as f:
            f.write(inner_script)

        try:
            print("  -> Running dry-run in container...")
            proc = subprocess.run(
                [
                    "docker",
                    "run",
                    "--name",
                    container_name,
                    "-e",
                    "AUTOCORR=1",
                    "-v",
                    f"{(exam / 'es2.zip').resolve()}:/tmp/es2.zip:ro",
                    "-v",
                    f"{script_path.resolve()}:/tmp/run_inner.sh:ro",
                    DOCKER_IMAGE,
                    "bash",
                    "/tmp/run_inner.sh",
                ],
                text=True,
                timeout=120,
            )

            for artifact in [
                "solution.diff",
                "boot_output.txt",
                "normalized_output.txt",
                "es2_artifact.zip",
            ]:
                subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{container_name}:/tmp/{artifact}",
                        str(rd / artifact),
                    ],
                    capture_output=True,
                )

        except subprocess.TimeoutExpired:
            print(f"  -> TIMEOUT")
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            results_summary.append(
                {"model": model_name, "exam": exam_name, "passed": False}
            )
            continue
        finally:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

        normalized_output_path = rd / "normalized_output.txt"
        actual_text = (
            normalized_output_path.read_text()
            if normalized_output_path.exists()
            else ""
        )
        actual_lines = [
            l.strip() for l in actual_text.strip().splitlines() if l.strip()
        ]

        expected_variants = load_expected_outputs(exam)
        passed = compare_output(actual_lines, expected_variants)

        print(f"  -> Result: {'PASS ✓' if passed else 'FAIL ✗'}")
        if not passed:
            print(f"  -> Actual output:   {actual_lines}")
            if expected_variants:
                print(f"  -> Expected output: {expected_variants[0]}")

        diff_path = rd / "solution.diff"
        diff_text = diff_path.read_text() if diff_path.exists() else ""

        result_data = {
            "passed": passed,
            "output": actual_lines,
            "expected": expected_variants[0] if expected_variants else [],
            "diff": diff_text,
            "error": None,
        }
        with open(rd / "result.json", "w") as f:
            json.dump(result_data, f, indent=2)

        results_summary.append(
            {"model": model_name, "exam": exam_name, "passed": passed}
        )

    print(f"\n{'=' * 60}")
    print("SUMMARY (dry-run)")
    print(f"{'=' * 60}")
    for r in results_summary:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{r['model']:<30} {r['exam']:<20} {status}")

    print("\n✓ Eval dry-run complete!")


def main():
    global RESULTS_DIR, EXAMS_DIR, MODELS_CONFIG

    parser = argparse.ArgumentParser(
        description="calcolatori-bench: benchmark LLM agents on CE exams (pi harness)"
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=MODELS_CONFIG,
        help="Path to models TOML config (default: models.toml)",
    )
    parser.add_argument(
        "--exams",
        type=Path,
        default=EXAMS_DIR,
        help="Path to exams directory (default: exams/)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=RESULTS_DIR,
        help="Path to results directory (default: results/pi/)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30 * 60,
        help="Timeout per agent run in seconds (default: 30 minutes)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=MAX_ITERATIONS,
        help="Maximum number of agent iterations (default: 50)",
    )
    parser.add_argument(
        "--build", action="store_true", help="Build the Docker image before running"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached results and re-run everything",
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Run only this model (by name)"
    )
    parser.add_argument(
        "--exam", type=str, default=None, help="Run only this exam (by directory name)"
    )
    parser.add_argument(
        "--model-dry-run",
        action="store_true",
        help="Test pi config for a model without running evaluation (requires --model)",
    )
    parser.add_argument(
        "--eval-dry-run",
        action="store_true",
        help="Run evaluation pipeline without executing pi (creates dummy dry-run.cpp for diff)",
    )
    args = parser.parse_args()

    RESULTS_DIR = args.results
    EXAMS_DIR = args.exams
    MODELS_CONFIG = args.models

    # Load models
    models = load_models(MODELS_CONFIG)
    if not models:
        print("ERROR: No models found in config")
        sys.exit(1)

    # Pre-validate all models and load API keys
    model_api_keys = {}
    for model in models:
        try:
            api_key = load_api_key(model)
            model_api_keys[model["name"]] = api_key
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    # Filter model if specified
    if args.model:
        models = [m for m in models if m["name"] == args.model]
        if not models:
            print(f"ERROR: Model '{args.model}' not found in config")
            sys.exit(1)

    # Model dry-run mode: test pi config and exit
    if args.model_dry_run:
        if not args.model:
            print("ERROR: --model-dry-run requires --model to be specified")
            sys.exit(1)

        model = models[0]
        model_name = model["name"]
        api_key = model_api_keys[model_name]
        model_id = model["model_id"]
        base_url = model["base_url"]

        print(f"Dry-run for model: {model_name}")
        print(f"Model ID: {model_id}")
        print(f"Base URL: {base_url}")
        print(f"API key: {'*' * 8}{api_key[-4:]}" if len(api_key) > 4 else "API key too short")
        print()

        pi_models_json = generate_pi_models_json(model, api_key)

        print("models.json:")
        print(json.dumps(pi_models_json, indent=2))
        print()

        print("Testing pi connection...")
        test_prompt = "Reply with just: OK"

        # Write models.json to temp file for testing
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(pi_models_json, f)
            temp_models_path = f.name

        try:
            # Set up pi config directory
            import shutil

            temp_home = tempfile.mkdtemp()
            pi_config_dir = Path(temp_home) / ".pi" / "agent"
            pi_config_dir.mkdir(parents=True)
            shutil.copy(temp_models_path, pi_config_dir / "models.json")

            env = os.environ.copy()
            env["HOME"] = temp_home

            result = subprocess.run(
                [
                    "pi",
                    "--mode",
                    "json",
                    "--no-session",
                    "--no-context-files",
                    "--model",
                    f"custom/{model_id}",
                    test_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            print("STDOUT:", result.stdout[:500] if result.stdout else "(empty)")
            if result.stderr:
                print("STDERR:", result.stderr[:500])
            print("Return code:", result.returncode)

            if result.returncode == 0:
                print("\n✓ Model dry-run successful!")
            else:
                print("\n✗ Model dry-run failed!")
                sys.exit(1)
        finally:
            os.unlink(temp_models_path)
            shutil.rmtree(temp_home, ignore_errors=True)
        return

    # Eval dry-run mode: run pipeline without pi
    if args.eval_dry_run:
        run_eval_dry_run(args)
        return

    # Discover exams
    exams = discover_exams(EXAMS_DIR)
    if not exams:
        print("ERROR: No exams found")
        sys.exit(1)

    # Filter exam if specified
    if args.exam:
        exams = [e for e in exams if e.name == args.exam]
        if not exams:
            print(f"ERROR: Exam '{args.exam}' not found")
            sys.exit(1)

    print(f"Models: {[m['name'] for m in models]}")
    print(f"Exams:  {[e.name for e in exams]}")
    print(f"Total combinations: {len(models) * len(exams)}")

    # Build image if requested
    if args.build:
        build_docker_image()
        return

    # Check if Docker image exists
    if not check_docker_image():
        print(f"ERROR: Docker image '{DOCKER_IMAGE}' does not exist.")
        print("Run 'python evaluate-pi.py --build' to build it.")
        sys.exit(1)

    # Run evaluations
    results_summary = []
    for model in models:
        model_name = model["name"]
        display_name = model.get("display_name", model_name)
        model_dir = RESULTS_DIR / sanitize_path(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_info_path = model_dir / "model_info.json"
        if not model_info_path.exists():
            with open(model_info_path, "w") as f:
                json.dump({"display_name": display_name}, f, indent=2)

        for exam in exams:
            exam_name = exam.name

            # Check cache
            if not args.no_cache and is_cached(model_name, exam_name):
                print(f"\n  [CACHED] {model_name} x {exam_name}")
                rd = result_dir(model_name, exam_name)
                with open(rd / "result.json") as f:
                    cached = json.load(f)
                results_summary.append(
                    {
                        "model": model_name,
                        "exam": exam_name,
                        "passed": cached["passed"],
                        "cached": True,
                    }
                )
                continue

            result = run_exam(
                model,
                exam,
                model_api_keys[model_name],
                timeout_agent=args.timeout,
                max_iterations=args.max_iterations,
            )
            results_summary.append(
                {
                    "model": model_name,
                    "exam": exam_name,
                    "passed": result["passed"],
                    "cached": False,
                }
            )

    # Print summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Model':<30} {'Exam':<20} {'Result':<10}")
    print(f"{'-' * 30} {'-' * 20} {'-' * 10}")
    for r in results_summary:
        status = "PASS" if r["passed"] else "FAIL"
        cached = " (cached)" if r["cached"] else ""
        print(f"{r['model']:<30} {r['exam']:<20} {status}{cached}")

    # Per-model scores
    print(f"\nScores:")
    model_names = sorted(set(r["model"] for r in results_summary))
    for mname in model_names:
        model_results = [r for r in results_summary if r["model"] == mname]
        passed = sum(1 for r in model_results if r["passed"])
        total = len(model_results)
        print(f"  {mname}: {passed}/{total}")


if __name__ == "__main__":
    main()
