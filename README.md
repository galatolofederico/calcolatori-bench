# calcolatori-bench

**An evaluation framework for Agentic LLMs based on the University of Pisa's "Calcolatori Elettronici" course.**

`calcolatori-bench` tests an agent's ability to navigate an obscure, highly technical, and strictly constrained mixed-language environment (C++ and x86_64 Assembly) with virtually zero training data contamination.

---

### 🏛️ The Challenge: Why "Calcolatori Elettronici"?

"Calcolatori Elettronici" is widely regarded as one of the **most difficult** courses in the **Computer Engineering** bachelor's degree at the **University of Pisa**.

* **Niche Codebase:** The exams run on a custom educational OS/kernel environment. The code is a complex interplay of C++ and x86_64 Assembly.
* **Low Contamination:** Unlike Python scripts or React components, there are almost no public GitHub repositories or StackOverflow threads covering this specific system. The only resources are the course PDFs.
* **High Complexity:** To pass, an agent cannot rely on memorization. It must understand low-level memory management, hardware interrupts, and specific kernel interfaces, then compile and boot a virtual machine to verify correctness.

### ⚙️ Architecture & Workflow

This benchmark uses a containerized sandbox to ensure fair and safe evaluation. We utilize **OpenCode** as the agent interface.

The evaluation pipeline for each Model-Exam pair proceeds as follows:

1. **Sandbox Spawning:** A Docker container is spun up with the specific build environment (GCC, Make, QEMU/Boot tools) and `opencode` installed.
2. **Context Injection:** The specific exam text is extracted and provided to the agent.
3. **Agent Execution:** The agent is initialized in a Git repository. It is instructed to:
    - Read the PDF.
    - Modify the source code to solve the exercise.
    - Run `make` to compile.
    - Run `timeout 10s boot` to test the kernel.
4. **Result Capture:** Once the agent terminates, the benchmark captures the `git diff` of the solution.
5. **Strict Verification:** The benchmark host recompiles the code clean and executes the kernel. The output is filtered and normalized
6. **Scoring:** The normalized output is compared against the ground truth. If they match exactly, the exam is **PASSED**.

### 🛠️ Configuration

The benchmark is driven by a TOML configuration file allowing for easy testing of different models and parameters.

**`models.toml` example:**

```toml
[claude-3-5-sonnet]
provider = "openrouter"
model_name = "anthropic/claude-3.5-sonnet"
temperature = 0.7

[[model]]
name = "grok-code-fast-1"
provider = "openrouter"
model_id = "x-ai/grok-code-fast-1"
```

### 📊 Results Structure

To save costs and time, the system implements a caching mechanism. Results are stored in the `results/` folder. Rerunning the script will skip model/exam combinations that have already been evaluated.

* **Score:** The final metric is the raw count of passed exams vs total exams attempted.