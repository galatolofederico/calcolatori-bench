#!/usr/bin/env python3
"""
calcolatori-bench: LLM benchmark for the Calcolatori Elettronici course.

Evaluates LLM agents (via opencode) on exam exercise 2 (nucleo kernel exercises).
For each model x exam combination, spawns a Docker container, runs the agent,
then verifies the output.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

DOCKER_IMAGE = "calcolatori-bench"
RESULTS_DIR = Path("results")
EXAMS_DIR = Path("exams")
MODELS_CONFIG = Path("models.toml")

PROVIDER_CONFIG = {
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "provider_id": "openrouter",
    },
    "zai-coding-plan": {
        "env_var": "GLM_CODING_API_KEY",
        "provider_id": "zai-coding-plan",
    },
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "provider_id": "anthropic",
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "provider_id": "openai",
    },
}


def load_models(config_path: Path) -> list[dict]:
    """Load model configurations from TOML file."""
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    return config.get("model", [])


def get_provider_config(provider_name: str) -> dict:
    """Get provider configuration by name."""
    if provider_name not in PROVIDER_CONFIG:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available: {list(PROVIDER_CONFIG.keys())}"
        )
    return PROVIDER_CONFIG[provider_name]


def load_api_key(provider_name: str) -> str:
    """Load API key for a provider from environment or .env file."""
    provider_config = get_provider_config(provider_name)
    env_var = provider_config["env_var"]

    api_key = os.environ.get(env_var, "")

    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{env_var}="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    return api_key


def discover_exams(exams_dir: Path) -> list[Path]:
    """Discover all exam directories that contain es2.zip and testo.pdf."""
    exams = []
    for d in sorted(exams_dir.iterdir()):
        if d.is_dir() and (d / "es2.zip").exists() and (d / "testo.pdf").exists():
            exams.append(d)
    return exams


def result_key(model_name: str, exam_name: str) -> str:
    """Generate a unique key for a model × exam combination."""
    return f"{model_name}/{exam_name}"


def result_dir(model_name: str, exam_name: str) -> Path:
    """Get the results directory for a model × exam combination."""
    return RESULTS_DIR / model_name / exam_name


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


def generate_opencode_config(model: dict, api_key: str) -> dict:
    """Generate an opencode.json configuration for the given model."""
    provider_name = model["provider"]
    provider_config = get_provider_config(provider_name)
    provider_id = provider_config["provider_id"]
    model_id = model["model_id"]

    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {provider_id: {"models": {model_id: {}}}},
    }
    return config


def generate_auth_json(model: dict, api_key: str) -> dict:
    """Generate the auth.json for opencode credentials."""
    provider_name = model["provider"]
    provider_config = get_provider_config(provider_name)
    provider_id = provider_config["provider_id"]
    return {provider_id: {"type": "api", "key": api_key}}


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
    """Build the Docker image from container/Dockerfile."""
    print("==> Building Docker image...")
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            DOCKER_IMAGE,
            "-f",
            "container/Dockerfile",
            "container/",
        ],
        capture_output=False,
        timeout=600,
    )
    if result.returncode != 0:
        print("ERROR: Failed to build Docker image")
        sys.exit(1)
    print("==> Docker image built successfully")


def run_exam(
    model: dict, exam_dir: Path, api_key: str, timeout_agent: int = 300
) -> dict:
    """Run a single model × exam evaluation.

    Returns a dict with keys: passed, output, expected, diff, error
    """
    model_name = model["name"]
    exam_name = exam_dir.name
    provider_name = model["provider"]
    provider_config = get_provider_config(provider_name)
    env_var = provider_config["env_var"]
    provider_id = provider_config["provider_id"]

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

    # Generate opencode config
    opencode_config = generate_opencode_config(model, api_key)
    auth_config = generate_auth_json(model, api_key)

    # Write config files to temp location
    config_path = rd / "opencode.json"
    auth_path = rd / "auth.json"
    with open(config_path, "w") as f:
        json.dump(opencode_config, f, indent=2)
    with open(auth_path, "w") as f:
        json.dump(auth_config, f, indent=2)

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

Remember: ALWAYS use `timeout 10s boot` instead of `boot` - this is critical to avoid hanging!
"""

    # Create a container and run the evaluation
    container_name = f"bench-{model_name}-{exam_name}".replace("/", "-").replace(
        ".", "-"
    )

    # Clean up any existing container with same name
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    print("  -> Starting container...")

    # We need to:
    # 1. Copy es2.zip into the container
    # 2. Extract it
    # 3. Init git repo
    # 4. Set up opencode config
    # 5. Run opencode
    # 6. Collect diff + output

    # Build a script to run inside the container
    # Escape the prompt for shell
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

