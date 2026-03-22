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

The qa-harness CLI is installed in the plugin's venv. Use this alias:

```bash
QA="${CLAUDE_PLUGIN_DATA}/venv/bin/qa-harness"
if [ ! -f "$QA" ]; then
  QA="$(which qa-harness 2>/dev/null || echo '')"
fi
if [ -z "$QA" ]; then
  echo "ERROR: qa-harness not found. Running install..."
  "${CLAUDE_PLUGIN_ROOT}/scripts/install-qa-harness.sh"
  QA="${CLAUDE_PLUGIN_DATA}/venv/bin/qa-harness"
fi
```

Run the above FIRST before any qa-harness command. Then use `$QA` for all subsequent calls.

## Your Task

Execute this pipeline in order. Never ask permission between stages. Always proceed automatically.

### Stage 1: Parse TC

```bash
$QA parse-tc -i "$ARGUMENTS" -o parsed.json
```

If parse succeeds, report TC count.

### Stage 2: Generate YAML

```bash
$QA generate-yaml --tc parsed.json --catalog "${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens" --templates "${CLAUDE_PLUGIN_ROOT}/src/templates"
```

If 0 YAMLs generated, report: "0 YAMLs generated. The bundled knowledge base does not cover these TCs. Run /qa-index with a connected device to scan the actual app." Then continue.

### Stage 3: Validate

```bash
$QA validate --flows src/flows --catalog "${CLAUDE_PLUGIN_ROOT}/src/knowledge/screens"
```

If errors, report which TCs failed and why. Continue with valid flows.

### Stage 4: Report

Summarize:
- Total TCs parsed
- YAMLs generated
- Validation pass/fail counts
- Any errors encountered

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use $QA CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use $QA CLI output.
- If $QA is not found after install attempt, report the error and stop.
