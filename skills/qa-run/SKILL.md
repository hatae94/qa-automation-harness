---
name: qa-run
description: Use when executing QA test flows via maestro-runner — deterministic execution with ZERO LLM involvement, handles batching, CDP bridge, and session management
---

# qa-run: Deterministic Test Execution

## Overview

Execute validated YAML test flows through maestro-runner. **ZERO LLM calls occur during execution.** Every decision — which selector to tap, which input method to use, how to recover from failure — is pre-determined by the harness.

## When to Use

- Running smoke tests (5 min, ~5 TCs)
- Running core regression (15 min, ~25 TCs)
- Running full suite (45-60 min, ~100+ TCs)

## CRITICAL: No LLM at Runtime

| What happens at runtime | What does NOT happen |
|------------------------|---------------------|
| maestro-runner executes pre-validated YAML | LLM generating or modifying YAML |
| CDP bridge relays pre-determined commands | LLM deciding which element to tap |
| Deterministic retry on known error patterns | LLM analyzing failures in real-time |
| Batch restart on session threshold | LLM monitoring execution progress |

## Execution Process

```
Pre-flight checks
      |
      v
Start CDP bridge (input_server.py)
      |
      v
For each batch (25 TCs):
  |
  ├─ For each TC:
  |   ├─ Reset app state
  |   ├─ maestro-runner --driver devicelab test {yaml}
  |   ├─ Renderer Dispatch: WebView -> CDP | Native -> maestro native
  |   ├─ Collect result (pass/fail + screenshot on failure)
  |   └─ Deterministic retry if eligible
  |
  └─ Restart driver between batches
      |
      v
Aggregate JUnit XML results
```

### Pre-flight Checks

1. Device connected and responsive (`adb devices`)
2. CDP bridge port available (kill stale ADB forwards)
3. App installed and launchable
4. All YAML files validated (skip any without validation stamp)

### Batch Strategy

- **25 tests per batch** — PoC #1040 showed driver crashes after 55+ consecutive tests
- **Driver restart between batches** — clean slate for CDP connections and app state
- **Independent TC execution** — each TC starts from app launch, no cross-TC state leakage

### Renderer Dispatch

Pre-determined per screen in the knowledge base `renderer` field:

```
Screen renderer = "webview"?
    YES -> CDP bridge (tap_remote.js / input_remote.js)
    NO  -> maestro-runner native commands
```

Transition handling:
- WebView to Native: CDP session cleanup + waitForAnimationToEnd
- Native to WebView: ADB forward port recheck + CDP connect + WebView load wait

### Error Handling (Deterministic, NOT LLM-based)

| Error Type | Recovery Action | Max Retries |
|-----------|----------------|-------------|
| TIMEOUT | Restart app, re-execute TC | 1 |
| CDP_CONNECTION_LOST | Reset ADB forward, reconnect | 2 |
| ELEMENT_NOT_FOUND | Screenshot + mark FAIL | 0 |
| APP_CRASH | Reinstall app, restart batch | 1 |
| DRIVER_CRASH | Restart maestro-runner driver | 1 |

### 3-Tier Execution

| Tier | TCs | Time | Use Case |
|------|-----|------|----------|
| Smoke | ~5 critical path | ~5 min | Pre-deploy gate |
| Core | ~25 high-value | ~15 min | Daily regression |
| Full | 100+ all automated | 45-60 min | Weekly/release |

## Example Commands

```bash
# Execute smoke tier (dry run)
qa-harness run --tier smoke --dry-run

# Execute core tier on a specific device
qa-harness run --tier core --device emulator-5554

# Execute full suite
qa-harness run --tier full

# CDP bridge management
qa-harness run cdp-start --device emulator-5554
qa-harness run cdp-health
qa-harness run cdp-stop
```

## Output

- JUnit XML results per TC
- Failure screenshots in `results/screenshots/`
- Execution log in `results/execution.log`
- Session metadata in `results/session.json`
