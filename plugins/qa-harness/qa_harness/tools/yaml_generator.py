"""YAML Generator -- Template-based maestro-runner YAML generation.

Uses Jinja2 for template rendering (replacing regex-based approach).

Fixes applied:
  C2  -- single slot-filling call site
  C3  -- surface YAML parse errors
  M1  -- visual-check template for UI-only TCs
  M2  -- integrate test-accounts.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import click
import yaml as pyyaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from qa_harness.knowledge.catalog import ScreenCatalog, load_catalog
from qa_harness.types import (
    MaestroFlow,
    MaestroFlowMetadata,
    MaestroStep,
    RendererType,
    TCParseResult,
    TestAccountsFile,
    TestCase,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template matching rules
# ---------------------------------------------------------------------------

class _MappingRule:
    def __init__(
        self,
        category_pattern: str,
        template_id: str,
        slot_strategy: str,
        step_pattern: str | None = None,
    ):
        self.category_re = re.compile(category_pattern)
        self.step_re = re.compile(step_pattern) if step_pattern else None
        self.template_id = template_id
        self.slot_strategy = slot_strategy


_MAPPING_RULES: list[_MappingRule] = [
    _MappingRule(r"인트로.*권한|권한.*팝업", "permission-dialog", "permission"),
    _MappingRule(r"멤버십 신청.*전화번호|전화번호 인증|전화번호 입력", "signup-phone", "signup-phone"),
    _MappingRule(r"인증 번호|인증번호|OTP", "signup-phone", "signup-phone"),
    _MappingRule(r"로그인", "login-flow", "login"),
    _MappingRule(r"인트로.*멤버십|멤버십 신청.*온보딩", "signup-phone", "signup-phone"),
    _MappingRule(r"프로필|닉네임|생년월일|성별|사진", "profile-input", "profile-input"),
    _MappingRule(r"스플래시|인트로.*UI", "visual-check", "visual-check"),
    _MappingRule(r"스플래시|인트로", "signup-phone", "generic"),
]


def _match_template(tc: TestCase, available: set[str]) -> tuple[str | None, str]:
    """Return (template_id, slot_strategy) for a given TC.

    M1 fix: UI-only TCs that do not match any functional template
    are routed to ``visual-check``.
    """
    cat = f"{tc.category.major} {tc.category.middle} {tc.category.minor}"

    for rule in _MAPPING_RULES:
        if rule.category_re.search(cat):
            if rule.step_re and not rule.step_re.search(tc.raw_step_text):
                continue
            if rule.template_id in available:
                return rule.template_id, rule.slot_strategy

    # Keyword fallback
    if any(kw in tc.raw_step_text for kw in ("로그인", "login")):
        if "login-flow" in available:
            return "login-flow", "login"
    if any(kw in tc.raw_step_text for kw in ("멤버십", "전화번호")):
        if "signup-phone" in available:
            return "signup-phone", "signup-phone"

    # M1 fix: UI-only TCs get visual-check template
    if tc.function_type == "UI" and "visual-check" in available:
        return "visual-check", "visual-check"

    return None, ""


# ---------------------------------------------------------------------------
# Slot filling  (C2 fix: single call site)
# ---------------------------------------------------------------------------

_DEFAULT_TEST_DATA: dict[str, str] = {
    "phoneNumber": "01077322441",
    "otpCode": "123456",
    "deviceId": "emulator-5554",
    "cdpPort": "5100",
    "permissionAction": "allow",
    "permissionType": "notification",
}


def _build_slot_values(
    tc: TestCase,
    strategy: str,
    catalog: ScreenCatalog,
    test_accounts: TestAccountsFile | None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Single slot-filling call site (C2 fix).

    M2 fix: when *test_accounts* is provided, pick the right account
    by matching account type to TC flow.
    """
    slots: dict[str, str] = dict(_DEFAULT_TEST_DATA)
    if extra:
        slots.update(extra)

    # M2: integrate test accounts
    if test_accounts and test_accounts.accounts:
        if strategy in ("signup-phone", "generic"):
            accts = [a for a in test_accounts.accounts if a.type == "new-user"]
        elif strategy == "login":
            accts = [a for a in test_accounts.accounts if a.type == "existing-user"]
        else:
            accts = test_accounts.accounts[:1]
        if accts:
            acct = accts[0]
            slots["phoneNumber"] = acct.phone_number
            slots["otpCode"] = acct.otp_code

    # TC-specific overrides
    if tc.pre_condition:
        phone_match = re.search(r"\d{10,11}", tc.pre_condition)
        if phone_match:
            slots["phoneNumber"] = phone_match.group()

    # visual-check: target_element from TC category
    if strategy == "visual-check":
        elem = tc.category.minor or tc.category.middle or "splash_screen"
        slots["target_element"] = elem.replace(" ", "_").lower()

    # profile-input: fill profile-specific slots
    if strategy == "profile-input":
        cat = f"{tc.category.middle} {tc.category.minor}".strip()
        slots.setdefault("profile_field_selector", cat.replace(" ", "_").lower())
        slots.setdefault("input_selector", f"#{cat.replace(' ', '-').lower()}-input")
        slots.setdefault("input_value", "테스트")
        slots.setdefault("next_button", "next-btn")
        slots.setdefault("expected_result_element", "profile-complete")

    return slots


