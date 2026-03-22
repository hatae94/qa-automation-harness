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
!`ls src/flows/*.yaml 2>/dev/null | wc -l | xargs echo "Ready flows:"`

## Execution

### 1. Pre-flight

```bash
qa-harness run --dry-run --tier smoke
```

Stop and report if pre-flight fails.

### 2. CDP Bridge

```bash
qa-harness run cdp-start
```

### 3. Execute

```bash
qa-harness run --tier smoke
```

$ARGUMENTS overrides: `<tier>` or `<tier> <device-id>`

### 4. Cleanup + Report

```bash
qa-harness run cdp-stop
qa-harness report generate --format all
```

## Rules

- Do NOT make decisions during execution. The runner is deterministic.
- Do NOT retry with modified YAML on failure. Report the failure as-is.
- Batch size 25, driver restarts between batches automatically.
