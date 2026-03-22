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
!`cat src/knowledge/flow-graph.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Flow graph: {len(d.get(\"nodes\",[]))} screens, {len(d.get(\"edges\",[]))} transitions')" 2>/dev/null || echo "Flow graph: not loaded"`

## Step 1: Parse CSV

```bash
qa-harness plan parse -i "$0" -o parsed.json
```

Report: total TCs, priority distribution, categories found.

## Step 2: Generate YAML

```bash
qa-harness plan generate --tc parsed.json
```

Report: how many TCs matched templates, how many skipped.

## Step 3: Validate

```bash
qa-harness plan validate
```

Report: pass/fail per flow, error details for failures.

## Rules

- Use `qa-harness` CLI exclusively. Never parse CSV manually.
- Never generate YAML structure directly. The CLI uses templates + slot filling.
- $ARGUMENTS contains the CSV file path.