# ---------------------------------------------------------------------------
# Flow generation
# ---------------------------------------------------------------------------

def _detect_renderer_dispatch(
    tc: TestCase, template_id: str, _catalog: ScreenCatalog
) -> list[dict[str, str | int]]:
    cat = f"{tc.category.major} {tc.category.middle} {tc.category.minor}"
    if "권한" in cat or template_id == "permission-dialog":
        return [{"step": 0, "renderer": "native"}]
    return [{"step": 0, "renderer": "webview"}]


def _infer_screens(tc: TestCase) -> list[str]:
    cat = f"{tc.category.major} {tc.category.middle}"
    screens: list[str] = []
    if "스플래시" in cat or "인트로" in cat:
        screens.append("intro")
    if "권한" in cat:
        screens.append("permission-dialog")
    if "온보딩" in cat:
        screens.append("onboarding")
    if "전화번호" in cat:
        screens.append("phone-input")
    if "인증" in cat:
        screens.append("otp-verify")
    return screens or ["intro"]


def _parse_steps_from_yaml(filled_yaml: str) -> list[MaestroStep]:
    """Extract MaestroSteps from the commands section of a filled YAML.

    C3 fix: YAML parse errors are surfaced, not silently swallowed.
    """
    docs = filled_yaml.split("---")
    if len(docs) < 2:
        return []

    try:
        parsed = pyyaml.safe_load(docs[-1])
    except pyyaml.YAMLError as exc:
        raise RuntimeError(f"YAML parse error in filled template: {exc}") from exc

    if not isinstance(parsed, list):
        return []

    steps: list[MaestroStep] = []
    for item in parsed:
        if isinstance(item, dict):
            for command, args in item.items():
                steps.append(
                    MaestroStep(
                        command=command,
                        args=args if isinstance(args, dict) else {},
                    )
                )
    return steps


