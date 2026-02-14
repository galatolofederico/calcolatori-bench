# 🍝 calcolatori-bench 🏋️

**An esoteric benchmark for Agentic LLMs based on the University of Pisa's [Calcolatori Elettronici](https://calcolatori.iet.unipi.it/) course.**

`calcolatori-bench` is a rigorous benchmark designed to break LLMs by throwing them into the deep end of the **University of Pisa's "Calcolatori Elettronici"** course.

It tests an agent's ability to navigate an obscure, highly technical, and strictly constrained mixed-language environment (C++ and x86_64 Assembly) with **virtually zero training data contamination**.

---

### 🇮🇹 The Challenge: The "Italian Job"

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

We use a containerized sandbox to ensure fair, safe, and reproducible evaluation. The agent is powered by **OpenCode**.

**The Gauntlet:**

1. **📦 Sandbox Spawning:** A Docker container spins up with the build environment (GCC, Make, QEMU/Boot tools) and `opencode` pre-installed.
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
* `glm-coding` (Z.AI GLM Coding Plan)
* `anthropic`
* `openai`

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

### 📊 Results & Caching

Testing takes time and tokens. We respect both.

* **Caching:** Results are cached in the `results/` folder. If you rerun the script, it skips model/exam combinations that have already been evaluated.
* **Score:** The final metric is raw and brutal: **Passed Exams / Total Attempts**.