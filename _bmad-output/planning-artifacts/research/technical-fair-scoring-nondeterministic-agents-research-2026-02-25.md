---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'Fair Scoring and Evaluation Methodologies for Non-Deterministic AI Agents'
research_goals: 'Design a scoring framework for benchmarking non-deterministic AI agents on crisis_bench; explore 0-100% scoring, success rates, multi-run aggregation, and leaderboard-friendly metrics'
user_name: 'Mauk'
date: '2026-02-25'
web_research_enabled: true
source_verification: true
---

# Fair Scoring of Non-Deterministic AI Agents: Comprehensive Technical Research for crisis_bench

**Date:** 2026-02-25
**Author:** Mauk
**Research Type:** Technical

---

## Executive Summary

AI agents are inherently non-deterministic — the same agent given the same scenario can produce different actions across runs, with documented accuracy fluctuations of up to 10% even under "deterministic" configurations. This makes fair, reproducible scoring a first-class engineering challenge for any benchmark, and crisis_bench is no exception.

This research surveyed the state of the art across 20+ benchmarks, frameworks, and academic sources to answer: **how should crisis_bench score agents fairly given this non-determinism?** The key finding is that the field has converged on a clear set of best practices, but crisis_bench has a unique requirement — it needs to **observe and catalogue what agents do** (contact police, call a spouse, gather information) without prescribing the "right" answer upfront. This pushes the design toward an **exploratory/observational scoring model** inspired by Anthropic's Bloom framework, layered on top of standard multi-run statistical aggregation.

**Key Findings:**
- **Run multiple times**: K=5-10 runs per scenario per agent is the practical sweet spot. Always report 95% confidence intervals alongside scores.
- **pass@k and pass^k**: The two dominant metrics. pass@k measures capability ("can it ever succeed?"), pass^k measures reliability ("does it always succeed?"). Even top agents see 60% drops from pass@1 to pass@8.
- **Action logging is foundational**: Capture every tool call, argument, and outcome. Build the action taxonomy from observed behavior, not from assumptions.
- **Code-based grading where possible**: Deterministic grading (did the agent call function X?) is faster, cheaper, and more reliable than LLM-as-judge. Use LLM-as-judge only for dimensions that require it.
- **Aggregate in layers**: Per-run score → per-scenario score (mean across K runs + CI) → overall agent score (mean across scenarios). Keep it simple with equal weighting.

**Recommended Approach for crisis_bench:**
1. Log all agent actions per run (discovery-first, no prescribed "right" answers)
2. Build action taxonomy from observed behaviors across agents
3. Score action presence/absence per run (code-based, deterministic)
4. Run K=5-10 epochs per scenario, reduce with mean + CI
5. Present leaderboard with overall score + action frequency breakdowns + confidence intervals

---

## Table of Contents

