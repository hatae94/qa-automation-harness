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

!`qa-harness validate --flows src/flows --catalog ${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens 2>&1 | tail -5 || echo "No flows generated yet"`
!`ls src/flows/*.yaml 2>/dev/null | wc -l | xargs echo "Generated YAML flows:"`

## Your Task

Execute this pipeline in order. Never ask permission between stages. Always proceed to the next stage automatically.

### Stage 1: Parse TC

Extract the CSV file path from $ARGUMENTS (first argument) and parse it directly.

```bash
qa-harness parse-tc -i $ARGUMENTS -o parsed.json
```

If parse succeeds, report TC count.

### Stage 2: Generate YAML

```bash
qa-harness generate-yaml --tc parsed.json --catalog ${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens --templates ${CLAUDE_PLUGIN_ROOT}/src/templates
```

If 0 YAMLs are generated, report the stats and state: "0 YAMLs generated. The bundled knowledge base does not cover these TCs. Run /qa-index with a connected device to scan the actual app."

Then continue to Stage 3 regardless.

### Stage 3: Validate

```bash
qa-harness validate --flows src/flows --catalog ${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens
```

If validation has errors, report which TCs failed and why. Continue with valid flows.

### Stage 4: Report

Summarize:
- Total TCs parsed
- YAMLs generated
- Validation pass/fail counts
- Any errors encountered

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- Use `qa-harness` CLI for all operations. Do NOT manually parse CSV or generate YAML.
- If `qa-harness` is not installed, tell the user to run `pip install -e .` in the project directory.
- $ARGUMENTS contains the CSV file path. Use it directly as the first argument to parse-tc.
