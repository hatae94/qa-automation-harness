---
name: qa-index
description: Use when building or updating the app knowledge base — scans app screens via maestro hierarchy, indexes UI elements, and builds the flow graph for harness-based QA automation
---

# qa-index: App Knowledge Base Construction

## Overview

One-time (or on-app-update) construction of the app knowledge base. This is the foundation of harness engineering: **pre-compute everything so the LLM never needs to explore at runtime.**

## When to Use

- Initial project setup (first time)
- After an app update changes UI screens or navigation
- When `qa-plan` reports missing selectors or stale screen definitions

## Process

```
maestro hierarchy --compact
        |
        v
  Parse UI tree per screen
        |
        v
  Index elements (selector, type, renderer, inputMethod)
        |
        v
  Build flow-graph.json (screen nodes + transition edges)
        |
        v
  Output: knowledge/ directory
```

### Step-by-Step

1. **Connect device** — verify via `adb devices` (Android) or `xcrun simctl list` (iOS).
2. **Launch app** — navigate to each screen manually or via a basic maestro flow.
3. **Dump hierarchy** — for each screen run:
   ```bash
   maestro hierarchy --compact > snapshots/{screen-id}.hierarchy.json
   ```
4. **Parse elements** — extract all interactive elements (buttons, inputs, links). For each element record: `selector`, `type`, `label`, `renderer` (webview/native), `inputMethod`.
5. **LLM label enrichment (1-time)** — for elements missing human-readable labels, use LLM to infer labels from hierarchy context. This is the only LLM usage in indexing.
6. **Build screen JSONs** — write `knowledge/screens/{screen-id}.json` with elements and transitions.
7. **Build element catalog** — aggregate all elements into `knowledge/elements/element-catalog.json`.
8. **Build flow graph** — define nodes (screens) and edges (transitions with actions and renderer type) in `knowledge/flows/flow-graph.json`.
9. **Populate test data** — create `knowledge/test-data/accounts.json` and `phone-numbers.json` with available test data pools.

## Output Structure

```
knowledge/
├── screens/{screen-id}.json      # per-screen element + transition definitions
├── flows/flow-graph.json         # FSM: nodes (screens) + edges (transitions)
├── elements/element-catalog.json # all selectors with metadata
├── test-data/                    # test account and data pools
└── snapshots/                    # raw hierarchy dumps + screenshots
```

## Example Commands

```bash
# Scan a single screen
maestro hierarchy --compact > snapshots/login-phone.hierarchy.json

# Detect renderer type
qa-harness index detect-renderer --device $DEVICE_ID

# Validate knowledge base completeness
qa-harness index validate --dir knowledge/

# Full indexing pipeline
qa-harness index build --device $DEVICE_ID --app com.example.app
```

## Harness Principle

Pre-computation eliminates runtime exploration. Every selector, every screen transition, every renderer type is known before any test runs. The LLM never guesses — it looks up.
