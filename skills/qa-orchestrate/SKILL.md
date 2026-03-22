---
name: qa-orchestrate
description: Use when running the full QA automation pipeline end-to-end — orchestrates parse, plan, validate, execute, and report in sequence with proper error handling
---

# qa-orchestrate: Full Pipeline Orchestrator

## Overview

Run the entire QA automation pipeline from TC input to final report in a single command. Orchestrates all stages with proper error handling and artifact caching. **LLM is involved in exactly one stage: slot filling during `qa-plan`.**

## When to Use

- "Run QA tests" or "automate these test cases"
- CI/CD pipeline integration (single entry point)
- End-to-end validation after app update

## Pipeline

```
[1] Parse TC          (deterministic)
 |
 v
[2] Check knowledge/  exists?
 |       |
 |    NO: run qa-index first (abort if no device)
 |       |
 v       v
[3] Generate YAML     (LLM: slot filling ONLY)  <-- single LLM step
 |
 v
[4] Validate          (deterministic)
 |
 |   fail? ──> log + skip failed TCs
 v
[5] Execute           (deterministic, LLM = 0%)
 |
 v
[6] Report            (deterministic)
 |
 v
[7] Triage (if failures exist, optional)
```

## LLM Involvement Map

| Stage | LLM? | Why |
|-------|-------|-----|
| [1] Parse TC | No | CSV parsing is deterministic |
| [2] Knowledge check | No | File existence check |
| [3] Generate YAML | **Yes** | Slot filling from catalog (TC-by-TC, 1 call each) |
| [4] Validate | No | Static rules against knowledge base |
| [5] Execute | No | maestro-runner only |
| [6] Report | No | JUnit XML parsing + templates |
| [7] Triage | Maybe | Rules-based first; LLM only for ambiguous failures |

## Stage Error Handling

| Stage | On Error | Pipeline Action |
|-------|----------|----------------|
| Parse TC | Malformed CSV row | Skip row, log warning, continue |
| Knowledge check | Missing KB | Abort with "run qa-index first" |
| Generate YAML | LLM returns NOT_FOUND slot | Skip TC, log as "unmappable" |
| Validate | Rule violation | Skip TC, log reason |
| Execute | TC failure | Record fail, continue next TC |
| Execute | Driver crash | Restart driver, continue batch |
| Report | Missing results | Generate partial report |

## Artifact Caching (Skip If Exists)

The orchestrator skips stages when valid artifacts already exist:

- `knowledge/` exists and is newer than app version? Skip `qa-index`
- `src/flows/{tc-id}.yaml` exists and validated? Skip `qa-plan` for that TC
- `results/{tc-id}.xml` exists for current run? Skip `qa-run` for that TC

Force full re-run with `--fresh` flag.

## Example Commands

```bash
# Full pipeline, core tier
qa-harness orchestrate --input tests.csv --tier core

# Re-plan only (skip execution)
qa-harness orchestrate --input tests.csv --stage plan

# Execute only (assumes YAML already generated)
qa-harness orchestrate --tier smoke --stage run

# Full fresh run, no caching
qa-harness orchestrate --input tests.csv --tier full --fresh
```

## Execution Tiers

| Tier | TC Selection | Expected Duration |
|------|-------------|-------------------|
| smoke | Top 5 critical path TCs | ~5 min |
| core | Top 25 high-value TCs | ~15 min |
| full | All automated TCs | 45-60 min |

## Output

Final output from the last completed stage. On success: full report (HTML + Telegram + JSON). On partial failure: partial report with skipped/failed TC list and reasons.