# Set up opencode auth
mkdir -p ~/.local/share/opencode
cp /tmp/auth.json ~/.local/share/opencode/auth.json

# Copy opencode config
cp /tmp/opencode.json /work/es2/nucleo/opencode.json

# Run opencode agent in non-interactive mode
export {env_var}="${env_var}"
cd /work/es2/nucleo

opencode run '{prompt_escaped}' --model '{provider_id}/{model["model_id"]}' 2>&1 | tee /tmp/agent_output.log || true

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

echo "===DONE==="
"""

    script_path = rd / "run_inner.sh"
    with open(script_path, "w") as f:
        f.write(inner_script)

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
                f"{env_var}={api_key}",
                "-e",
                "AUTOCORR=1",
                "-v",
                f"{(exam_dir / 'es2.zip').resolve()}:/tmp/es2.zip:ro",
                "-v",
                f"{config_path.resolve()}:/tmp/opencode.json:ro",
                "-v",
                f"{auth_path.resolve()}:/tmp/auth.json:ro",
                "-v",
                f"{script_path.resolve()}:/tmp/run_inner.sh:ro",
                DOCKER_IMAGE,
                "bash",
                "/tmp/run_inner.sh",
            ],
            text=True,
            timeout=timeout_agent,
        )

        agent_stdout = ""
        agent_stderr = ""

        # Copy artifacts out of the container
        for artifact in [
            "solution.diff",
            "boot_output.txt",
            "normalized_output.txt",
            "agent_output.log",
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
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        result_data = {
            "passed": False,
            "output": "",
            "expected": "",
            "diff": "",
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

    result_data = {
        "passed": passed,
        "output": actual_lines,
        "expected": expected_variants[0] if expected_variants else [],
        "boot_output": boot_output,
        "diff": diff_text,
        "error": None,
    }

    with open(rd / "result.json", "w") as f:
        json.dump(result_data, f, indent=2)

    return result_data


def main():
    global RESULTS_DIR, EXAMS_DIR, MODELS_CONFIG

    parser = argparse.ArgumentParser(
        description="calcolatori-bench: benchmark LLM agents on CE exams"
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
        help="Path to results directory (default: results/)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout per agent run in seconds (default: 600)",
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
        "--dry-run",
        action="store_true",
        help="Test opencode config for a model without running evaluation (requires --model)",
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

    # Pre-validate all providers and load API keys
    model_api_keys = {}
    for model in models:
        provider = model["provider"]
        try:
            api_key = load_api_key(provider)
            if not api_key:
                env_var = get_provider_config(provider)["env_var"]
                print(f"ERROR: {env_var} not found in .env or environment")
                sys.exit(1)
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

    # Dry-run mode: test opencode config and exit
    if args.dry_run:
        if not args.model:
            print("ERROR: --dry-run requires --model to be specified")
            sys.exit(1)

        model = models[0]
        model_name = model["name"]
        provider = model["provider"]
        provider_config = get_provider_config(provider)
        api_key = model_api_keys[model_name]

        print(f"Dry-run for model: {model_name}")
        print(f"Provider: {provider}")
        print(f"Provider ID: {provider_config['provider_id']}")
        print(f"Env var: {provider_config['env_var']}")
        print(
            f"API key: {'*' * 8}{api_key[-4:]}"
            if len(api_key) > 4
            else "API key too short"
        )
        print()

        opencode_config = generate_opencode_config(model, api_key)
        auth_config = generate_auth_json(model, api_key)

        print("opencode.json:")
        print(json.dumps(opencode_config, indent=2))
        print()
        print("auth.json:")
        print(json.dumps(auth_config, indent=2))
        print()

        print("Testing opencode connection...")
        test_prompt = "Reply with just: OK"
        result = subprocess.run(
            [
                "opencode",
                "run",
                test_prompt,
                "--model",
                f"{provider_config['provider_id']}/{model['model_id']}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, provider_config["env_var"]: api_key},
        )
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print("Return code:", result.returncode)

        if result.returncode == 0:
            print("\n✓ Dry-run successful!")
        else:
            print("\n✗ Dry-run failed!")
            sys.exit(1)
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

    # Check if Docker image exists
    if not check_docker_image():
        print(f"ERROR: Docker image '{DOCKER_IMAGE}' does not exist.")
        print("Run 'python evaluate.py --build' to build it.")
        sys.exit(1)

    # Run evaluations
    results_summary = []
    for model in models:
        for exam in exams:
            model_name = model["name"]
            exam_name = exam.name

            # Check cache
            if not args.no_cache and is_cached(model_name, exam_name):
                print(f"\n  [CACHED] {model_name} × {exam_name}")
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
                model, exam, model_api_keys[model_name], timeout_agent=args.timeout
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
