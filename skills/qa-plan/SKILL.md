---
name: qa-plan
description: Use when converting QA test cases (Excel/CSV) into validated maestro-runner YAML flows — parses CSV, generates YAML from templates, validates against knowledge base
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Read, Write, Glob, Grep
---

# TC → YAML Conversion

You are converting test cases into maestro-runner YAML flows. Process $ARGUMENTS.

## Current Knowledge Base

!`ls src/knowledge/screens/*.json 2>/dev/null | wc -l | xargs echo "Indexed screens:"`

## Step 1: Parse CSV

```bash
qa-harness parse-tc -i $ARGUMENTS -o parsed.json
```

Report: total TCs, priority distribution, categories found.

## Step 2: Generate YAML

```bash
qa-harness generate-yaml --tc parsed.json
```

Report: how many TCs matched templates, how many skipped.

## Step 3: Validate

```bash
qa-harness validate
```

Report: pass/fail per flow, error details for failures.

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- Use `qa-harness` CLI exclusively. Never parse CSV manually.
- Never generate YAML structure directly. The CLI uses templates + slot filling.
- $ARGUMENTS contains the CSV file path.
