"""Pydantic v2 models for the QA Automation Harness.

Covers the full pipeline: TC parsing, screen knowledge base, template-based
YAML generation, validation, execution, and reporting.

Fixes applied:
  C1  -- dict instead of Map
  M6  -- proper None handling via pydantic Optional fields
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Test Case types
# ---------------------------------------------------------------------------

class TCPriority(int, Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


TCResult = Literal["Pass", "Fail", "Block", "N/A", "N/T", ""]
DefectSeverity = Literal["Critical", "Major", "Minor", "Trivial", ""]
DefectType = Literal["Bug", "Design", "Etc", ""]


class TCCategory(BaseModel):
    """Category hierarchy: 대분류 > 중분류 > 소분류."""

    major: str = ""
    middle: str = ""
    minor: str = ""


class TCStep(BaseModel):
    """A single numbered test step."""

    number: int = Field(ge=1)
    description: str

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        return v.strip()


class TestCase(BaseModel):
    """One row in the TC spreadsheet."""

    id: str
    priority: TCPriority = TCPriority.LOW
    category: TCCategory = Field(default_factory=TCCategory)
    function_type: str = "UI"
    pre_condition: str = ""
    steps: list[TCStep] = Field(default_factory=list)
    raw_step_text: str = ""
    expected_result: str = ""
    result_android: TCResult = ""
    result_ios: TCResult = ""
    issue_id: str = ""
    defect_severity: DefectSeverity = ""
    defect_type: DefectType = ""
    change_note: str = ""
    remark: str = ""


class TCSummary(BaseModel):
    """Aggregate summary row from the CSV header."""

    platform: Literal["Android", "iOS", "Project"]
    total_tc: int = 0
    coverage: str = ""
    pass_rate: str = ""
    passed: int = Field(0, alias="pass")
    fail: int = 0
    block: int = 0
    na: int = 0
    nt: int = 0
    note: str = ""

    model_config = {"populate_by_name": True}


class TCParseError(BaseModel):
    row: int
    message: str
    raw_data: str | None = None


class TCParseResult(BaseModel):
    summary: list[TCSummary] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    errors: list[TCParseError] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# App Knowledge Base types
# ---------------------------------------------------------------------------

RendererType = Literal["native", "webview"]


class UIElementType(str, Enum):
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    IMAGE = "image"
    CONTAINER = "container"
    DIALOG = "dialog"
    TOAST = "toast"
    KEYBOARD = "keyboard"
    TOGGLE = "toggle"
    DROPDOWN = "dropdown"
    ICON = "icon"


SelectorType = Literal["testID", "text", "point", "cdp-selector"]


class UIElement(BaseModel):
    """A single identifiable UI element on a screen."""

    id: str
    screen: str
    selector: str
    selector_type: SelectorType = Field(alias="selectorType")
    type: UIElementType
    label: str
    renderer_type: RendererType = Field(alias="rendererType")
    cdp_selector: str | None = Field(None, alias="cdpSelector")
    enabled: bool = True
    optional: bool = False

    model_config = {"populate_by_name": True}


class AppScreen(BaseModel):
    """An app screen with its elements and metadata."""

    id: str
    name: str
    description: str = ""
    renderer_type: RendererType = Field(alias="rendererType")
    elements: list[UIElement] = Field(default_factory=list)
    related_tc_ids: list[str] = Field(default_factory=list, alias="relatedTCIds")
    preconditions: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class FlowTransition(BaseModel):
    """Edge in the screen flow graph."""

    from_screen: str = Field(alias="from")
    to_screen: str = Field(alias="to")
    action: str
    element_id: str | None = Field(None, alias="elementId")
    preconditions: list[str] = Field(default_factory=list)
    is_optional: bool = Field(False, alias="isOptional")

    model_config = {"populate_by_name": True}


class FlowGraph(BaseModel):
    """Complete flow graph (state machine)."""

    screens: list[str]
    transitions: list[FlowTransition]
    entry_screen: str = Field(alias="entryScreen")
    terminal_screens: list[str] = Field(default_factory=list, alias="terminalScreens")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Template & YAML Generation types
# ---------------------------------------------------------------------------

SlotSource = Literal["catalog", "testdata", "computed", "literal"]
SlotValueType = Literal["string", "number", "boolean", "selector", "screen-id"]


class TemplateSlot(BaseModel):
    name: str
    type: SlotValueType = "string"
    source: SlotSource = "literal"
    description: str = ""
    required: bool = True
    default_value: str | None = None


class TemplateMetadata(BaseModel):
    id: str
    name: str
    description: str = ""
    slots: list[TemplateSlot] = Field(default_factory=list)
    applicable_categories: list[str] = Field(default_factory=list)
    renderer_type: RendererType | None = None


class MaestroStep(BaseModel):
    command: str
    args: dict[str, Any] = Field(default_factory=dict)
    renderer_type: RendererType | None = None
    comment: str | None = None


class MaestroFlowMetadata(BaseModel):
    covers_tc_ids: list[str] = Field(default_factory=list)
    screens_visited: list[str] = Field(default_factory=list)
    uses_cdp: bool = False
    uses_korean_input: bool = False
    renderer_dispatch: list[dict[str, Any]] = Field(default_factory=list)
    estimated_duration_sec: int = 0
    generated_at: str = ""
    template_id: str = ""


class MaestroFlow(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list[MaestroStep] = Field(default_factory=list)
    metadata: MaestroFlowMetadata = Field(default_factory=MaestroFlowMetadata)


# ---------------------------------------------------------------------------
# Validation types
# ---------------------------------------------------------------------------

ValidationSeverity = Literal["error", "warning", "info"]


class ValidationIssue(BaseModel):
    severity: ValidationSeverity
    code: str
    message: str
    file: str | None = None
    step: int | None = None
    details: dict[str, Any] | None = None


class ValidationStats(BaseModel):
    total_flows: int = 0
    valid_flows: int = 0
    invalid_flows: int = 0
    total_steps: int = 0
    warnings: int = 0
    errors: int = 0


class ValidationResult(BaseModel):
    valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    stats: ValidationStats = Field(default_factory=ValidationStats)


# ---------------------------------------------------------------------------
# Execution & Reporting types
# ---------------------------------------------------------------------------

ExecutionStatus = Literal["passed", "failed", "skipped", "error", "timeout"]


class TestExecution(BaseModel):
    flow_id: str
    tc_ids: list[str] = Field(default_factory=list)
    status: ExecutionStatus
    duration_ms: int = 0
    started_at: str = ""
    finished_at: str = ""
    error_message: str | None = None
    screenshot_path: str | None = None


class BatchResult(BaseModel):
    batch_index: int
    flows: list[TestExecution] = Field(default_factory=list)
    total_duration_ms: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0


class ReportSummary(BaseModel):
    total_tcs: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: str = "0%"
    total_duration_ms: int = 0


class ReportFailure(BaseModel):
    flow_id: str
    tc_ids: list[str] = Field(default_factory=list)
    error: str = ""
    step: int | None = None


class TestReport(BaseModel):
    """Complete test report.  C1 fix: tc_results is a plain dict."""

    id: str
    generated_at: str = ""
    summary: ReportSummary = Field(default_factory=ReportSummary)
    batches: list[BatchResult] = Field(default_factory=list)
    tc_results: dict[str, ExecutionStatus] = Field(default_factory=dict)
    failures: list[ReportFailure] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CDP Bridge types
# ---------------------------------------------------------------------------

class CDPBridgeConfig(BaseModel):
    host: str = "localhost"
    port: int = 5100
    adb_forward_port: int = 9222
    input_server_path: str = "scripts/input_server.py"
    health_check_interval_ms: int = 5000
    connection_timeout_ms: int = 15000


class CDPBridgeStatus(BaseModel):
    running: bool = False
    pid: int | None = None
    port: int = 5100
    connected_devices: list[str] = Field(default_factory=list)
    last_health_check: str | None = None
    uptime: int | None = None


# ---------------------------------------------------------------------------
# Harness Configuration
# ---------------------------------------------------------------------------

class HarnessConfig(BaseModel):
    """Top-level configuration. M8 fix: populated via CLI flags / YAML."""

    catalog_dir: str = "src/knowledge/screens"
    templates_dir: str = "src/templates"
    flow_graph_path: str = "src/knowledge/flow-graph.json"
    output_dir: str = "output/flows"
    reports_dir: str = "output/reports"
    batch_size: int = Field(25, ge=1, le=200)
    device_id: str | None = None
    cdp_bridge: CDPBridgeConfig = Field(default_factory=CDPBridgeConfig)
    html_report: bool = True
    telegram_summary: bool = True
    concurrency: int = Field(1, ge=1, le=16)
    flow_timeout_ms: int = Field(120_000, ge=1000)
    restart_between_batches: bool = True
    test_accounts_path: str = "fixtures/test-accounts.json"

    @field_validator("batch_size")
    @classmethod
    def clamp_batch(cls, v: int) -> int:
        return max(1, min(v, 200))


# ---------------------------------------------------------------------------
# Test Account types  (M2 fix)
# ---------------------------------------------------------------------------

class TestAccountUserInfo(BaseModel):
    name: str = ""
    gender: str = ""
    birth_year: int | None = Field(None, alias="birthYear")
    email: str = ""
    region: str = ""

    model_config = {"populate_by_name": True}


class TestAccount(BaseModel):
    id: str
    type: str
    phone_number: str = Field(alias="phoneNumber")
    otp_code: str = Field(alias="otpCode")
    user_info: TestAccountUserInfo = Field(
        default_factory=TestAccountUserInfo, alias="userInfo"
    )
    locked: bool = False
    locked_by: str | None = Field(None, alias="lockedBy")
    last_used: str | None = Field(None, alias="lastUsed")
    notes: str = ""

    model_config = {"populate_by_name": True}


class TestAccountPool(BaseModel):
    max_concurrent: int = Field(3, alias="maxConcurrent")
    lock_timeout_ms: int = Field(300_000, alias="lockTimeoutMs")
    auto_release_on_failure: bool = Field(True, alias="autoReleaseOnFailure")

    model_config = {"populate_by_name": True}


class TestAccountsFile(BaseModel):
    description: str = ""
    accounts: list[TestAccount] = Field(default_factory=list)
    pool: TestAccountPool = Field(default_factory=TestAccountPool)
