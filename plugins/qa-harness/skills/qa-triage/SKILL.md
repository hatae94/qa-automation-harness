---
name: qa-triage
description: Use when analyzing test failures after QA execution — rules-based classification first, LLM only for ambiguous cases
context: fork
agent: general-purpose
allowed-tools: Bash(qa-harness *), Read, Write, Grep
---

# Analyze Test Failures

Classify and analyze test failures from the latest execution results.

## Current Results

!`ls results/*.xml 2>/dev/null | wc -l | xargs echo "Result files:"`
!`qa-harness triage summary 2>/dev/null | head -10 || echo "No triage data yet"`

## Execute

### Analyze All Failures

```bash
qa-harness triage analyze
```

### Analyze Specific TC

```bash
qa-harness triage analyze --tc-id $0
```

$ARGUMENTS: TC ID to analyze, or empty for all failures.

### Show Summary

```bash
qa-harness triage summary
```

## IMPORTANT
- Do NOT run --help. Execute commands directly as shown above.
- Do NOT read or parse files manually. Use qa-harness CLI exclusively.
- Do NOT ask the user questions. Handle errors automatically.
- Do NOT use python3 -c for analysis. Use qa-harness CLI output.

## Rules

- Classification is rules-based pattern matching. LLM is LAST RESORT (<10%).
- If >10% of failures need LLM, the classification rules need expanding.
- Match against known-issues.json before creating new issues.
