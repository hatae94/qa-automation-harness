# QA Automation Skills

## Harness Engineering Philosophy

> "LLM이 성공할 수밖에 없는 환경을 구축한다."
> (Build an environment where the LLM cannot fail.)

These skills implement the **harness engineering paradigm**: pre-compute everything, constrain the LLM to slot-filling only, and execute deterministically. The LLM is a planner, not an executor.

### Core Principles

1. **LLM Zero at Runtime** — test execution involves zero LLM calls
2. **Pre-computation Everything** — all screens, selectors, and flows indexed before any test runs
3. **Template-Only Generation** — LLM fills slots in immutable templates; never generates YAML structure
4. **Validate Before Execute** — every LLM output passes static validation before reaching the executor
5. **Deterministic Recovery** — failure handling uses rules, not LLM judgment

## Skill Map

```
qa-index ──> qa-plan ──> qa-run ──> qa-report
  (KB)      (YAML gen)   (exec)    (results)
              |                        |
              |  LLM here ONLY         |  optional
              v                        v
         slot filling             qa-triage
                                  (analysis)

qa-orchestrate: runs the full pipeline end-to-end
```

## Skills Overview

| Skill | Purpose | LLM Usage |
|-------|---------|-----------|
| [qa-index](qa-index/SKILL.md) | Build app knowledge base (screens, elements, flow graph) | 1-time label enrichment only |
| [qa-plan](qa-plan/SKILL.md) | Convert TCs to validated YAML via template slot-filling | **Yes** — the single LLM touchpoint |
| [qa-run](qa-run/SKILL.md) | Execute tests via maestro-runner deterministically | **None (0%)** |
| [qa-report](qa-report/SKILL.md) | Generate reports from JUnit XML results | None |
| [qa-orchestrate](qa-orchestrate/SKILL.md) | Full pipeline orchestrator (parse > plan > run > report) | Only during plan stage |
| [qa-triage](qa-triage/SKILL.md) | Analyze failures with rules-based classification | Last resort only (<10% of failures) |

## CLI Reference

All skills are accessible via the `qa-harness` CLI (Python/Click):

```bash
# Install the package
pip install -e .

# Top-level commands
qa-harness index ...        # Knowledge base construction
qa-harness plan ...         # TC parsing + YAML generation
qa-harness run ...          # Deterministic test execution
qa-harness report ...       # Result collection and reporting
qa-harness orchestrate ...  # Full pipeline orchestration
qa-harness triage ...       # Failure analysis

# Or via Python module
python -m qa_harness index ...
python -m qa_harness plan ...
```

## Data Flow

```
TC CSV
  |
  v
qa-plan ──reads──> knowledge/ (from qa-index)
  |                templates/ (immutable Jinja2/YAML templates)
  |
  v
flows/*.yaml  (validated, immutable)
  |
  v
qa-run ──uses──> maestro-runner + CDP bridge
  |              (LLM involvement: 0%)
  v
results/ (JUnit XML + screenshots)
  |
  v
qa-report ──produces──> HTML, Telegram summary, JSON
  |
  v
qa-triage (if failures exist)
```

## Key Directories

| Path | Contents | Managed By |
|------|----------|-----------|
| `knowledge/` | Screens, flow graph, element catalog, test data | qa-index |
| `qa_harness/templates/` | Immutable Jinja2/YAML templates (git-managed) | Human (manual) |
| `flows/` | Generated + validated YAML per TC | qa-plan |
| `results/` | Execution results, screenshots, reports | qa-run, qa-report |
| `known-issues.json` | Error pattern to tracked issue mapping | qa-triage |

## Project Structure (Python)

```
qa-automation-harness/
├── qa_harness/              # Python package
│   ├── __init__.py
│   ├── cli.py               # Click-based CLI entry point
│   ├── models.py            # Pydantic models (TestCase, Screen, etc.)
│   ├── tc_parser.py         # CSV/Excel parser
│   ├── yaml_generator.py    # Template-based YAML generator
│   ├── yaml_validator.py    # Pre-execution validation
│   ├── batch_runner.py      # Maestro-runner orchestration
│   ├── cdp_bridge.py        # CDP bridge lifecycle
│   ├── renderer_dispatch.py # WebView/Native detection
│   ├── report_generator.py  # HTML/Telegram/JSON reports
│   └── templates/           # Jinja2 YAML templates
├── tests/                   # pytest test suite
├── knowledge/               # App knowledge base (generated)
├── fixtures/                # Sample data and test accounts
├── scripts/                 # Shell helpers
├── pyproject.toml           # Python project config (hatchling)
└── README.md
```

## Why This Architecture

The previous LLM-in-the-loop approach failed in stakeholder demo: the LLM explored wrong screens, regenerated YAML on every retry, and produced different results for identical inputs. maestro-runner itself was fast — the LLM runtime involvement was the bottleneck.

Harness engineering fixes this by moving all LLM work offline (1 call per TC for slot-filling) and making execution 100% deterministic. Same input always produces the same result.
