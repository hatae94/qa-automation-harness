# QA Automation Harness

Deterministic test generation and execution framework for hybrid WebView mobile apps. Built on the **harness engineering** paradigm: LLM plans once, harness validates, maestro-runner executes deterministically.

## Architecture

```
                          qa-harness CLI (Python/Click)
                                   |
       ┌───────────┬───────────┬───┴───┬───────────┬───────────┐
       v           v           v       v           v           v
    qa-index    qa-plan     qa-run  qa-report  qa-triage  qa-orchestrate
   (build KB)  (YAML gen)  (exec)  (reports)  (analyze)  (full pipeline)
       |           |           |       |           |
       |      LLM: slot    LLM: 0%    |      LLM: <10%
       |      fill ONLY                |      (last resort)
       v           v           v       v
   knowledge/  src/flows/  results/  results/
   (screens,   (validated  (JUnit    (HTML,
    elements,   YAML)       XML)      JSON,
    flow graph)                       Telegram)
```

### Core Principle

**"LLM plans, harness validates, maestro-runner executes."**

- LLM fills template slots (1 call per TC, offline)
- All YAML is validated against the App Knowledge Base before execution
- Runtime is 100% deterministic: no LLM, no exploration, no non-determinism

## Prerequisites

- **Python 3.11+**
- **maestro-runner** (mobile UI automation framework)
- **ADB** (Android Debug Bridge) for Android device interaction
- **Device or emulator** connected and visible via `adb devices`

## Installation

### 방법 1: Marketplace로 설치 (권장 — clone 불필요)

다른 노트북에서 GitHub 레포 URL만으로 설치할 수 있습니다.

```bash
# 1. Marketplace 등록 (1회만)
claude plugin marketplace add hatae94/qa-automation-harness

# 2. 플러그인 설치
claude plugin install qa-automation-harness@hatae94-qa-automation-harness

# 설치 확인 — /qa-automation-harness:qa-run 등 skill 사용 가능
claude

# 삭제
claude plugin uninstall qa-automation-harness@hatae94-qa-automation-harness
```

또는 `~/.claude/settings.json`에 직접 등록:

```json
{
  "extraKnownMarketplaces": {
    "qa-harness": {
      "source": { "source": "github", "repo": "hatae94/qa-automation-harness" }
    }
  },
  "enabledPlugins": {
    "qa-automation-harness@qa-harness": true
  }
}
```

### 방법 2: Clone + 로컬 설치

Python CLI 도구도 함께 사용하려면 clone이 필요합니다.

```bash
# 1. 레포 클론
git clone git@github.com:hatae94/qa-automation-harness.git
cd qa-automation-harness

# 2. Python 패키지 설치
pip install -e ".[dev]"

# 3. Claude Code 플러그인으로 로드
claude --plugin-dir ./qa-automation-harness

# 4. 설치 확인
qa-harness --help
```

### Updating the Plugin

```bash
claude plugin update qa-harness@qa-harness
```

### SSH 설정 (회사 노트북에서 개인 GitHub 사용)

```bash
# ~/.ssh/config에 추가
Host personal
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_personal  # 개인 SSH 키

# 클론 시 personal 호스트 사용
git clone personal:hatae94/qa-automation-harness.git
```

## Quick Start

```bash
# 1. Build the app knowledge base (one-time, or after app update)
qa-harness index build --device emulator-5554 --app com.example.app

# 2. Parse test cases from CSV/Excel
qa-harness plan parse -i testcases.csv -o parsed.json

# 3. Generate validated YAML flows (LLM slot-filling happens here)
qa-harness plan generate --tc parsed.json

# 4. Validate generated flows against knowledge base
qa-harness plan validate

# 5. Execute tests deterministically (zero LLM)
qa-harness run --tier smoke --dry-run    # dry run first
qa-harness run --tier smoke              # real execution

# 6. Generate reports
qa-harness report generate --format all

# Or run the full pipeline in one command:
qa-harness orchestrate --input testcases.csv --tier core
```

## CLI Reference

The `qa-harness` CLI is built with Click. All commands are also accessible via `python -m qa_harness`.

