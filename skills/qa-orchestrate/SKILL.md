---
name: qa-orchestrate
description: Use when asked to run QA tests, execute test suite, automate test cases, or process TC CSV files for maestro-runner based mobile QA automation
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Bash(ls *), Bash(cat *), Read, Glob, Grep, Write, Skill
---

# QA Pipeline Orchestrator

You are executing the QA automation pipeline. Process $ARGUMENTS through the harness.

## Current State

!`qa-harness plan validate 2>&1 | tail -5 || echo "No flows generated yet"`
!`ls src/flows/*.yaml 2>/dev/null | wc -l | xargs echo "Generated YAML flows:"`

## Your Task

Execute this pipeline in order. Stop and report if any stage fails.

### Stage 1: Parse TC

```bash
qa-harness plan parse -i "$0" -o parsed.json
```

If parse succeeds, report TC count.

### Stage 2: Generate YAML

```bash
qa-harness plan generate --tc parsed.json
```

### Stage 3: Validate

```bash
qa-harness plan validate
```

If validation has errors, report which TCs failed and why. Continue with valid TCs.

### Stage 4: Report

Summarize:
- Total TCs parsed
- YAMLs generated
- Validation pass/fail counts
- Any errors encountered

## Rules

- Use `qa-harness` CLI for all operations. Do NOT manually parse CSV or generate YAML.
- If `qa-harness` is not installed, tell the user to run `pip install -e .` in the project directory.
- $ARGUMENTS contains the CSV file path or user instructions.
