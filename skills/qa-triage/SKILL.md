---
name: qa-triage
description: Use when analyzing test failures to determine root cause — uses rules-based classification first, LLM analysis only for ambiguous failures
---

# qa-triage: Failure Analysis

## Overview

Analyze test failures to determine root cause and recommend action. **Rules-based classification handles the majority of cases. LLM is the last resort, not the first.**

## When to Use

- After `qa-report` shows failures
- When investigating flaky tests
- Before filing bug reports from test results

## Process

```
Failed TC result
      |
      v
[1] Classify by error pattern (rules-based)
      |
      v
[2] Match against known issues DB
      |
  match? ─YES─> Link to existing issue, skip
      |
     NO
      |
      v
[3] Check if environmental (device/network)
      |
  env? ─YES─> Mark as INFRA, recommend retry
      |
     NO
      |
      v
[4] Deterministic root cause?
      |
  clear? ─YES─> Classify + recommend action
      |
     NO (ambiguous)
      |
      v
[5] LLM analysis (LAST RESORT)
      |
      v
Classification + recommended action
```

## Classification Rules (No LLM)

| Error Pattern | Classification | Root Cause | Action |
|--------------|----------------|------------|--------|
| `Element .* not found` | SELECTOR_NOT_FOUND | UI changed or selector stale | Re-run `qa-index`, update KB |
| `Timeout .* exceeded` | TIMEOUT | App slow or hung | Check app performance, increase timeout or file perf bug |
| `CDP connection refused` | CDP_ERROR | Bridge down or port conflict | Restart CDP bridge, check ADB forwards |
| `Process crashed` / `SIGKILL` | APP_CRASH | App bug | File crash bug with logs |
| `assertVisible .* failed` | ASSERTION_FAIL | Expected element missing | Verify TC expectation vs current app state |
| `adb: device not found` | DEVICE_LOST | Device disconnected | Reconnect device, retry |
| `nativeValueSetter .* failed` | INPUT_ERROR | React state sync issue | Check input method in KB |

## Known Issue Database

Maintain `known-issues.json` mapping error signatures to tracked issues:

```json
[
  {
    "pattern": "Element #terms-agree-all not found",
    "issue": "APP-1234",
    "status": "open",
    "workaround": "App v2.3.1 removed this element; update KB"
  }
]
```

When a failure matches a known pattern, triage links to the existing issue instead of creating duplicates.

## LLM Analysis (Last Resort Only)

LLM is invoked only when:
1. Error does not match any classification rule
2. No known issue matches
3. Not an environmental failure
4. Error message is ambiguous or multi-cause

LLM receives: error log, screenshot, TC steps, and element catalog context. LLM returns: probable root cause + confidence level.

**Budget:** LLM triage should apply to less than 10% of failures. If more than 10% require LLM, the classification rules need expansion.

## Example Commands

```bash
# Triage all failures from latest run
qa-harness triage analyze

# Triage a specific TC failure
qa-harness triage analyze --tc-id SignupPage_1

# Update known issues database
qa-harness triage add-known-issue --pattern "Element #terms-agree-all not found" --issue APP-1234

# Show triage summary
qa-harness triage summary
```

## Output Per Failure

```json
{
  "tc_id": "SignupPage_1",
  "classification": "SELECTOR_NOT_FOUND",
  "root_cause": "Element #terms-agree-all removed in app v2.3.1",
  "confidence": "high",
  "method": "rules-based",
  "action": "Update knowledge base: re-run qa-index for signup flow",
  "known_issue": null
}
```

## Triage Summary

After analyzing all failures, produce a grouped summary:

```
Triage Summary — 2 failures analyzed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SELECTOR_NOT_FOUND (1):
  SignupPage_1 — #terms-agree-all missing -> re-index

ASSERTION_FAIL (1):
  LoginPage_7 — #exit-popup-title not visible -> verify app behavior

LLM analysis used: 0/2 (0%)
```
