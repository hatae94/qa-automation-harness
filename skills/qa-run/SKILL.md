---
name: qa-run
description: Use when executing QA test flows via maestro-runner — deterministic batch execution with CDP bridge management, zero LLM at runtime
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Bash(adb *), Read, Glob
---

# Deterministic Test Execution

Execute validated YAML flows via maestro-runner. ZERO LLM decisions during execution.

## Pre-flight Status

!`adb devices 2>/dev/null | tail -n +2 | head -5 || echo "ADB not available"`
!`ls flows/*.yaml 2>/dev/null | wc -l | xargs echo "Ready flows:"`

## Execution

### 1. Pre-flight

```bash
qa-harness run --dry-run
```

Stop and report if pre-flight fails.

### 2. CDP Bridge

```bash
qa-harness cdp start
```

### 3. Execute

```bash
qa-harness run
```

$ARGUMENTS overrides: `--device <id>` or `--batch-size N`

### 4. Cleanup + Report

```bash
qa-harness cdp stop
qa-harness report --tc-map parsed.json
```

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- Do NOT make decisions during execution. The runner is deterministic.
- Do NOT retry with modified YAML on failure. Report the failure as-is.
- Batch size 25, driver restarts between batches automatically.
