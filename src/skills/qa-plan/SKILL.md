---
name: qa-plan
description: Use when converting QA test cases (Excel/CSV) into validated maestro-runner YAML flows — the ONLY point where LLM is involved in the pipeline, filling template slots from the knowledge base
---

# qa-plan: TC to YAML Conversion (Slot Filling)

## Overview

Convert test cases (CSV/Excel) into validated maestro-runner YAML files. **This is the single point where LLM participates in the entire pipeline.** The LLM's role is strictly constrained: fill template slots from the knowledge base catalog. It never generates YAML structure.

## When to Use

- New test cases to automate
- Test case updates or revisions
- After `qa-index` rebuilds the knowledge base

## Process

```
TC CSV ──parse──> structured steps
                      |
                      v
          Map to flow-graph path (deterministic)
                      |
                      v
          Select matching template (deterministic)
                      |
                      v
          LLM fills {{slots}} from element-catalog  <-- ONLY LLM step
                      |
                      v
          Validation gate (deterministic)
                      |
              pass?  / \  fail?
              v         v
        Save YAML    Reject + log reason
```

## LLM Role: Slot Filling ONLY

The LLM receives:
- The TC steps in natural language
- The template with named `{{slot}}` placeholders
- The element catalog (all valid selectors)
- The test data pool

The LLM returns a JSON object mapping slot names to catalog values. Nothing more.

### CRITICAL RULE: Template-Only Generation

- NEVER let the LLM generate YAML structure, flow sequences, or action types.
- NEVER let the LLM invent selectors not present in the element catalog.
- If a selector is not found, the LLM must return `"NOT_FOUND"` — not fabricate one.

### Slot Filling Example

**Input TC:** "LoginPage_13 — tap membership signup, enter phone number, verify OTP"

**Template:** `login-flow.template.yaml` with slots:
`{{intro_login_button}}`, `{{phone_input_selector}}`, `{{phone_number}}`, `{{otp_input_selector}}`, `{{otp_code}}`

**LLM output:**
```json
{
  "template": "login-flow.template.yaml",
  "slots": {
    "intro_login_button": "#intro-v2\\.click-signup-btn",
    "phone_input_selector": "#phone-input",
    "phone_number": "01012345678",
    "otp_input_selector": "#otp-input",
    "otp_code": "123456"
  },
  "confidence": "high"
}
```

## Validation Gate

Every LLM output is checked before saving:

1. **ELEMENT_EXISTS** — all selectors exist in element-catalog.json
2. **VALID_TRANSITION** — screen path is valid in flow-graph.json
3. **RENDERER_MATCH** — WebView elements use CDP commands, Native use maestro-runner native
4. **KOREAN_INPUT_METHOD** — Korean text uses correct input method (CDP nativeValueSetter / ADB clipboard)
5. **TEST_DATA_VALID** — data values come from test-data pool, not hardcoded

Validation failure does not retry via LLM. The harness auto-corrects where possible (e.g., nearest-match selector) or rejects the plan with a clear reason.

## Example Commands

```bash
# Parse TC CSV into structured JSON
qa-harness plan parse -i /path/to/tc.csv -o parsed.json

# Generate YAML flows from parsed TCs
qa-harness plan generate --tc parsed.json

# Validate generated flows against knowledge base
qa-harness plan validate

# Parse + generate + validate in one step
qa-harness plan full -i /path/to/tc.csv
```

## Output

Validated YAML files saved to `src/flows/{tc-id}.yaml`.
