---
name: qa-report
description: Use when generating QA test reports from maestro-runner results — parses JUnit XML, maps to original TC IDs, generates HTML and Telegram summary
---

# qa-report: Result Collection and Reporting

## Overview

Parse execution results and generate human-readable reports. Entirely rules-based — **no LLM involvement.** Maps raw maestro-runner JUnit XML output back to original TC IDs and produces reports in multiple formats.

## When to Use

- After `qa-run` completes (auto-triggered or manual)
- When stakeholders request test status
- For CI/CD pipeline integration

## Process

```
JUnit XML results
      |
      v
Parse pass/fail/error per test file
      |
      v
Map YAML filenames back to TC IDs (via tc-mapping.json)
      |
      v
Classify failures (rules-based)
      |
      v
Generate reports:
  ├─ HTML    (detailed, with screenshots)
  ├─ Telegram (summary message)
  └─ JSON   (machine-readable)
```

## Report Formats

### HTML Report (Detailed)

Full report with expandable failure details and embedded screenshots:

```
QA Automation Report — 2026-03-22 14:30
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary: 23/25 passed (92%) | 2 failed | 0 skipped
Duration: 14m 32s | Batch: core

PASS LoginPage_13 — Login with phone + OTP          [1.2s]
PASS LoginPage_15 — Phone input page UI validation   [0.8s]
FAIL SignupPage_1 — Full signup flow                 [TIMEOUT 60s]
   Error: Element #terms-agree-all not found within 10s
   Screenshot: screenshots/SignupPage_1_fail.png
FAIL LoginPage_7  — Back button exit popup           [ASSERTION]
   Error: assertVisible #exit-popup-title timed out
   Screenshot: screenshots/LoginPage_7_fail.png
```

### Telegram Summary

Concise message for team notification:

```
QA Report [core] 2026-03-22 14:30
23/25 (92%) passed | 2 failed
Duration: 14m 32s

Failed:
- SignupPage_1: TIMEOUT (#terms-agree-all)
- LoginPage_7: ASSERTION (#exit-popup-title)
```

### JSON (Machine-Readable)

```json
{
  "timestamp": "2026-03-22T14:30:00Z",
  "tier": "core",
  "summary": { "total": 25, "passed": 23, "failed": 2, "skipped": 0 },
  "duration_seconds": 872,
  "results": [
    { "tc_id": "LoginPage_13", "status": "pass", "duration_ms": 1200 },
    { "tc_id": "SignupPage_1", "status": "fail", "error_type": "TIMEOUT", "element": "#terms-agree-all" }
  ]
}
```

## Failure Classification (Rules-Based)

| Error Pattern | Classification | Auto-action |
|--------------|----------------|-------------|
| `Element .* not found` | SELECTOR_NOT_FOUND | Flag for KB review |
| `Timeout .* exceeded` | TIMEOUT | Check app responsiveness |
| `CDP connection` | CDP_ERROR | Check bridge status |
| `Process crashed` | APP_CRASH | Flag for dev team |
| `assertVisible .* failed` | ASSERTION_FAIL | Compare with expected state |

Classification is purely pattern-matching on error strings. No LLM interpretation.

## Example Commands

```bash
# Generate report from latest results
qa-harness report generate

# Generate report with TC mapping
qa-harness report generate --tc-map src/flows/_manifest.json

# Generate only Telegram summary
qa-harness report generate --format telegram

# Generate all formats
qa-harness report generate --format all
```

## Output Files

```
results/
├── report.html          # detailed HTML report
├── summary.txt          # Telegram-ready summary
├── results.json         # machine-readable results
├── tc-mapping.json      # YAML filename -> TC ID mapping
└── screenshots/         # failure screenshots
```
