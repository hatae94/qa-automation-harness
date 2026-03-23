---
name: qa-testid
description: Use when injecting, auditing, or exporting testIDs for React Native and WebView components -- automates testID coverage for QA automation
context: fork
agent: general-purpose
allowed-tools: Bash(*), Read, Write, Glob, Grep
---

# qa-testid Skill

Automates testID / data-testid injection, auditing, and export for hybrid mobile apps
(React Native + WebView).

## Commands

```bash
# Audit testID coverage for RN source
qa-harness testid audit --source <rn-src-path> --type rn

# Audit testID coverage for WebView source
qa-harness testid audit --source <web-src-path> --type web

# Dry-run inject (plan only, no file changes)
qa-harness testid inject --source <path> --type [rn|web] --dry-run

# Apply inject (modifies files)
qa-harness testid inject --source <path> --type [rn|web] --rules fixtures/testid-rules.yaml --apply

# Export testID manifest as JSON
qa-harness testid export --source <path> --type [rn|web] --output testid-manifest.json

# Show what would change (alias for inject --dry-run)
qa-harness testid diff --source <path> --type [rn|web]
```

## Standalone Usage

```bash
python -m qa_harness.tools.testid_injector audit --source <path> --type rn
python -m qa_harness.tools.testid_injector inject --source <path> --type web --dry-run
python -m qa_harness.tools.testid_injector export --source <path> --type rn --output manifest.json
```

## Naming Convention

Format: `{screen}.{section}.{element}-{type}`

- Charset: `[a-z0-9._-]` only
- Max length: 64 characters
- RN native screens: `native.{screen}.{element}-{type}`
- WebView wrapper: `webview.{screen}`
- Web pages: `{page}.{section}.{element}-{type}`

## Type Suffixes

| Suffix | Components |
|--------|-----------|
| `-btn` | Button, Pressable, TouchableOpacity |
| `-input` | TextInput, TextField, PhoneTextInput, input, textarea |
| `-link` | a, Link |
| `-select` | Select, Dropdown |
| `-checkbox` | CheckBox |
| `-switch` | Switch |
| `-nav` | TopNavigation, Header |
| `-modal` | BottomSheet, Modal |
| `-list` | FlatList, ScrollView |
| `-text` | Typography (error/title only) |

## Safety Rules

- NEVER override existing testID or data-testid attributes
- Always run `--dry-run` first to review changes
- Only inject on interactive/targetable components
- Validate charset compliance before applying
