---
name: qa-report
description: Use when generating QA test reports from execution results — parses JUnit XML, maps to TC IDs, generates HTML and Telegram summary
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Read, Write
---

# Generate QA Report

Generate reports from test execution results.

## Current Results

!`ls results/*.xml 2>/dev/null | wc -l | xargs echo "JUnit XML files:"`
!`ls src/flows/_manifest.json 2>/dev/null && echo "TC mapping: available" || echo "TC mapping: not found"`

## Execute

```bash
qa-harness report --tc-map parsed.json
```

$ARGUMENTS overrides: `--results <dir>` or `--output <dir>`

## Output

Reports saved to `results/`:
- `report.html` — detailed with screenshots
- `summary.txt` — Telegram-ready
- `results.json` — machine-readable

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- Classification is rules-based pattern matching. No LLM interpretation.
- If no results exist, tell the user to run `/qa-run` first.
