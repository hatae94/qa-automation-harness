"""Selector manifest generator for the Cascading Selector Strategy.

Reads parsed TC JSON and source code to determine the best selector strategy
for each TC step element:
  1. text match (Korean text found in code)
  2. testID match (data-testid or testID exists)
  3. manual_review (neither found)

Output: selector-manifest.json with deterministic selector lookups.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step extraction patterns
# ---------------------------------------------------------------------------

# TC step patterns: extract element text and action type
STEP_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # [버튼텍스트] 버튼 클릭 / [텍스트] 클릭 / [텍스트] 선택 / [텍스트] 탭
    (re.compile(r'\[(.+?)\]\s*(버튼\s*)?(클릭|선택|탭)'), 'button', 'tap'),
    # 앱 실행 / 앱 종료 (must come before generic patterns)
    (re.compile(r'(앱|알파)\s*(앱\s*)?(실행|종료|재실행)'), 'app', 'lifecycle'),
    # 앱 종료 후 XX (lifecycle)
    (re.compile(r'앱\s*종료\s*후'), 'app', 'lifecycle'),
    # Navigation chain: 인트로 > 앱 추적 권한 팝업 > 알림 받기(허용)
    # Extract the LAST segment after the final >
    (re.compile(r'(?:.*>\s*)(.+?)\s*$'), 'navigation_chain', 'tap'),
    # 전화번호 입력 / OO 입력
    (re.compile(r'(.+?)\s*입력'), 'input', 'input'),
    # > 페이지 이동 / OO 페이지 진입 / OO 화면 이동
    (re.compile(r'(.+?)\s*(페이지|화면)\s*(이동|노출|진입)'), 'navigation', 'assert'),
    # 팝업 노출 / 바텀 팝업 노출 / 토스트 노출
    (re.compile(r'(.+?)\s*(팝업|바텀\s*팝업|토스트|바텀시트)\s*노출'), 'popup', 'assert'),
    # OO 노출 확인 (generic assertion)
    (re.compile(r'(.+?)\s*노출\s*(확인)?'), 'element', 'assert'),
    # 뒤로가기 / 닫기
    (re.compile(r'(뒤로가기|닫기|<\s*아이콘)'), 'navigation_action', 'tap'),
    # 스와이프 / 스크롤
    (re.compile(r'(스와이프|스크롤|드래그)\s*(좌|우|상|하|왼쪽|오른쪽)?'), 'gesture', 'swipe'),
]


@dataclass
class StepElement:
    """Extracted element reference from a TC step."""
    text: str
    element_type: str  # button, input, navigation, popup, etc.
    action: str  # tap, input, assert, lifecycle, swipe


@dataclass
class SelectorEntry:
    """A single selector manifest entry for one TC step."""
    tc_id: str
    step_number: int
    step_description: str
    element_type: str
    action: str
    extracted_text: str | None
    selectors: dict  # primary, fallback, last_resort
    platform: str  # webview, rn, or unknown
    text_match_possible: bool
    text_found_in_code: bool
    testid_available: bool
    source_file: str | None = None
    notes: str | None = None


@dataclass
class SelectorManifest:
    """Full selector manifest for all TCs."""
    manifest_version: str = "1.0.0"
    strategy: str = "cascading-selector"
    generated_at: str = ""
    tc_count: int = 0
    entries: list[SelectorEntry] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Source code index
# ---------------------------------------------------------------------------

@dataclass
class SourceIndex:
    """Index of text and testIDs found in source code."""
    # Korean text -> list of (file_path, line_number)
    korean_texts: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # testID value -> (file_path, line_number)
    testid_map: dict[str, tuple[str, int]] = field(default_factory=dict)
    # screen_name -> list of testIDs
    screen_testids: dict[str, list[str]] = field(default_factory=dict)


def _build_source_index(source_dir: Path, source_type: str) -> SourceIndex:
    """Build an index of Korean texts and testIDs from source files."""
    index = SourceIndex()

    if not source_dir.exists():
        logger.warning("Source directory does not exist: %s", source_dir)
        return index

    testid_pattern = (
        re.compile(r'data-testid\s*=\s*["\']([^"\']+)["\']')
        if source_type == "web"
        else re.compile(r'testID\s*=\s*["\']([^"\']+)["\']')
    )
    # Match Korean text in JSX children or string props
    korean_re = re.compile(r'[>\'"]\s*([가-힣][가-힣\s.,?!·~()]*[가-힣.?!)])\s*[<\'"]')
    # Also match Korean text in string literals (error messages, titles, etc.)
    korean_string_re = re.compile(r'[\'"]([가-힣][가-힣\s.,?!·~()0-9]*[가-힣.?!0-9)])[\'"]')

    skip_patterns = {"node_modules", "__tests__", ".test.", ".stories.", ".d.ts"}

    for fpath in sorted(source_dir.rglob("*.tsx")):
        path_str = str(fpath)
        if any(skip in path_str for skip in skip_patterns):
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        rel_path = str(fpath.relative_to(source_dir.parent.parent))

        for line_no, line in enumerate(content.split('\n'), 1):
            # Index testIDs
            for m in testid_pattern.finditer(line):
                tid = m.group(1)
                index.testid_map[tid] = (rel_path, line_no)

            # Index Korean texts
            for pattern in (korean_re, korean_string_re):
                for m in pattern.finditer(line):
                    text = m.group(1).strip()
                    if len(text) >= 2:
                        if text not in index.korean_texts:
                            index.korean_texts[text] = []
                        index.korean_texts[text].append((rel_path, line_no))

    return index


# ---------------------------------------------------------------------------
# Step parsing
# ---------------------------------------------------------------------------

def _extract_step_element(step_desc: str) -> StepElement | None:
    """Extract the UI element reference from a TC step description."""
    for pattern, elem_type, action in STEP_PATTERNS:
        m = pattern.search(step_desc)
        if m:
            text = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ""
            # Clean brackets
            text = text.strip('[]')
            if text:
                return StepElement(text=text, element_type=elem_type, action=action)
            return StepElement(text=step_desc, element_type=elem_type, action=action)

    # Fallback: return the whole step as element text
    return StepElement(text=step_desc, element_type="unknown", action="unknown")


def _find_text_in_index(text: str, index: SourceIndex) -> tuple[bool, str | None]:
    """Search for Korean text in the source index. Returns (found, source_file)."""
    # Exact match
    if text in index.korean_texts:
        locations = index.korean_texts[text]
        return True, locations[0][0] if locations else None

    # Fuzzy: try contains match (for slight variations)
    for code_text, locations in index.korean_texts.items():
        if text in code_text or code_text in text:
            return True, locations[0][0] if locations else None

    return False, None


def _find_testid_for_element(
    element: StepElement,
    tc_category: dict | None,
    index: SourceIndex,
) -> tuple[bool, str | None, str | None]:
    """Try to find a matching testID for the element.

    Returns (found, testid_value, source_file).
    """
    # Build search terms from element text and category
    search_terms = [element.text.lower()]
    if tc_category:
        for val in tc_category.values():
            if val:
                search_terms.append(val.lower())

    for tid, (file_path, _line) in index.testid_map.items():
        tid_lower = tid.lower()
        for term in search_terms:
            # Check if any search term is contained in the testID
            term_parts = term.replace(' ', '-')
            if term_parts in tid_lower or any(
                part in tid_lower for part in term.split() if len(part) >= 2
            ):
                return True, tid, file_path

    return False, None, None


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

def generate_manifest(
    tc_path: Path,
    webview_source: Path | None = None,
    rn_source: Path | None = None,
    output_path: Path | None = None,
) -> SelectorManifest:
    """Generate a selector manifest from parsed TCs and source code.

    Args:
        tc_path: Path to parsed TC JSON (from parse-tc command).
        webview_source: Path to WebView source (e.g., vrew web-server pages).
        rn_source: Path to React Native source (e.g., alphaz/src).
        output_path: Optional output path for the manifest JSON.

    Returns:
        SelectorManifest with entries for all TC steps.
    """
    # Load parsed TCs
    tc_data = json.loads(tc_path.read_text(encoding="utf-8"))
    test_cases = tc_data.get("test_cases", [])

    logger.info("[manifest] Loading %d test cases from %s", len(test_cases), tc_path)

    # Build source indices
    web_index = _build_source_index(webview_source, "web") if webview_source else SourceIndex()
    rn_index = _build_source_index(rn_source, "rn") if rn_source else SourceIndex()

    logger.info(
        "[manifest] Source index: %d Korean texts (web), %d testIDs (web), "
        "%d Korean texts (rn), %d testIDs (rn)",
        len(web_index.korean_texts), len(web_index.testid_map),
        len(rn_index.korean_texts), len(rn_index.testid_map),
    )

    manifest = SelectorManifest(
        generated_at=datetime.now(timezone.utc).isoformat(),
        tc_count=len(test_cases),
    )

    stats = {
        "total_steps": 0,
        "text_match_count": 0,
        "testid_match_count": 0,
        "manual_review_count": 0,
        "lifecycle_skip_count": 0,
        "text_match_rate": 0.0,
        "automation_ready_rate": 0.0,
    }

    for tc in test_cases:
        tc_id = tc.get("id", "unknown")
        steps = tc.get("steps", [])
        category = tc.get("category")

        for step in steps:
            step_num = step.get("number", 0)
            step_desc = step.get("description", "")

            if not step_desc.strip():
                continue

            stats["total_steps"] += 1
            element = _extract_step_element(step_desc)

            if not element:
                continue

            # Lifecycle actions (app launch/kill) don't need selectors
            if element.action == "lifecycle":
                stats["lifecycle_skip_count"] += 1
                entry = SelectorEntry(
                    tc_id=tc_id,
                    step_number=step_num,
                    step_description=step_desc,
                    element_type=element.element_type,
                    action=element.action,
                    extracted_text=element.text,
                    selectors={
                        "primary": {"type": "lifecycle", "value": element.text},
                    },
                    platform="rn",
                    text_match_possible=False,
                    text_found_in_code=False,
                    testid_available=False,
                    notes="App lifecycle action - no selector needed",
                )
                manifest.entries.append(entry)
                continue

            # Search both indices
            text_found_web, web_file = _find_text_in_index(element.text, web_index)
            text_found_rn, rn_file = _find_text_in_index(element.text, rn_index)
            text_found = text_found_web or text_found_rn

            testid_found_web, web_tid, web_tid_file = _find_testid_for_element(
                element, category, web_index,
            )
            testid_found_rn, rn_tid, rn_tid_file = _find_testid_for_element(
                element, category, rn_index,
            )

            # Determine platform
            if text_found_web or testid_found_web:
                platform = "webview"
                source_file = web_file or web_tid_file
            elif text_found_rn or testid_found_rn:
                platform = "rn"
                source_file = rn_file or rn_tid_file
            else:
                platform = "unknown"
                source_file = None

            # Build selectors with cascading priority
            selectors: dict = {}
            if text_found:
                selectors["primary"] = {"type": "text", "value": element.text}
                stats["text_match_count"] += 1
                if testid_found_web or testid_found_rn:
                    tid = web_tid or rn_tid
                    selectors["fallback"] = {"type": "testID", "value": tid}
                    stats["testid_match_count"] += 1
            elif testid_found_web or testid_found_rn:
                tid = web_tid or rn_tid
                selectors["primary"] = {"type": "testID", "value": tid}
                stats["testid_match_count"] += 1
            else:
                selectors["primary"] = {"type": "manual_review", "value": None}
                stats["manual_review_count"] += 1

            entry = SelectorEntry(
                tc_id=tc_id,
                step_number=step_num,
                step_description=step_desc,
                element_type=element.element_type,
                action=element.action,
                extracted_text=element.text,
                selectors=selectors,
                platform=platform,
                text_match_possible=text_found,
                text_found_in_code=text_found,
                testid_available=testid_found_web or testid_found_rn,
                source_file=source_file,
            )
            manifest.entries.append(entry)

    # Calculate rates
    actionable = stats["total_steps"] - stats["lifecycle_skip_count"]
    if actionable > 0:
        stats["text_match_rate"] = round(stats["text_match_count"] / actionable * 100, 1)
        auto_ready = stats["text_match_count"] + stats["testid_match_count"]
        # Avoid double-counting: if text+testID both found, that's one auto-ready step
        unique_auto = stats["text_match_count"] + (
            stats["testid_match_count"] - min(stats["text_match_count"], stats["testid_match_count"])
        )
        # Actually auto_ready = steps that have at least one selector
        auto_ready_count = actionable - stats["manual_review_count"]
        stats["automation_ready_rate"] = round(auto_ready_count / actionable * 100, 1)

    manifest.stats = stats

    # Write output
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_dict = {
            "manifest_version": manifest.manifest_version,
            "strategy": manifest.strategy,
            "generated_at": manifest.generated_at,
            "tc_count": manifest.tc_count,
            "stats": manifest.stats,
            "entries": [
                {
                    "tc_id": e.tc_id,
                    "step_number": e.step_number,
                    "step_description": e.step_description,
                    "element_type": e.element_type,
                    "action": e.action,
                    "extracted_text": e.extracted_text,
                    "selectors": e.selectors,
                    "platform": e.platform,
                    "text_match_possible": e.text_match_possible,
                    "text_found_in_code": e.text_found_in_code,
                    "testid_available": e.testid_available,
                    "source_file": e.source_file,
                    "notes": e.notes,
                }
                for e in manifest.entries
            ],
        }
        output_path.write_text(
            json.dumps(manifest_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("[manifest] Written to %s", output_path)

    return manifest


def validate_manifest(manifest_path: Path) -> dict:
    """Validate a selector manifest for completeness and consistency.

    Returns a dict with validation results.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])

    issues: list[str] = []
    manual_review_entries: list[dict] = []

    for entry in entries:
        selectors = entry.get("selectors", {})
        primary = selectors.get("primary", {})

        if primary.get("type") == "manual_review":
            manual_review_entries.append(entry)

        # Check for empty selector values
        if primary.get("type") in ("text", "testID") and not primary.get("value"):
            issues.append(
                f"{entry['tc_id']} step {entry['step_number']}: "
                f"primary selector type={primary['type']} but value is empty"
            )

    return {
        "valid": len(issues) == 0,
        "total_entries": len(entries),
        "manual_review_count": len(manual_review_entries),
        "issues": issues,
        "manual_review_tc_ids": [e["tc_id"] for e in manual_review_entries],
    }