### Top-Level Commands

| Command | Description |
|---------|-------------|
| `qa-harness index` | Build/update the app knowledge base |
| `qa-harness plan` | Parse TCs and generate validated YAML flows |
| `qa-harness run` | Execute test flows via maestro-runner |
| `qa-harness report` | Generate reports from execution results |
| `qa-harness triage` | Analyze test failures |
| `qa-harness orchestrate` | Run the full pipeline end-to-end |

### Index Commands

```bash
qa-harness index build --device DEVICE_ID --app PACKAGE_NAME
qa-harness index detect-renderer --device DEVICE_ID
qa-harness index validate --dir knowledge/
```

### Plan Commands

```bash
qa-harness plan parse -i INPUT_CSV -o OUTPUT_JSON
qa-harness plan generate --tc PARSED_JSON
qa-harness plan validate
qa-harness plan full -i INPUT_CSV          # parse + generate + validate
```

### Run Commands

```bash
qa-harness run --tier [smoke|core|full]
qa-harness run --tier core --device DEVICE_ID
qa-harness run --dry-run
qa-harness run cdp-start --device DEVICE_ID
qa-harness run cdp-health
qa-harness run cdp-stop
```

### Report Commands

```bash
qa-harness report generate
qa-harness report generate --format [html|telegram|json|all]
qa-harness report generate --tc-map src/flows/_manifest.json
```

### Triage Commands

```bash
qa-harness triage analyze
qa-harness triage analyze --tc-id TC_ID
qa-harness triage add-known-issue --pattern "PATTERN" --issue ISSUE_ID
qa-harness triage summary
```

### Orchestrate Commands

```bash
qa-harness orchestrate --input INPUT_CSV --tier [smoke|core|full]
qa-harness orchestrate --input INPUT_CSV --stage [plan|run|report]
qa-harness orchestrate --input INPUT_CSV --tier full --fresh
```

## Project Structure

```
qa-automation-harness/
├── qa_harness/                        # Python package (pip installable)
│   ├── __init__.py                    # Package version
│   ├── cli.py                         # Click-based CLI entry point
│   ├── models.py                      # Pydantic models (TestCase, Screen, FlowGraph, etc.)
│   ├── tc_parser.py                   # CSV/Excel TC parser
│   ├── yaml_generator.py             # Template-based YAML generator (Jinja2)
│   ├── yaml_validator.py             # Pre-execution validation rules
│   ├── batch_runner.py               # Maestro-runner orchestration (25-batch)
│   ├── cdp_bridge.py                 # CDP bridge lifecycle manager
│   ├── renderer_dispatch.py          # WebView/Native detection per screen
│   ├── report_generator.py           # HTML/Telegram/JSON report generator
│   └── templates/                     # Immutable Jinja2 YAML templates
│       ├── login-flow.template.yaml
│       ├── signup-phone.template.yaml
│       ├── permission-dialog.template.yaml
│       ├── korean-input-native.template.yaml
│       └── korean-input-webview.template.yaml
├── .claude-plugin/
│   └── plugin.json                    # Claude Code plugin manifest
├── skills/                            # Claude CLI skills (plugin root)
│   ├── README.md
│   ├── qa-index/SKILL.md
│   ├── qa-plan/SKILL.md
│   ├── qa-run/SKILL.md
│   ├── qa-report/SKILL.md
│   ├── qa-orchestrate/SKILL.md
│   └── qa-triage/SKILL.md
├── tests/                             # pytest test suite
├── src/
│   ├── knowledge/                     # App knowledge base
│   │   ├── screens/                   # Per-screen element definitions (JSON)
│   │   ├── flows/flow-graph.json      # Screen state machine (FSM)
│   │   └── elements/element-catalog.json
│   ├── flows/                         # Generated YAML flows (output, gitignored)
│   └── reports/                       # Generated reports (output, gitignored)
├── knowledge/                         # Alternative KB location (project root)
├── results/                           # Execution results
├── fixtures/                          # Sample data and test accounts
│   ├── test-accounts.json
│   └── sample-tc.json
├── scripts/                           # Shell helpers
│   └── qa-harness.sh
├── pyproject.toml                     # Python project config (hatchling build)
├── .gitignore
└── README.md
```

