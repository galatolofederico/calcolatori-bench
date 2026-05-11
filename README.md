# 🍝 calcolatori-bench 🏋️

**An esoteric benchmark for Agentic LLMs based on the University of Pisa's [Calcolatori Elettronici](https://calcolatori.iet.unipi.it/) course.**

`calcolatori-bench` is a rigorous benchmark designed to break LLMs by throwing them into the deep end of the **University of Pisa's "Calcolatori Elettronici"** course.

It tests an agent's ability to navigate an obscure, highly technical, and strictly constrained mixed-language environment (C++ and x86_64 Assembly) with **virtually zero training data contamination**.

> **[📊 Check the Leaderboard](https://galatolofederico.github.io/calcolatori-bench/)**

---

### 🇮🇹 The Challenge

Why is this benchmark harder than your average Python coding test? Because it requires a unique combination of low-level systems knowledge and linguistic flexibility.

#### 1. Truly Esoteric & Niche

The exams run on a custom, educational OS/kernel environment designed specifically for the course.

* **No StackOverflow Help:** Unlike React components or generic Python scripts, there are almost no public GitHub repos or forum threads covering this specific kernel architecture.
* **Zero Contamination:** The model cannot rely on memorization. It has to actually *think*.

#### 2. The Language Barrier (It's in Italian)

To add to the chaos, the entire environment is a linguistic maze:

* **Source Code:** A mix of English keywords and Italian variable/function names.
* **Documentation:** All comments and docs in **Italian**.
* **The Exam Text:** The problem description is in **Italian**.

The agent must be a multilingual systems engineer: translating intent from Italian instructions into x86_64 Assembly and C++, all while respecting the strict syntax of a custom kernel.

#### 3. High-Stakes Complexity

This isn't about printing "Hello World." To pass, an agent must manipulate hardware interrupts, manage low-level memory, and interface with specific kernel structures. It then has to compile and **boot a virtual machine** to prove it works.

---

### ⚙️ Architecture & Workflow

We use a containerized sandbox to ensure fair, safe, and reproducible evaluation. The benchmark supports two agent harnesses, both accessible through a single entrypoint:

```bash
./evaluate.sh --harness <opencode|pi> [options...]
```

* **[OpenCode](https://github.com/opencode-ai/opencode)** — `./evaluate.sh --harness opencode`
* **[pi](https://pi.dev)** — `./evaluate.sh --harness pi`

**The Gauntlet:**

1. **📦 Sandbox Spawning:** A Docker container spins up with the build environment (GCC, Make, QEMU/Boot tools) and the chosen agent harness pre-installed.
2. **💉 Context Injection:** The specific exam text (in Italian) is extracted and fed to the agent.
3. **🤖 Agent Execution:** The agent is dropped into the kernel's source code and told to:
 - Read the PDF documentation.
 - Modify the source code (C++/ASM) to solve the exercise.
 - Run `make` to compile.
 - Boot and test the kernel in QEMU.
4. **📸 Result Capture:** Once the agent finishes, we capture the `git diff` of the solution.
5. **⚖️ The Verdict:** The host system recompiles the code clean and executes the kernel. The output is filtered, normalized, and compared against the ground truth.
6. **✅ Scoring:** Exact match required. Pass or Fail. No partial credit in kernel space.

---

### 🛠️ Configuration

The benchmark is controlled via a simple TOML configuration file. You can pit different models against each other easily.

**Supported Providers:**

* `openrouter`
* `zai-coding-plan` (Z.AI GLM Coding Plan)
* `anthropic`
* `openai`
* `custom` (for self-hosted or custom endpoints)

**`models.toml` example:**

```toml
[[model]]
name = "claude-4.5-sonnet"
provider = "anthropic"
model_id = "claude-4.5-sonnet"

[[model]]
name = "grok-nitro"
provider = "openrouter"
model_id = "x-ai/grok-code-fast-1"
shortcut = "nitro"  # See shortcuts below

[[model]]
name = "glm-4.7"
provider = "zai-coding-plan"
model_id = "glm-4.7"
```

**⚡ OpenRouter Shortcuts:**

* `shortcut = "nitro"`: Prioritizes throughput
* `shortcut = "floor"`: Prioritizes lowest price
* `shortcut = "free"`: Routes to free tier providers

---

### 🔧 Custom Models

You can configure self-hosted models or custom OpenAI-compatible endpoints using the `custom` provider:

```toml
[[model]]
name = "my-local-llama"
provider = "custom"
model_id = "llama-3.1-70b"
base_url = "http://localhost:8000/v1"
api_key = "${MY_LOCAL_API_KEY}"  # Supports env var interpolation

# Optional: define model capabilities
[model.modalities]
input = ["text", "image"]
output = ["text"]
```

**Custom Model Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Human-readable identifier for results |
| `provider` | Yes | Must be `"custom"` |
| `model_id` | Yes | Model identifier sent to the API |
| `base_url` | Yes | Base URL for the OpenAI-compatible API |
| `api_key` | Yes | API key (supports `${ENV_VAR}` interpolation) |
| `modalities` | No | Model capabilities (text, image input/output) |

**Environment Variable Interpolation:**

All string values in `models.toml` support environment variable interpolation using `${VAR_NAME}` syntax:

```toml
[[model]]
name = "production-model"
provider = "openrouter"
model_id = "anthropic/claude-3.5-sonnet"
# API key loaded from OPENROUTER_API_KEY env var

[[model]]
name = "custom-endpoint"
provider = "custom"
model_id = "my-model"
base_url = "${CUSTOM_BASE_URL}"
api_key = "${CUSTOM_API_KEY}"
```

---

### 🚀 Running the Benchmark

#### Prerequisites

1. **Docker** - Required for sandboxed evaluation
2. **Python 3.11+** - For the evaluation script
3. **pdftotext** - For extracting exam text (usually via `poppler-utils`)

#### Setup

1. **Build the Docker image** (choose the harness you plan to use):

```bash
# OpenCode harness
./evaluate.sh --harness opencode --build

# Pi harness
./evaluate.sh --harness pi --build
```

2. **Configure API keys:**

Create a `.env` file in the project root:

```bash
# For OpenRouter models
OPENROUTER_API_KEY=sk-or-v1-...

# For Z.AI GLM Coding Plan
GLM_CODING_API_KEY=...

# For Anthropic models
ANTHROPIC_API_KEY=...

# For OpenAI models
OPENAI_API_KEY=...

# For custom models, define your own
CUSTOM_API_KEY=...
```

3. **Configure models:**

Create `models.toml` to specify which models to benchmark (see examples above).

#### Running Evaluations

All evaluation commands go through `./evaluate.sh` with the `--harness` flag. All remaining arguments are forwarded to the underlying Python script.

```bash
# Run all model × exam combinations (OpenCode)
./evaluate.sh --harness opencode

# Run all model × exam combinations (pi)
./evaluate.sh --harness pi

# Run a specific model
./evaluate.sh --harness opencode --model "glm-4.7"
./evaluate.sh --harness pi --model "Qwen/Qwen3.5-27B:f16"

# Run a specific exam
./evaluate.sh --harness opencode --exam "2023-01-11_08"
./evaluate.sh --harness pi --exam "2023-01-11_08"

# Run a specific model × exam combination
./evaluate.sh --harness opencode --model "glm-4.7" --exam "2023-01-11_08"
./evaluate.sh --harness pi --model "Qwen/Qwen3.5-27B:f16" --exam "2023-01-11_08"

# Test model configuration without running full evaluation
./evaluate.sh --harness opencode --model "my-model" --model-dry-run
./evaluate.sh --harness pi --model "my-model" --model-dry-run

# Ignore cached results and re-run everything
./evaluate.sh --harness opencode --no-cache
./evaluate.sh --harness pi --no-cache

# Adjust timeout (default: 30 minutes per agent run)
./evaluate.sh --harness opencode --timeout 3600
./evaluate.sh --harness pi --timeout 3600

# Adjust max agent turns (OpenCode, default: 100)
./evaluate.sh --harness opencode --max-turns 50

# Adjust max agent iterations (pi, default: 50)
./evaluate.sh --harness pi --max-iterations 30
```

#### Dry-run Mode

Test the infrastructure without executing the agent:

```bash
./evaluate.sh --harness opencode --eval-dry-run
./evaluate.sh --harness pi --eval-dry-run
```

### 📊 Results & Caching

Testing takes time and tokens. We respect both.

* **Caching:** Results are cached per-harness in `results/<harness>/` (e.g., `results/opencode/`, `results/pi/`). If you rerun the script, it skips model/exam combinations that have already been evaluated.
* **Score:** The final metric is raw and brutal: **Passed Exams / Total Attempts**.
* **Leaderboard:** Run `python build_results.py` to generate `site/leaderboard_data.json` from all harness results. The static website at `site/` consumes this file.