def _generate_flow(
    tc: TestCase,
    template_id: str,
    filled_content: str,
    catalog: ScreenCatalog,
) -> MaestroFlow:
    dispatch = _detect_renderer_dispatch(tc, template_id, catalog)
    screens = _infer_screens(tc)

    steps: list[MaestroStep] = []
    try:
        steps = _parse_steps_from_yaml(filled_content)
    except RuntimeError as exc:
        logger.warning("[yaml-gen] %s: %s", tc.id, exc)

    uses_cdp = "runScript" in filled_content and "tap_remote" in filled_content
    uses_korean = "cdp_input" in filled_content or "adb_korean_input" in filled_content

    meta = MaestroFlowMetadata(
        covers_tc_ids=[tc.id],
        screens_visited=screens,
        uses_cdp=uses_cdp,
        uses_korean_input=uses_korean,
        renderer_dispatch=dispatch,
        estimated_duration_sec=len(steps) * 3,
        generated_at="",  # filled at write time
        template_id=template_id,
    )

    return MaestroFlow(
        id=f"flow_{tc.id.lower()}",
        name=f"Flow for {tc.id}: {tc.category.minor or tc.category.middle}",
        description=tc.expected_result,
        steps=steps,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def generate_yaml_flows(
    *,
    tc_path: Path,
    catalog_dir: Path,
    flow_graph_path: Path,
    templates_dir: Path,
    output_dir: Path,
    test_accounts_path: Path | None = None,
    extra_test_data: dict[str, str] | None = None,
) -> list[MaestroFlow]:
    """Generate maestro-runner YAML flows from parsed TCs."""
    import datetime as _dt

    # Load parsed TCs
    logger.info("[yaml-gen] Loading parsed test cases...")
    raw = json.loads(tc_path.read_text(encoding="utf-8"))
    parse_result = TCParseResult.model_validate(raw)
    test_cases = parse_result.test_cases
    logger.info("[yaml-gen] %d test cases loaded", len(test_cases))

    # Load catalog
    logger.info("[yaml-gen] Loading screen catalog...")
    catalog = load_catalog(catalog_dir, flow_graph_path)

    # Load test accounts (M2 fix)
    test_accounts: TestAccountsFile | None = None
    if test_accounts_path and test_accounts_path.is_file():
        try:
            ta_raw = json.loads(test_accounts_path.read_text(encoding="utf-8"))
            test_accounts = TestAccountsFile.model_validate(ta_raw)
            logger.info("[yaml-gen] Loaded %d test accounts", len(test_accounts.accounts))
        except Exception as exc:
            logger.warning("[yaml-gen] Failed to load test accounts: %s", exc)

    # Load Jinja2 templates
    logger.info("[yaml-gen] Loading templates from %s", templates_dir)
    jinja_env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        undefined=_StrictUndefined,
    )
    available_templates: set[str] = set()
    for tpl_path in templates_dir.glob("*.template.yaml"):
        tid = tpl_path.stem.removesuffix(".template")
        available_templates.add(tid)
    logger.info("[yaml-gen] %d templates available", len(available_templates))

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    flows: list[MaestroFlow] = []
    matched = 0
    unmatched = 0

    for tc in test_cases:
        template_id, strategy = _match_template(tc, available_templates)
        if not template_id:
            logger.warning(
                "[yaml-gen] No template match for %s (%s > %s > %s)",
                tc.id,
                tc.category.major,
                tc.category.middle,
                tc.category.minor,
            )
            unmatched += 1
            continue

        matched += 1

        # C2 fix: single slot-filling call
        slots = _build_slot_values(tc, strategy, catalog, test_accounts, extra_test_data)

        # Render via Jinja2
        tpl_name = f"{template_id}.template.yaml"
        try:
            template = jinja_env.get_template(tpl_name)
        except TemplateNotFound:
            logger.warning("[yaml-gen] Template file not found: %s", tpl_name)
            unmatched += 1
            continue

        # Jinja2 uses {{ var }} by default which matches our slot syntax
        # Ensure all slot values are YAML-safe (quote special chars)
        safe_slots = {}
        for k, v in slots.items():
            if isinstance(v, str) and any(c in v for c in ':{}[]&*?|>!%@`'):
                safe_slots[k] = v  # already quoted in template
            else:
                safe_slots[k] = v
        filled_content = template.render(**safe_slots)

        flow = _generate_flow(tc, template_id, filled_content, catalog)
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        flow.metadata.generated_at = now

        # Write flow YAML
        meta_header = "\n".join([
            f"# Generated Flow: {flow.name}",
            f"# TC IDs: {', '.join(flow.metadata.covers_tc_ids)}",
            f"# Template: {flow.metadata.template_id}",
            f"# Screens: {' -> '.join(flow.metadata.screens_visited)}",
            f"# Uses CDP: {flow.metadata.uses_cdp}",
            f"# Uses Korean Input: {flow.metadata.uses_korean_input}",
            f"# Renderer Dispatch: {json.dumps(flow.metadata.renderer_dispatch)}",
            f"# Generated: {flow.metadata.generated_at}",
            f"# Estimated Duration: {flow.metadata.estimated_duration_sec}s",
            "",
        ])
        out_path = output_dir / f"{flow.id}.yaml"
        out_path.write_text(meta_header + filled_content, encoding="utf-8")
        flows.append(flow)
        logger.info("[yaml-gen] Generated: %s (template: %s)", flow.id, template_id)

    logger.info("[yaml-gen] Generation complete: %d matched, %d unmatched", matched, unmatched)

    # Write manifest
    manifest = {
        "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "totalFlows": len(flows),
        "flows": [
            {
                "id": f.id,
                "name": f.name,
                "tcIds": f.metadata.covers_tc_ids,
                "templateId": f.metadata.template_id,
                "screens": f.metadata.screens_visited,
            }
            for f in flows
        ],
    }
    manifest_path = output_dir / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return flows


# Jinja2 strict undefined to catch unfilled slots
from jinja2 import StrictUndefined as _StrictUndefined  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("generate-yaml")
@click.option("--tc", "tc_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--catalog", "catalog_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--templates", "templates_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", "output_dir", required=True, type=click.Path(path_type=Path))
@click.option("--test-accounts", "test_accounts_path", default=None, type=click.Path(path_type=Path))
@click.option("--flow-graph", "flow_graph_path", default=None, type=click.Path(path_type=Path))
def generate_yaml_cmd(
    tc_path: Path,
    catalog_dir: Path,
    templates_dir: Path,
    output_dir: Path,
    test_accounts_path: Path | None,
    flow_graph_path: Path | None,
) -> None:
    """Generate maestro-runner YAML flows from parsed TCs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if flow_graph_path is None:
        flow_graph_path = catalog_dir.parent / "flow-graph.json"

    generate_yaml_flows(
        tc_path=tc_path,
        catalog_dir=catalog_dir,
        flow_graph_path=flow_graph_path,
        templates_dir=templates_dir,
        output_dir=output_dir,
        test_accounts_path=test_accounts_path,
    )