def print_manifest_stats(manifest_path: Path) -> None:
    """Print summary statistics from a selector manifest."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    stats = data.get("stats", {})
    entries = data.get("entries", [])

    print(f"\n{'=' * 60}")
    print(f"  Selector Manifest Statistics")
    print(f"  Generated: {data.get('generated_at', 'unknown')}")
    print(f"{'=' * 60}\n")

    print(f"  Total TCs:              {data.get('tc_count', 0)}")
    print(f"  Total Steps:            {stats.get('total_steps', 0)}")
    print(f"  Text Match:             {stats.get('text_match_count', 0)}")
    print(f"  TestID Match:           {stats.get('testid_match_count', 0)}")
    print(f"  Manual Review Needed:   {stats.get('manual_review_count', 0)}")
    print(f"  Lifecycle (skip):       {stats.get('lifecycle_skip_count', 0)}")
    print(f"  Text Match Rate:        {stats.get('text_match_rate', 0):.1f}%")
    print(f"  Automation Ready Rate:  {stats.get('automation_ready_rate', 0):.1f}%")
    print()

    # Platform breakdown
    platform_counts: dict[str, int] = {}
    element_type_counts: dict[str, int] = {}
    for entry in entries:
        p = entry.get("platform", "unknown")
        platform_counts[p] = platform_counts.get(p, 0) + 1
        et = entry.get("element_type", "unknown")
        element_type_counts[et] = element_type_counts.get(et, 0) + 1

    print("  Platform breakdown:")
    for p, count in sorted(platform_counts.items()):
        print(f"    {p:<15} {count:>5}")

    print("\n  Element type breakdown:")
    for et, count in sorted(element_type_counts.items(), key=lambda x: -x[1]):
        print(f"    {et:<20} {count:>5}")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Standalone CLI for manifest_generator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Selector manifest generator for Cascading Selector Strategy"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = sub.add_parser("generate", help="Generate selector manifest")
    p_gen.add_argument("--tc", required=True, type=Path, help="Parsed TC JSON")
    p_gen.add_argument("--webview-source", type=Path, default=None)
    p_gen.add_argument("--rn-source", type=Path, default=None)
    p_gen.add_argument("--output", type=Path, required=True)

    # validate
    p_val = sub.add_parser("validate", help="Validate manifest")
    p_val.add_argument("--manifest", required=True, type=Path)

    # stats
    p_stats = sub.add_parser("stats", help="Show manifest statistics")
    p_stats.add_argument("--manifest", required=True, type=Path)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "generate":
        manifest = generate_manifest(
            tc_path=args.tc,
            webview_source=args.webview_source,
            rn_source=args.rn_source,
            output_path=args.output,
        )
        print(f"\n  Generated manifest: {len(manifest.entries)} entries")
        print(f"  Stats: {manifest.stats}")

    elif args.command == "validate":
        result = validate_manifest(args.manifest)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["valid"]:
            raise SystemExit(1)

    elif args.command == "stats":
        print_manifest_stats(args.manifest)


if __name__ == "__main__":
    _cli_main()
