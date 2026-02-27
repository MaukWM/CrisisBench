# CrisisBench -- Remaining Brainstorming Roadmap

## What's Done

- [x] Morphological analysis (all 7 dimensions scoped)
- [x] Scenario architecture (three-actor system, full-day sim)
- [x] Payload format (JSON, nested per module, heartbeat push model)
- [x] Scenario script architecture (generate_scenario.py + run_benchmark.py)
- [x] Scoring MVP (detection, action, time-to-action, LLM-as-judge)
- [x] Memory system design (fresh context per heartbeat, memory = only continuity)
- [x] Comms format (emails=subject only, SMS/Slack=complete)
- [x] Tool space refinement (custom controlled tools + real MCP noise filler)
- [x] Chaos engineering (10 attacks analyzed, all resolved)

## What's Left (in recommended order)

### 1. System Prompt / Agent Identity
**Why next:** The most sensitive remaining piece. Determines whether the agent behaves naturally or suspects a test. Now that tools and chaos engineering are done, we know what constraints the prompt must satisfy.

- Draft the SOUL.md equivalent (personality, no emergency framing)
- Draft the identity (name, vibe)
- Draft the system prompt (how heartbeats are presented, tool framing)
- Define tool descriptions as the agent sees them (dry, functional, no hints)
- Define memory usage instructions
- Define "when to act vs stay quiet" guidance (must NOT hint at health monitoring)
- Validate against Attack 4 (prompt must not leak intent)

### 2. Cross-Pollination (Scoring & Methodology)
**Why second:** Refine scoring with best practices from existing benchmarks before implementation.

- Study how MMLU, HumanEval, SWE-bench, AgentBench score things
- Statistical methodology: how many runs per config? Confidence intervals?
- How do other benchmarks handle non-deterministic LLM outputs?
- Inter-rater reliability for LLM-as-judge
- What metrics do paper reviewers expect?
- Leaderboard design (ELO vs pass@k vs composite)

### 3. Human Simulator & Operator Design
**Why last:** Implementation details that flow from above decisions.

- Human Simulator: detailed persona, response patterns, edge cases
- 911 Operator: NENA protocol, conversation flow
- Temperature/model settings for reproducibility
- Edge cases (what if agent asks David a medical question pre-crisis?)

---

## Ready for Implementation After These

With all brainstorming complete, the implementation plan would be:
1. Write generate_scenario.py (scenario file generation)
2. Write the system prompt + agent config
3. Write the orchestrator (heartbeat loop, tool routing)
4. Write the scorer
5. Run against 3-4 models across T1-T4
6. Analyze results
7. Write the paper
