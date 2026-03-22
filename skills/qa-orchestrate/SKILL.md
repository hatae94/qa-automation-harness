---
name: qa-orchestrate
description: Use when asked to run QA tests, execute test suite, automate test cases, or process TC CSV files for maestro-runner based mobile QA automation
context: fork
agent: general-purpose
allowed-tools: Bash(*), Read, Glob, Grep, Write, Skill
---

# QA Pipeline Orchestrator

You are executing the QA automation pipeline. Process $ARGUMENTS through the harness.

## CLI Setup

Run this setup block FIRST, exactly once. All subsequent stages reference `$QA` directly.

```bash
# Setup (run this FIRST, exactly once)
QA="${CLAUDE_PLUGIN_DATA}/venv/bin/qa-harness"
[ -f "$QA" ] || QA="$(which qa-harness 2>/dev/null)"
[ -z "$QA" ] && { "${CLAUDE_PLUGIN_ROOT}/scripts/install-qa-harness.sh" && QA="${CLAUDE_PLUGIN_DATA}/venv/bin/qa-harness"; }
echo "QA=$QA"
```

## Your Task

Execute this pipeline in order. Never ask permission between stages. Always proceed automatically.

### Stage 1: Parse TC

```bash
$QA parse-tc -i "$ARGUMENTS" -o parsed.json
```

If parse succeeds, report TC count.

### Stage 2: Generate YAML

```bash
$QA generate-yaml --tc parsed.json --catalog "${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens" --templates "${CLAUDE_PLUGIN_ROOT}/src/templates" --output flows/
```

If 0 YAMLs generated, report: "0 YAMLs generated. The bundled knowledge base does not cover these TCs. Run /qa-index with a connected device to scan the actual app." Then continue.

### Stage 3: Validate

```bash
$QA validate --flows flows/ --catalog "${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens"
```

If errors, report which TCs failed and why. Continue with valid flows.

### Stage 4: Report

Summarize:
- Total TCs parsed
- YAMLs generated
- Validation pass/fail counts
- Any errors encountered

Do NOT suggest next steps or recommend actions. Report results and stop.

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use $QA CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use $QA CLI output.
- If $QA is not found after install attempt, report the error and stop.