1. [Technical Research Scope Confirmation](#technical-research-scope-confirmation)
2. [Technology Stack Analysis](#technology-stack-analysis) — Core metrics, formulas, statistical methods, grading approaches, reference benchmarks
3. [Integration Patterns Analysis](#integration-patterns-analysis) — Pipeline architecture, data formats, grading patterns, CI/CD, frameworks
4. [Architectural Patterns and Design](#architectural-patterns-and-design) — Scoring patterns, multi-run design, aggregation layers, reproducibility, reporting standards
5. [Implementation Approaches](#implementation-approaches-and-technology-adoption) — Action logging, Bloom-style scoring, cost management, pipeline architecture, risk assessment
6. [Technical Research Recommendations](#technical-research-recommendations) — Recommended framework, implementation roadmap, technology stack
7. [Research Synthesis](#research-synthesis) — Strategic recommendations, future outlook, source documentation

---

## Technical Research Scope Confirmation

**Research Topic:** Fair Scoring and Evaluation Methodologies for Non-Deterministic AI Agents
**Research Goals:** Design a scoring framework for benchmarking non-deterministic AI agents on crisis_bench; explore 0-100% scoring, success rates, multi-run aggregation, and leaderboard-friendly metrics

**Technical Research Scope:**

- Scoring Architecture — How existing benchmarks score non-deterministic outputs (pass@k, mean scores, percentile-based)
- Multi-Run Aggregation — Statistical methods for combining results across repeated runs
- Success Rate Metrics — Binary pass/fail rates, partial credit scoring, rubric-based grading
- Normalization & Comparability — Leaderboard-friendly, comparable scores across agents and scenarios
- Practical Implementation — Concrete scoring pipelines, run count tradeoffs, cost vs. statistical power

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-02-25

## Technology Stack Analysis

### Core Scoring Metrics & Formulas

The field has converged on several key metrics for scoring non-deterministic agents:

**pass@k — "At least one success in k attempts"**
Measures the probability that at least one of k independently sampled solutions is correct. The theoretical formula is `pass@k = 1 - (1 - p)^k` where p is the true success probability. However, the naive formula is biased (assumes sampling with replacement). The unbiased estimator from Chen et al. (2021) is:

`pass@k = 1 - C(n-c, k) / C(n, k)`

Where n = total samples generated, c = number of correct samples. When k=1, this simplifies to `pass@1 = c/n` — simply the empirical success rate. This is the most widely adopted metric: BigCodeBench ranks models by calibrated Pass@1 using greedy decoding. SWE-bench uses resolved count and fraction (effectively pass@1).
_Source: [Chen et al. Codex Paper](https://arxiv.org/pdf/2107.03374), [Pass@k Unbiased Estimator](https://leehanchung.github.io/blogs/2025/09/08/pass-at-k/), [BigCodeBench Leaderboard](https://bigcode-bench.github.io/)_

**pass^k — "Reliable success across all k attempts"**
Introduced by Sierra's τ-bench, this metric measures whether an agent can successfully complete the same task multiple times. It captures reliability — the probability that ALL k trials succeed. Even GPT-4o with >60% pass@1 drops to <25% on pass^8, a staggering 60% drop. Anthropic's model cards now include pass^k to measure consistency. pass@k and pass^k diverge as trials increase: pass@k approaches 100% while pass^k declines.
_Source: [τ-Bench (Sierra)](https://sierra.ai/blog/benchmarking-ai-agents), [τ-bench Paper](https://arxiv.org/abs/2406.12045)_

**Success Rate (SR)**
The simplest metric: fraction of episodes in which the agent fully completes the task. Equivalent to pass@1 when computed over a single run per scenario, or averaged across runs. Many benchmarks break tasks into milestones for partial credit.
_Source: [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

**Partial Credit / Rubric-Based Scoring**
For multi-component tasks, scoring "the continuum of success" with partial credit rather than binary pass/fail. Anthropic recommends designing rubrics where "two domain experts would independently reach the same pass/fail verdict." Grade what the agent produced, not the path it took.
_Source: [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

### Statistical Methods for Multi-Run Evaluation

**Confidence Intervals & Standard Error**
Anthropic's statistical approach to model evals recommends reporting 95% confidence intervals: `CI = mean ± 1.96 × SEM`. The standard error of the mean captures uncertainty from sampling. Researchers should report SEM alongside eval scores. Cluster standard errors when questions are related.
_Source: [Anthropic Statistical Approach](https://www.anthropic.com/research/statistical-approach-to-model-evals)_

**Variance & Reproducibility**
Accuracy fluctuations of up to 10% across repeated identical inference runs have been documented, even with deterministic configurations enforced. Target coefficient of variation (CV = std/mean) < 0.05 for acceptable variance. With enough runs, averages converge to the true score.
_Source: [Statistical LLM Evaluations](https://medium.com/@sulbha.jindal/statistical-llm-evaluations-confidence-scoring-caa6c9d57656)_

**Significance Testing**
Use paired-differences t-tests rather than two-sample tests when comparing models. Frontier models show correlations between 0.3 and 0.7 on the same questions. Power analysis helps determine required sample sizes — e.g., for a 5% margin of error on a metric expected to be 80%, approximately 246 samples are needed.
_Source: [Anthropic Statistical Approach](https://www.anthropic.com/research/statistical-approach-to-model-evals)_

**Practical Run Count Guidance**
Anthropic recommends 20-50 simple tasks drawn from real failures for initial evals. The Inspect framework supports resampling via its `epochs` parameter. The community is converging on pass@10 as a practical sweet spot (aligns with human review capacity). pass@100 reveals capability frontiers but is computationally expensive.
_Source: [Opinions on Pass@K](https://runloop.ai/blog/i-have-opinions-on-pass-k-you-should-too), [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

### Grading Approaches & Tools

Three complementary grading strategies identified by Anthropic:

**Code-Based Grading** — String matching, regex, exact match, outcome verification. Fast and highly reliable. The best method when eval design allows it. Used by SWE-bench (patch resolves issue = pass), τ-bench (database state comparison), BigCodeBench (test case execution).
_Source: [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

**Model-Based Grading (LLM-as-Judge)** — Rubric-based scoring, natural language assertions, pairwise comparison, reference-based evaluation. Flexible and handles nuance but is itself non-deterministic, requiring calibration with human graders.
_Source: [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

**Stateful Evaluation** — Compares system/database state after task completion with expected outcome. Used by τ-bench to objectively measure decision-making without needing to evaluate conversational quality. Provides room for valid solution variations.
_Source: [τ-Bench (Sierra)](https://sierra.ai/blog/benchmarking-ai-agents)_

### Reference Benchmarks & Their Scoring Architectures

| Benchmark | Metric | Grading Method | Multi-Run? |
|-----------|--------|---------------|------------|
| **SWE-bench** | Resolved fraction (pass@1) | Code: patch resolves issue via test suite | Single run per submission |
| **τ-bench** | pass^k reliability | Stateful: DB state comparison | Multiple runs (k=1..8+) |
| **BigCodeBench** | Calibrated pass@1 | Code: test case execution (avg 5.6 tests/task, 99% branch coverage) | Single greedy decode |
| **HELM** | Multi-metric (accuracy, calibration, robustness, fairness) | Mixed code + model | Varies by metric |
| **Artificial Analysis** | Pass@1 aggregated across repeats | Code + model | Multiple repeats |
| **CLEAR Framework** | Composite (cost, latency, efficacy, assurance, reliability) | Mixed | pass@k for reliability dimension |

_Source: [SWE-bench](https://www.swebench.com/), [BigCodeBench](https://bigcode-bench.github.io/), [Artificial Analysis](https://artificialanalysis.ai/methodology/intelligence-benchmarking)_

### Aggregation & Normalization Approaches

**Per-scenario aggregation**: Mean or median across runs. Median is more robust to outliers (used for binary predictions by Artificial Analysis). Normalized median for multiple-choice. Averages for numeric/continuous scores.

**Cross-scenario aggregation**: Equally-weighted average of per-scenario scores is the simplest approach. Some benchmarks weight by difficulty or domain. CLEAR Framework uses weighted composite across multiple dimensions.

**Leaderboard presentation**: Most leaderboards present a single percentage (resolved rate, pass@1). Best practice is to also show confidence intervals or variance indicators.

_Source: [Artificial Analysis Methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking), [Benchmarking AI Agents: Stop Trusting Headline Scores](https://medium.com/alan/benchmarking-ai-agents-stop-trusting-headline-scores-start-measuring-trade-offs-0fdae3a418cf)_

### Adoption Trends

**From single-shot to multi-run**: The field is moving toward requiring multiple runs per scenario to account for non-determinism. pass^k (reliability) is gaining prominence alongside pass@1 (capability).

**From binary to partial credit**: Modern benchmarks break tasks into milestones/steps. End-point scores are combined with milestone scores for richer signal.

**From static to dynamic evals**: Static benchmarks are saturating. Live/dynamic benchmarks (LiveBench, SWE-bench Live) that update regularly are gaining traction.

**Composite scoring**: Single-metric leaderboards are being supplemented with multi-dimensional frameworks (CLEAR, HELM) that capture cost, latency, reliability alongside accuracy.

_Source: [Stanford AI Index 2025](https://hai.stanford.edu/ai-index/2025-ai-index-report/technical-performance), [LiveBench](https://livebench.ai/), [LLM Stats](https://llm-stats.com/)_

## Integration Patterns Analysis

### Evaluation Pipeline Architecture

The standard evaluation pipeline for agent benchmarks follows a consistent pattern across frameworks:

**Pipeline Components (in order):**
1. **Dataset / Task Definition** — Test cases with inputs (prompts/scenarios) and targets (expected outcomes or grading guidance)
2. **Solver / Agent Runtime** — Executes the agent against each task, capturing full traces of actions and outputs
3. **Scorer / Grader** — Evaluates agent output against targets using code-based, model-based, or stateful methods
4. **Reducer / Aggregator** — Combines per-sample scores into per-scenario and per-agent metrics (mean, median, pass@k)
5. **Logger / Reporter** — Produces structured evaluation logs with all metadata for reproducibility

The Inspect AI framework (UK AISI) cleanly embodies this: `Task = Dataset + Solver + Scorer`, evaluated against a model, producing an `EvalLog` with status, task details, solver plan, per-sample scores, aggregated results, and token usage.
_Source: [Inspect AI](https://inspect.aisi.org.uk/), [Inspect AI Review](https://neurlcreators.substack.com/p/inspect-ai-evaluation-framework-review)_

**Multi-Run Orchestration:**
Inspect supports `epochs` — repeating each sample N times with a configurable `reducer` function (defaults to "mean") to combine scores. This is the cleanest integration pattern for handling non-determinism: run K epochs, reduce per-sample, then aggregate across samples.
_Source: [Inspect AI Reference](https://inspect.aisi.org.uk/reference/inspect_ai.html)_

### Data Formats & Submission Schemas

**SWE-bench Submission Format:**
```json
{
  "instance_id": "repo__issue_number",
  "model_patch": "git diff content...",
  "model_name_or_path": "agent-name"
}
```
Submissions include per-issue results denoting pass/fail, plus aggregate scores (resolved count and fraction). Submitted via PR to the leaderboard repo with CI triggered for validation.
_Source: [SWE-bench Evaluation Guide](https://www.swebench.com/SWE-bench/guides/evaluation/)_

**Inspect AI EvalLog Format:**
Structured log per evaluation run containing: overall status, task/model details, solver plan, list of every sample (input, output, score), aggregated results, token usage stats, and error logs. This provides full reproducibility.
_Source: [Inspect AI](https://inspect.aisi.org.uk/)_

**Emerging Standard:**
Most frameworks converge on JSON/JSONL for results, with per-instance records containing: instance_id, agent output/trace, individual scores per grading dimension, and metadata (model, timestamp, cost). No single universal schema exists yet, but the pattern is consistent.
_Source: [Codabench](https://www.codabench.org/)_

### Grading Integration Patterns

**Pattern 1: Code-Based Deterministic Grading**
Used by SWE-bench (test suite passes), BigCodeBench (test case execution), and τ-bench (database state comparison). Agent patches are applied in Docker containers; the repository's test suite is run; pass = all tests pass. This is the gold standard for objectivity — no grader variance.
_Source: [SWE-bench Evaluation](https://www.swebench.com/SWE-bench/guides/evaluation/), [τ-Bench](https://sierra.ai/blog/benchmarking-ai-agents)_

**Pattern 2: LLM-as-Judge Rubric Grading**
For tasks where code-based grading isn't possible (open-ended responses, conversational quality). Integration pattern: input + agent output + rubric → judge LLM → score + reasoning. Key calibration practices:
- Calibrate against human-annotated examples before deployment
- Use binary evaluations when possible (more reliable than Likert scales)
- Lock rubrics into immutable specifications (Rulers framework) to prevent drift
- Run multiple judge passes and aggregate for stability
_Source: [LLM-as-a-Judge Guide (TDS)](https://towardsdatascience.com/llm-as-a-judge-a-practical-guide/), [Rulers Framework](https://arxiv.org/html/2601.08654), [GoDaddy Calibration](https://www.godaddy.com/resources/news/calibrating-scores-of-llm-as-a-judge)_

**Pattern 3: Stateful Evaluation**
Compares system state (database, file system, API state) after agent execution against expected end-state. Doesn't care about conversation path — only outcome. Allows valid solution variations. Used by τ-bench for customer service tasks.
_Source: [τ-Bench](https://sierra.ai/blog/benchmarking-ai-agents)_

**Pattern 4: Hybrid/Multi-Dimensional**
Combine grader outputs through weighted, binary (all must pass), or hybrid approaches. Grade each dimension with an isolated LLM-as-judge rather than one judge for all dimensions. Then combine dimension scores into composite.
_Source: [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

### Leaderboard Integration & CI/CD

**Submission → Scoring → Display Pipeline:**

| Platform | Submission Method | Scoring | Leaderboard |
|----------|------------------|---------|-------------|
| **SWE-bench** | PR to GitHub repo | CI runs Docker-based eval | Static site from results |
| **BigCodeBench** | PyPI eval framework + submission | Local eval, submit results | HuggingFace Space |
| **Codabench** | Zip archive upload | Server-side scoring program | Built-in web leaderboard |
| **LiveCodeBench** | PR with model generations folder | Automated review | GitHub Pages |
| **Frontier-CS** | Solution files via PR | Weekly CI job dispatches workers | Auto-updated |

**Key CI/CD Integration Patterns:**
- **Containerized evaluation**: Docker ensures reproducibility across platforms (SWE-bench, Inspect)
- **Automated validation**: CI checks schema, re-runs evaluations, validates output consistency before merging
- **Continuous scoring**: Weekly/continuous CI jobs discover new submissions and score them automatically
- **Concurrent execution**: Inspect supports `max_connections` for API concurrency and `max_subprocesses` for Docker container concurrency
_Source: [SWE-bench](https://www.swebench.com/), [Codabench](https://www.codabench.org/), [Frontier-CS](https://frontier-cs.org/blog/evaluation/)_

### Evaluation Frameworks & Platforms

| Framework | Focus | Multi-Run Support | Scoring | Open Source |
|-----------|-------|-------------------|---------|-------------|
| **Inspect AI** | General LLM/agent evals | Epochs + reducers | Code + model-based | Yes (UK AISI) |
| **Codabench** | Competition benchmarks | Configurable | Custom scoring programs | Yes |
| **EleutherAI Harness** | LLM benchmarks | Configurable | Task-specific | Yes |
| **Braintrust** | Production agent evals | Built-in | Multi-dimensional | Partial |
| **DeepEval** | LLM evaluation | Configurable | Metric library | Yes |
| **Promptfoo** | Prompt testing | Repeat counts | Code + LLM judge | Yes |

**For crisis_bench, the most relevant integration patterns are:**
- Inspect AI's epoch/reducer pattern for multi-run orchestration
- SWE-bench's containerized evaluation for reproducibility
- τ-bench's stateful evaluation for objective outcome grading
- Codabench's submission pipeline for leaderboard management

_Source: [Inspect AI](https://inspect.aisi.org.uk/), [Codabench](https://www.codabench.org/), [EleutherAI Harness](https://github.com/EleutherAI/lm-evaluation-harness), [Braintrust](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)_

## Architectural Patterns and Design

### Scoring Architecture Patterns

Three dominant architectural patterns for scoring non-deterministic agents have emerged:

**Pattern A: Binary Outcome + Success Rate**
The simplest architecture. Each scenario run produces a binary pass/fail. The agent's score per scenario = number of passes / number of runs. Leaderboard shows success rate as a percentage.
- _Used by_: SWE-bench (resolved or not), τ-bench (task completed or not)
- _Pros_: Simple, unambiguous, easy to understand on a leaderboard
- _Cons_: No partial credit — an agent that gets 90% of the way there scores the same as one that does nothing
- _Best for_: Tasks with clear, verifiable end-states

**Pattern B: Rubric-Based Partial Credit**
Each scenario has a multi-dimensional rubric. Per run, the agent receives a score per dimension (e.g., 0/1/2 or 0-100%). Dimension scores are combined (weighted average or sum) into a per-run score. Per-scenario score = mean of per-run scores across K runs.
- _Used by_: HELM (multi-metric), CLEAR Framework, ResearchRubrics
- _Emerging practice_: Ternary grading {Satisfied, Partially Satisfied, Not Satisfied} per rubric item
- _Time-aware weighting_: Later, better-informed steps count more; critical violations short-circuit to fail
- _Pros_: Rich signal, captures "how well" not just "did it work"
- _Cons_: Rubric design is hard, LLM-as-judge adds its own variance
_Source: [ResearchRubrics](https://arxiv.org/html/2511.07685), [Rubric-Based Evaluation for Agentic Systems](https://medium.com/@aiforhuman/rubric-based-evaluation-for-agentic-systems-db6cb14d8526)_

**Pattern C: Milestone/Progress-Based**
Tasks are decomposed into ordered milestones. Agent receives credit for each milestone reached, regardless of whether the final goal is achieved. Score = milestones_reached / total_milestones. Combines end-point score with progress score.
- _Used by_: Modern multi-step agent benchmarks
- _Rubric variant_: Award partial credit as tests start to pass; track "lift in pass-rates" — evaluation as momentum, not just end-state
- _Pros_: Rewards meaningful progress, differentiates between agents that fail early vs. late
- _Cons_: Milestone definition is subjective; not all tasks decompose cleanly
_Source: [Agentic Benchmarks](https://www.emergentmind.com/topics/agentic-benchmarks), [Evaluating Agentic AI (TechRxiv)](https://www.techrxiv.org/users/985444/articles/1350845/master/file/data/agentic_techrxiv_v3/agentic_techrxiv_v3.pdf)_

### Multi-Run Evaluation Architecture

The core architectural decision for handling non-determinism:

**How many runs per scenario?**
- pass@1 with single run: cheapest, but unreliable for non-deterministic agents
- K runs with mean aggregation: standard approach. K=3 is minimum, K=5-10 is the practical sweet spot, K=100 for capability frontier research
- The unbiased pass@k estimator (Chen et al.) allows generating n>k samples and estimating pass@k without running exactly k trials

**Reducer/Aggregation function per scenario:**
- **Mean**: Most common. Smooth, handles partial credit. Sensitive to outliers.
- **Median**: Robust to outliers. Used by Artificial Analysis for binary predictions.
- **Trimmed mean**: Excludes extreme values. Used in database benchmarks (TPC-H style).
- **pass@k formula**: For binary outcomes only. `1 - C(n-c,k)/C(n,k)`
- **pass^k**: For reliability measurement. Probability all k trials succeed. Dramatically lower than pass@1 for most agents.

**Architectural recommendation from the field**: Run K epochs, store all per-run scores, compute multiple aggregate metrics (mean, CI, pass@k, pass^k). Let the leaderboard show the primary metric with CI as secondary.
_Source: [Anthropic Statistical Approach](https://www.anthropic.com/research/statistical-approach-to-model-evals), [τ-Bench](https://sierra.ai/blog/benchmarking-ai-agents)_

### Aggregation Architecture: Per-Scenario to Leaderboard

**Level 1 — Per-Run Score**: Single number for one agent on one scenario in one run (binary or 0-100%)

**Level 2 — Per-Scenario Score**: Aggregate across K runs for one agent on one scenario
- Reducer: mean, median, or pass@k
- Also report: standard deviation, confidence interval, min/max

**Level 3 — Per-Category Score** (optional): If scenarios are grouped (e.g., by crisis type, difficulty), aggregate per-scenario scores within category
- Typically: equally-weighted average across scenarios in category

**Level 4 — Overall Agent Score**: Single leaderboard number
- **Equal weighting**: Mean across all scenarios (simplest, most common)
- **Weighted by difficulty**: Harder scenarios count more
- **Composite multi-dimensional**: CLEAR-style `Score = w₁·Dim₁ + w₂·Dim₂ + ... + wₙ·Dimₙ` with customizable weights summing to 1.0
- **Normalization**: Min-max scaling when combining dimensions of different units/scales

_Source: [CLEAR Framework](https://arxiv.org/html/2511.14136v1), [Artificial Analysis Methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking)_

### Reproducibility Architecture

**Containerized evaluation** is the gold standard:
- Fresh Docker container per task/run ensures identical initial state
- Pinned dependency versions, prebuilt images, deterministic templates
- Agent-Diff uses PostgreSQL schema isolation — each environment in its own namespace, seeded from deterministic templates
- Terminal-Bench pins package versions and includes dependencies in Docker context

**Remaining non-determinism sources** (cannot be fully eliminated):
- LLM API responses (temperature, sampling)
- External API latency/availability
- Hardware differences affecting timing

**Mitigation**: Multiple runs + confidence intervals + containerization addresses all controllable sources. Report which sources of non-determinism are present.
_Source: [SetupBench](https://arxiv.org/pdf/2507.09063), [Agent-Diff](https://arxiv.org/html/2602.11224v1), [Terminal-Bench](https://arxiv.org/html/2601.11868v1)_

### Reporting & Transparency Standards

The Agentic Benchmark Checklist (ABC) from UIUC emphasizes two core validity principles:
1. **Task Validity**: A task should be solvable if and only if the agent possesses the target capability
2. **Outcome Validity**: Evaluation methods should accurately indicate whether a task was solved

**Best practices for leaderboard reporting:**
- Report primary metric + confidence interval (not just a single number)
- Use hybrid evaluation: process-based metrics alongside outcome-based
- Validate LLM-as-judge graders with AlignEval or similar tools
- Freeze environments (frozen websites, pinned versions) for consistency
- When perfect validity is impossible, report limitations transparently

**CLEAR Framework production thresholds:**
- pass@8 ≥ 80% recommended for mission-critical applications
- Enterprises customize dimension weights based on priorities (e.g., financial services emphasize reliability + assurance)

_Source: [Agentic Benchmark Checklist](https://uiuc-kang-lab.github.io/agentic-benchmarks/), [CLEAR Framework](https://arxiv.org/html/2511.14136v1)_

## Implementation Approaches and Technology Adoption

### Action Logging & Behavior Cataloguing

**This is critical for crisis_bench's exploratory evaluation philosophy** — observing what agents do rather than prescribing what they should do.

**What to capture per run:**
Every agent run should produce a structured trace containing:
- **Tool/function calls**: What tools the agent invoked (call_police, contact_wife, search_web, transfer_money, etc.)
- **Call sequence & timing**: Order of actions, time between decisions
- **Arguments/parameters**: Who was called, what was said, what amounts were involved
- **Agent reasoning**: Chain-of-thought or internal reasoning (if accessible)
- **Outcome per action**: Did the call succeed? What was the response?

**Industry standard for tracing**: OpenTelemetry (OTEL) is emerging as the standard for agent telemetry. Langfuse and LangSmith natively capture tool calls, token usage, and prompt/completion pairs. Traces capture the full context of each request including relationships between steps.
_Source: [Langfuse Observability](https://langfuse.com/docs/observability/overview), [LangSmith](https://www.langchain.com/langsmith/observability), [Azure Agent Observability](https://azure.microsoft.com/en-us/blog/agent-factory-top-5-agent-observability-best-practices-for-reliable-ai/)_

**Building an action taxonomy for crisis_bench:**
Rather than a fixed taxonomy, start with a two-pass approach:
1. **Discovery pass**: Run agents on scenarios, log all tool calls and actions with no pre-defined categories
2. **Taxonomy construction**: After observing N runs, cluster actions into categories (e.g., "contact_authority", "contact_known_person", "gather_information", "take_direct_action", "do_nothing")
3. **Scoring pass**: Apply the taxonomy retroactively and to future runs

This mirrors Anthropic's Bloom framework: specify target behaviors with descriptions, generate scenarios, execute across multiple runs, then judge behavior presence — all without requiring ground truth labels.
_Source: [Bloom Auto-Evals (Anthropic)](https://alignment.anthropic.com/2025/bloom-auto-evals/)_

### Scoring Without Prescribing "Right" Answers

**The Bloom Model Applied to crisis_bench:**

Bloom's four-stage pipeline maps well to the crisis_bench use case:
1. **Understanding**: Define behaviors of interest (e.g., "contacts emergency services", "attempts to verify the situation", "escalates to a human")
2. **Ideation**: The crisis scenarios themselves serve as the elicitation suite
3. **Rollout**: Run each agent K times per scenario
4. **Judgment**: Score each run for presence/absence/degree of each behavior

**Elicitation rate** = proportion of runs where a behavior score exceeds a threshold. This gives you:
- "Agent X contacts authorities in 7/10 runs of the suicide crisis scenario"
- "Agent Y attempts to verify the situation first in 9/10 runs"
- No claim about which behavior is "correct" — just observable frequencies

**Reference-free metrics** for open-ended evaluation:
- Rather than evaluating against expected outputs, evaluate general behavior patterns
- Measure behavior presence distribution, not just binary correct/incorrect
- This supports Mauk's goal of discovering action paths that weren't anticipated
_Source: [Bloom Auto-Evals (Anthropic)](https://alignment.anthropic.com/2025/bloom-auto-evals/), [Google Agent Evaluation Codelab](https://codelabs.developers.google.com/codelabs/production-ready-ai-roadshow/2-evaluating-multi-agent-systems/evaluating-multi-agent-systems)_

### Practical Multi-Run Cost Management

**The cost equation:**
`Total cost = (scenarios × agents × runs_per_scenario × cost_per_run)`

If cost_per_run ≈ $0.05-0.50 (depending on model and scenario length):
- 10 scenarios × 5 agents × 5 runs = 250 runs → $12.50-$125
- 10 scenarios × 5 agents × 10 runs = 500 runs → $25-$250
- 50 scenarios × 10 agents × 10 runs = 5,000 runs → $250-$2,500

**Cost optimization strategies:**
- **Start with K=3 runs** during development, increase to K=5-10 for official leaderboard results
- **Batch API calls** — combine multiple requests to reduce overhead (15-30% of costs are API call overhead)
- **Semantic caching** — if the same scenario+agent produces identical prompts, cache results (can avoid ~41% of calls in some setups)
- **Tiered evaluation** — quick pass with K=3 to filter, deep pass with K=10 for leaderboard candidates
- **Cost-per-pass metric** — report how much it costs for an agent to achieve a successful outcome (CLEAR framework pattern)
_Source: [Efficient Agents](https://arxiv.org/html/2508.02694v1), [Databricks Cost Optimization](https://www.databricks.com/blog/building-state-art-enterprise-agents-90x-cheaper-automated-prompt-optimization)_

### Implementation Architecture for crisis_bench

**Proposed evaluation pipeline (based on research findings):**

```
┌─────────────────────────────────────────────────────┐
│                  EVALUATION PIPELINE                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. SCENARIO LOADER                                 │
│     Load crisis scenario + agent config             │
│                                                     │
│  2. AGENT RUNNER (K epochs per scenario)            │
│     Execute agent, capture full trace:              │
│     - All tool/function calls                       │
│     - Arguments and responses                       │
│     - Reasoning chain (if available)                │
│     - Timing and token usage                        │
│                                                     │
│  3. ACTION EXTRACTOR                                │
│     Parse traces → structured action list           │
│     Categorize actions against taxonomy             │
│     Flag novel/unexpected actions                   │
│                                                     │
│  4. SCORER (per run)                                │
│     Code-based: action presence/absence checks      │
│     Optional: LLM-as-judge for quality dimensions   │
│     Output: per-run score vector                    │
│                                                     │
│  5. REDUCER (per scenario)                          │
│     Aggregate K runs → per-scenario metrics:        │
│     - Mean score + CI                               │
│     - Action frequency distribution                 │
│     - Success rate (if binary criteria defined)     │
│     - pass@k / pass^k (if applicable)              │
│                                                     │
│  6. AGGREGATOR (per agent)                          │
│     Combine per-scenario → overall agent score      │
│     Equal-weighted mean across scenarios             │
│                                                     │
│  7. REPORTER                                        │
│     Leaderboard JSON + detailed per-scenario logs   │
│     Action frequency heatmaps                       │
│     Confidence intervals on all metrics             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Testing & Quality Assurance of the Scoring System

**Validate the evaluator itself:**
- Use AlignEval or similar tools to benchmark LLM-as-judge accuracy (if using model-based grading)
- Create "golden" runs with known expected behaviors to sanity-check the scoring pipeline
- Test edge cases: agent does nothing, agent does everything, agent hallucinates tools
- Verify that scoring is deterministic given the same trace (the scorer should be deterministic even if the agent isn't)
_Source: [Agentic Benchmark Checklist](https://uiuc-kang-lab.github.io/agentic-benchmarks/), [Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)_

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM-as-judge variance | Scores differ between judge runs | Use code-based grading where possible; average multiple judge runs |
| Insufficient run count | Noisy scores, false leaderboard rankings | Start with K=5 minimum; report CI; increase K if CI is wide |
| Action taxonomy misses novel behaviors | Interesting agent behavior goes unscored | Keep raw traces; flag uncategorized actions; update taxonomy iteratively |
| Cost explosion with many agents × runs | Budget overrun | Tiered evaluation; start small; cache where possible |
| Scenario design bias | Benchmark tests only expected behaviors | Include open-ended scenarios; Bloom-style discovery; regular scenario refresh |

## Technical Research Recommendations

### Recommended Scoring Framework for crisis_bench

Based on all research, the recommended approach combines elements from multiple patterns:

**Primary Metric (Leaderboard):** Behavior-weighted score (0-100%) per scenario, averaged across K runs, then averaged across scenarios for overall agent score. Report with 95% confidence intervals.

**Secondary Metrics:**
- Action frequency distribution per scenario (what % of runs did the agent take action X?)
- pass@k / pass^k for binary outcome dimensions
- Cost-per-run for practical comparison

**Scoring Layers:**
1. **Action presence layer** (code-based, deterministic): Did the agent take action X? Binary per action, automated from trace.
2. **Action quality layer** (optional, LLM-as-judge): How well did the agent execute the action? Rubric-scored.
3. **Behavior frequency layer** (statistical): How often does the agent take each action across K runs?

### Implementation Roadmap

1. **Phase 1 — Trace Infrastructure**: Build action logging that captures all tool calls and agent decisions per run
2. **Phase 2 — Discovery Runs**: Run agents on scenarios, collect traces, build initial action taxonomy from observed behaviors
3. **Phase 3 — Scorer V1**: Code-based scoring of action presence/absence against taxonomy
4. **Phase 4 — Multi-Run Pipeline**: Add K-epoch execution with statistical aggregation
5. **Phase 5 — Leaderboard**: Aggregate scores, generate leaderboard with CI and action frequency breakdowns

### Technology Stack Recommendations

- **Trace format**: JSON/JSONL per-run logs following OpenTelemetry-inspired schema
- **Evaluation framework**: Inspect AI pattern (Dataset + Solver + Scorer + Reducer) or custom lightweight pipeline
- **Containerization**: Docker per scenario run for reproducibility
- **Statistical reporting**: Mean + 95% CI + action frequency heatmaps
- **Leaderboard**: Static site generated from results JSON (GitHub Pages or similar)

## Research Synthesis

### Strategic Recommendations for crisis_bench

Based on comprehensive research across 20+ benchmarks, frameworks, and academic sources, here are the concrete recommendations for crisis_bench's scoring framework:

#### 1. Adopt a Two-Layer Scoring Architecture

**Layer 1 — Observational (What did the agent do?)**
This is crisis_bench's differentiator. Don't prescribe right answers. Instead:
- Log every tool call, function call, and agent action per run
- After initial discovery runs, build an action taxonomy from observed behaviors
- Score action presence/absence with code-based grading (deterministic, no judge variance)
- Report as action frequency distributions: "Agent X contacts authorities in 70% of runs"

**Layer 2 — Evaluative (How well did the agent perform?)**
Once you have enough data to form opinions about what "good" looks like:
- Optional rubric dimensions scored by LLM-as-judge (calibrated against human examples)
- Composite score combining action presence + quality dimensions
- This layer can evolve over time as understanding deepens

#### 2. Multi-Run Statistical Protocol

| Parameter | Recommended Value | Rationale |
|-----------|------------------|-----------|
| Runs per scenario (K) | 5 (dev), 10 (leaderboard) | Practical sweet spot per community consensus |
| Reducer | Mean | Simplest, handles partial credit, widely understood |
| Uncertainty | 95% CI (mean ± 1.96 × SEM) | Anthropic-recommended standard |
| Comparison test | Paired t-test | Accounts for correlation between agents on same scenarios |
| Minimum CV target | < 0.05 | Ensures acceptable variance |

#### 3. Leaderboard Design

**Primary display per agent:**
```
Agent Name | Overall Score | 95% CI | Runs
───────────┼───────────────┼────────┼─────
Agent A    | 78.3%         | ±4.2%  | 10/scenario
Agent B    | 65.1%         | ±5.8%  | 10/scenario
```

**Drill-down per scenario:**
- Per-scenario scores with CI
- Action frequency heatmap (which actions, how often)
- pass@k curve (capability) and pass^k curve (reliability)

**Reporting standards (from ABC checklist + Anthropic):**
- Never show single-run scores without CI
- When CIs overlap between agents, explicitly note that ranking is uncertain
- Report number of runs, cost per run, total evaluation cost
- Make raw traces available for independent analysis

#### 4. Practical Implementation Phases

| Phase | What | When |
|-------|------|------|
| **Phase 1** | Trace infrastructure — capture all tool calls per run in JSON/JSONL | First |
| **Phase 2** | Discovery runs — run 3-5 agents × 3 runs, collect traces, observe patterns | After Phase 1 |
| **Phase 3** | Action taxonomy — cluster observed actions, build category system | After Phase 2 |
| **Phase 4** | Scorer V1 — code-based action presence scoring against taxonomy | After Phase 3 |
| **Phase 5** | Multi-run pipeline — K=10 epochs with mean + CI aggregation | After Phase 4 |
| **Phase 6** | Leaderboard — static site with overall scores, drill-downs, heatmaps | After Phase 5 |
| **Phase 7** | Iterate — add LLM-as-judge quality dimensions, expand scenarios, refine taxonomy | Ongoing |

### Broader Context: AI Safety Evaluation Gap

This research is timely. The 2026 International AI Safety Report highlights an emerging "evaluation gap" where benchmark performance doesn't reliably reflect real-world behavior. 87% of AI agents lack safety evaluation cards (MIT CSAIL AI Agent Index 2025). crisis_bench directly addresses this gap by benchmarking agent behavior in high-stakes scenarios.

The field is moving from static benchmarks toward dynamic, behavior-focused evaluation. crisis_bench's observational approach — logging what agents actually do rather than checking against pre-defined answers — aligns with this trajectory and could set a precedent for safety-focused agent benchmarking.
_Source: [International AI Safety Report 2026](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026), [MIT CSAIL AI Agent Index 2025](https://arxiv.org/html/2602.17753)_

### Source Documentation

**Primary Sources:**
- [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — Grading strategies, rubric design, practical recommendations
- [Anthropic: Statistical Approach to Model Evals](https://www.anthropic.com/research/statistical-approach-to-model-evals) — CI calculation, significance testing, run count guidance
- [Anthropic: Bloom Auto-Evals](https://alignment.anthropic.com/2025/bloom-auto-evals/) — Behavioral evaluation without ground truth
- [Sierra: τ-Bench](https://sierra.ai/blog/benchmarking-ai-agents) — pass^k reliability metric, stateful evaluation
- [Chen et al.: Evaluating LLMs Trained on Code (Codex)](https://arxiv.org/pdf/2107.03374) — Unbiased pass@k estimator formula
- [CLEAR Framework](https://arxiv.org/html/2511.14136v1) — Multi-dimensional composite scoring
- [Agentic Benchmark Checklist (UIUC)](https://uiuc-kang-lab.github.io/agentic-benchmarks/) — Task and outcome validity principles

**Evaluation Frameworks:**
- [Inspect AI (UK AISI)](https://inspect.aisi.org.uk/) — Epochs, reducers, modular evaluation pipeline
- [SWE-bench](https://www.swebench.com/) — Containerized evaluation, submission format
- [BigCodeBench](https://bigcode-bench.github.io/) — Calibrated pass@1
- [Codabench](https://www.codabench.org/) — Open-source benchmark platform with leaderboard

**Observability & Tracing:**
- [Langfuse](https://langfuse.com/docs/observability/overview) — Agent tracing and observability
- [LangSmith](https://www.langchain.com/langsmith/observability) — LLM application monitoring

**Additional Sources:**
- [Pass@k Opinions (Runloop)](https://runloop.ai/blog/i-have-opinions-on-pass-k-you-should-too) — pass@10 as practical sweet spot
- [Pass@k Unbiased Estimator](https://leehanchung.github.io/blogs/2025/09/08/pass-at-k/) — Formula derivation and implementation
- [Artificial Analysis Methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking) — Aggregation approaches
- [HuggingFace Evaluation Guidebook](https://huggingface.co/spaces/OpenEvals/evaluation-guidebook) — Variance-aware reporting
- [International AI Safety Report 2026](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026) — Evaluation gap analysis

---

**Technical Research Completion Date:** 2026-02-25
**Research Period:** Comprehensive current technical analysis
**Source Verification:** All technical facts cited with current sources
**Confidence Level:** High — based on multiple authoritative technical sources with cross-validation
