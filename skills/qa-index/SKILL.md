---
name: qa-index
description: Use when building or updating the app knowledge base — scans app screens via maestro hierarchy, indexes UI elements, builds flow graph
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Bash(maestro *), Bash(adb *), Read, Write, Glob
---

# Build App Knowledge Base

Scan the connected device's app and build the knowledge base for harness-based QA.

## Current State

!`ls src/knowledge/screens/*.json 2>/dev/null | wc -l | xargs echo "Indexed screens:"`
!`adb devices 2>/dev/null | tail -n +2 | head -3 || echo "ADB not available"`

## Execute

### 1. Validate Device

```bash
adb devices
```

Stop if no device connected.

### 2. Build Knowledge Base

```bash
qa-harness index build --device $0 --app $1
```

$ARGUMENTS format: `<device-id> <app-package>` (e.g., `emulator-5554 com.cupist.alpha`)

### 3. Detect Renderers

```bash
qa-harness index detect-renderer --device $0
```

### 4. Validate

```bash
qa-harness index validate
```

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- This is a ONE-TIME operation (or after app UI changes).
- LLM may enrich element labels, but structure comes from hierarchy dumps.
- Output goes to `src/knowledge/screens/` and `src/knowledge/flow-graph.json`.