## Development Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=qa_harness --cov-report=term-missing

# Run a specific test
pytest tests/test_tc_parser.py -v

# Type checking (optional, with mypy)
mypy qa_harness/
```

## Configuration

The harness uses a layered configuration approach:

| Config Source | Purpose | Example |
|--------------|---------|---------|
| `pyproject.toml` | Package metadata, dependencies | Python version, deps |
| `knowledge/` directory | App-specific screen/element data | Selectors, flow graph |
| `fixtures/test-accounts.json` | Test data pools | Phone numbers, accounts |
| `known-issues.json` | Error-to-issue mapping for triage | Pattern matching rules |
| Environment variables | Device and runtime config | `DEVICE_ID`, `APP_PACKAGE` |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVICE_ID` | ADB device serial | First connected device |
| `APP_PACKAGE` | Android app package name | (required for index) |
| `CDP_PORT` | Chrome DevTools Protocol port | `9222` |
| `BATCH_SIZE` | Tests per execution batch | `25` |

## Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        qa-harness orchestrate                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │ TC CSV   │───>│ qa-plan  │───>│ qa-run   │───>│ qa-report    │  │
│  │ (input)  │    │ parse +  │    │ maestro  │    │ HTML/JSON/   │  │
│  │          │    │ generate │    │ executor │    │ Telegram     │  │
│  └──────────┘    └────┬─────┘    └──────────┘    └──────┬───────┘  │
│                       │                                  │          │
│                       │ LLM: slot                        │          │
│                       │ fill ONLY                        v          │
│                       v                           ┌──────────────┐  │
│                 ┌──────────┐                      │ qa-triage    │  │
│                 │knowledge/│                      │ (optional)   │  │
│                 │ (from    │                      │ rules-based  │  │
│                 │ qa-index)│                      └──────────────┘  │
│                 └──────────┘                                        │
│                                                                     │
│  LLM involvement: plan stage ONLY (1 call per TC for slot filling) │
│  Runtime execution: 100% deterministic, 0% LLM                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Why Harness Engineering?

The PoC (29 issues documented) proved that "LLM-in-the-loop" fails for mobile QA automation:
- LLM explores wrong paths at runtime
- YAML regeneration loops on failure
- Non-deterministic results (same input, different output)
- Unacceptable speed (9-15 min per TC vs. 1-2 min target)

The harness approach eliminates all runtime non-determinism.

### Why Batches of 25?

PoC issue #1040: maestro-runner driver crashes after 55+ consecutive test executions. Batches of 25 with driver restart between batches prevent this.

### Why Renderer Dispatch?

PoC issue #1873: The app is hybrid (WebView + Native). Applying CDP to all screens fails when hitting native screens (photo gallery, permission dialogs). Each screen must be classified and use the correct interaction method.

### Why Korean Input Workarounds?

PoC issues #918, #1507: Standard `inputText` cannot handle Korean characters in WebView (React `onChange` not triggered) or native (HID keycode mapping missing). Two workarounds:
- **WebView**: CDP `nativeValueSetter` + `dispatchEvent` (single `Runtime.evaluate` call to avoid race conditions)
- **Native**: ADB clipboard paste

## PoC Lessons Encoded

| PoC Issue | Lesson | Encoded In |
|-----------|--------|------------|
| #1643 | maestro-runner lacks WebView CDP integration | CDP bridge manager, runScript templates |
| #1873 | WebView/Native must be dispatched separately | `renderer_dispatch.py`, screen catalog |
| #1763 | CDP input race condition (2nd input fails) | korean-input-webview template (single evaluate) |
| #1687 | ADB forward port stale connections | `cdp_bridge.py` port cleanup |
| #1040 | Driver crashes after 55+ flows | `batch_runner.py` (25-flow batches) |
| #252 | 88% testID labels missing | Screen catalog with explicit labels |
| #1691 | Multi-device CDP routing | DEVICE env var in all CDP templates |
