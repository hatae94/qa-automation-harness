"""testID injection automation tool for React Native and WebView components.

Provides audit, inject, export, and diff commands for testID coverage management.
Uses regex + line-by-line parsing (not full AST) for simplicity and robustness with TSX.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & patterns
# ---------------------------------------------------------------------------

# RN interactive components that should have testID
RN_INTERACTIVE_COMPONENTS = {
    "TouchableOpacity": "-btn",
    "Pressable": "-btn",
    "TextInput": "-input",
    "Button": "-btn",
    "Switch": "-switch",
    "ScrollView": "-list",
    "FlatList": "-list",
    "AlphazButton": "-btn",
    "AlphazBottomSheet": "-modal",
    "CommonWebView": "-webview",
}

# Web interactive elements (lowercase HTML) and components (PascalCase)
WEB_INTERACTIVE_ELEMENTS = {
    "button": "-btn",
    "input": "-input",
    "a": "-link",
    "select": "-select",
    "textarea": "-input",
    "form": "-form",
}

WEB_INTERACTIVE_COMPONENTS = {
    "Button": "-btn",
    "TextField": "-input",
    "Input": "-input",
    "Link": "-link",
    "Select": "-select",
    "PhoneTextInput": "-input",
    "PinTextFeild": "-input",
    "TextInput": "-input",
    "TopNavigation": "-nav",
    "SearchBar": "-input",
    "CheckBox": "-checkbox",
    "Radio": "-radio",
    "BottomSheet": "-modal",
    "AlphazBottomSheet": "-modal",
    "ErrorMessage": "-text",
    "ClearCloseButton": "-btn",
}

# Regex to match JSX opening tags (handles multi-line by scanning per-file)
# Captures: <ComponentName  or <html-tag
# Uses a negative lookbehind to exclude TypeScript generics like useRef<ScrollView>,
# Array<Button>, Promise<Response>, etc.
_JSX_OPEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"  # not preceded by identifier chars (rules out generics)
    r"<\s*([A-Z][A-Za-z0-9]*|[a-z][a-z0-9-]*)"
    r"(?=[\s/>]|$)"
)

# Regex to detect existing testID / data-testid prop on a JSX element
_HAS_TESTID_RN = re.compile(r'\btestID\s*=')
_HAS_TESTID_WEB = re.compile(r'\bdata-testid\s*=')

# Valid testID charset
_VALID_CHARSET = re.compile(r'^[a-z0-9._-]+$')

# Patterns to skip
_SKIP_PATHS = {
    "node_modules", "__tests__", ".test.", ".stories.", ".d.ts",
}

# ---------------------------------------------------------------------------
# Semantic naming: handler / children text / placeholder extraction
# ---------------------------------------------------------------------------

# Korean text -> English segment dictionary for children text
KR_EN_DICT: dict[str, str] = {
    "멤버십 신청": "membership-signup",
    "로그인": "login",
    "인증번호 받기": "get-otp",
    "다음": "next",
    "확인": "confirm",
    "취소": "cancel",
    "허용": "allow",
    "돌아가기": "go-back",
    "문제가 있으신가요": "need-help",
    "다시 인증번호 받기": "resend-otp",
    "해당 번호로 계속하기": "continue-with-number",
    "다른 번호 입력": "use-different-number",
    "이미 신청했어요": "already-applied",
    "패스할게요": "pass",
    "추천받기": "get-referral",
    "프로필 등록": "register-profile",
    "저장": "save",
    "삭제": "delete",
    "신고": "report",
    "차단": "block",
    "연결하기": "connect",
    "프로필 카드 보기": "view-profile-card",
    "이용약관": "terms-of-service",
    "개인정보 처리 방침": "privacy-policy",
    "수정": "edit",
    "완료": "done",
    "닫기": "close",
    "인증되었습니다": "verified",
    "다시 인증번호 받기": "resend-otp",
    "인증번호를 받지 못하셨나요": "otp-not-received",
    "이미 멤버십 신청된 번호입니다": "already-registered",
}

# Placeholder key nouns (Korean placeholder text -> english segment)
KR_PLACEHOLDER_DICT: dict[str, str] = {
    "전화번호를 입력해주세요": "phone-number",
    "전화번호": "phone-number",
    "닉네임": "nickname",
    "소개": "introduction",
    "인증번호": "otp-code",
    "검색": "search",
    "010-0000-0000": "phone-number",
    "메모를 입력해주세요": "memo",
}

# Regex to extract onClick handler name (e.g., onClick={handleClickSignUp} -> "SignUp")
_HANDLER_RE = re.compile(r'onClick\s*=\s*\{([A-Za-z_][A-Za-z0-9_]*)\}')

# Regex to extract children text right after closing > (handles JSX inline text)
# Matches: >한국어텍스트</ or >\n  한국어텍스트\n</
_CHILDREN_TEXT_RE = re.compile(r'>\s*\n?\s*([가-힣][가-힣\s?!.·]*[가-힣?!.])\s*\n?\s*</')

# Regex to extract placeholder prop value
_PLACEHOLDER_RE = re.compile(r'placeholder\s*=\s*["\']([^"\']+)["\']')


def _extract_handler_segment(tag_text: str) -> str | None:
    """Extract a semantic segment from onClick handler name.

    handleClickSignUp -> "signup"
    handleClick -> None (too generic)
    onSubmit -> "submit"
    """
    m = _HANDLER_RE.search(tag_text)
    if not m:
        return None
    handler = m.group(1)

    # Strip common prefixes (order matters: longer prefixes first)
    for prefix in ("handleClick", "handle_click_", "handle_", "handle", "onClick_", "on"):
        if handler.startswith(prefix) and len(handler) > len(prefix):
            remainder = handler[len(prefix):]
            if remainder and remainder[0].isupper():
                # CamelCase -> kebab-case
                segment = re.sub(r'([A-Z])', r'-\1', remainder).lower().strip('-')
                segment = re.sub(r'-+', '-', segment)
                if len(segment) > 2:  # skip too-short like "go"
                    return segment

    return None


def _extract_children_text_segment(tag_text: str, after_tag_lines: list[str]) -> str | None:
    """Extract a semantic segment from Korean children text.

    Searches in tag_text and the lines immediately following for Korean text
    that matches our dictionary.
    """
    # Combine tag text with a few following lines for context
    search_text = tag_text
    if after_tag_lines:
        search_text += '\n' + '\n'.join(after_tag_lines[:5])

    # Try dictionary match (longest match first)
    for kr_text, en_segment in sorted(KR_EN_DICT.items(), key=lambda x: -len(x[0])):
        if kr_text in search_text:
            return en_segment

    return None


def _extract_placeholder_segment(tag_text: str) -> str | None:
    """Extract a semantic segment from placeholder text."""
    m = _PLACEHOLDER_RE.search(tag_text)
    if not m:
        return None
    placeholder = m.group(1)

    for kr_text, en_segment in sorted(KR_PLACEHOLDER_DICT.items(), key=lambda x: -len(x[0])):
        if kr_text in placeholder:
            return en_segment

    return None


def _has_text_children(tag_text: str, after_tag_lines: list[str]) -> bool:
    """Check if a component has Korean text children (for selective injection)."""
    search_text = tag_text
    if after_tag_lines:
        search_text += '\n' + '\n'.join(after_tag_lines[:5])

    # Check for any Korean text between > and </
    return bool(_CHILDREN_TEXT_RE.search(search_text))


def _is_icon_only_component(tag_text: str, after_tag_lines: list[str]) -> bool:
    """Check if the component only contains icon/image children (no text)."""
    search_text = tag_text
    if after_tag_lines:
        search_text += '\n' + '\n'.join(after_tag_lines[:5])

    # Check for icon/image patterns
    icon_patterns = [
        re.compile(r'<\s*(Icon|Image|SvgIcon|.*Icon)\s'),
        re.compile(r'source\s*=\s*\{'),
        re.compile(r'left\s*=\s*["\'](?:back|close)["\']'),
    ]
    has_icon = any(p.search(search_text) for p in icon_patterns)

    # Check for Korean text
    has_korean = bool(re.search(r'[가-힣]{2,}', search_text.split('</')[0] if '</' in search_text else search_text))

    return has_icon and not has_korean


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ComponentMatch:
    """A single JSX component occurrence found in source."""
    file_path: str
    line_number: int
    component_name: str
    has_testid: bool
    existing_testid: str | None = None
    suggested_testid: str | None = None


@dataclass
class FileAudit:
    """Audit result for a single file."""
    file_path: str
    screen_name: str
    total_interactive: int = 0
    with_testid: int = 0
    without_testid: int = 0
    components: list[ComponentMatch] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.total_interactive == 0:
            return 100.0
        return round(self.with_testid / self.total_interactive * 100, 1)


@dataclass
class AuditReport:
    """Overall audit report across all files."""
    source_type: str  # "rn" or "web"
    source_path: str
    files: list[FileAudit] = field(default_factory=list)

    @property
    def total_interactive(self) -> int:
        return sum(f.total_interactive for f in self.files)

    @property
    def total_with_testid(self) -> int:
        return sum(f.with_testid for f in self.files)

    @property
    def total_without_testid(self) -> int:
        return sum(f.without_testid for f in self.files)

    @property
    def coverage_pct(self) -> float:
        total = self.total_interactive
        if total == 0:
            return 100.0
        return round(self.total_with_testid / total * 100, 1)


@dataclass
class InjectionPlan:
    """A single planned testID injection."""
    file_path: str
    line_number: int
    component_name: str
    testid: str
    prop_name: str  # "testID" for RN, "data-testid" for web
    original_line: str
    modified_line: str


@dataclass
class ExportEntry:
    """A single testID entry for export."""
    id: str
    component: str
    file_path: str
    line: int
    type: str  # "interactive", "container", etc.
    platform: str  # "rn" or "web"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_skip_file(path: Path) -> bool:
    """Check if a file should be skipped based on path patterns."""
    path_str = str(path)
    return any(skip in path_str for skip in _SKIP_PATHS)


def _derive_screen_name(file_path: Path, source_type: str) -> str:
    """Derive a screen/page name from the file path.

    RN: screens/gallery/GalleryScreen.tsx -> "native.gallery"
    RN: screens/liveness/LivenessScreen.tsx -> "native.liveness"
    RN: components/web-view/CommonWebView.tsx -> "webview"
    Web: pages/alphaz/login.page.tsx -> "login"
    Web: pages/alphaz/intro-v2.page.tsx -> "intro-v2"
    Web: pages/alphaz/recommendation/index.page.tsx -> "recommendation"
    """
    parts = file_path.parts
    name = file_path.stem  # filename without extension

    if source_type == "rn":
        # Try to find "screens" in path
        if "screens" in parts:
            idx = list(parts).index("screens")
            remaining = parts[idx + 1:]
            # Strip "Screen" suffix from file stem for a clean identifier
            file_stem = re.sub(r'Screen$', '', name)
            # Convert CamelCase to kebab-case (before lowering)
            file_stem = re.sub(r'([A-Z])', r'-\1', file_stem).lower().strip('-')
            file_stem = re.sub(r'-+', '-', file_stem)
            if len(remaining) > 1:
                # File is in a subdirectory under screens/
                # e.g. screens/gallery/GalleryScreen.tsx -> "native.gallery"
                # e.g. screens/account-setting/AlertReportScreen.tsx -> "native.account-setting.alert-report"
                screen_dir = remaining[0].lower()
                if len(remaining) > 2 or screen_dir != file_stem:
                    # Include file stem for disambiguation when dir has multiple files
                    return f"native.{screen_dir}.{file_stem}"
                return f"native.{screen_dir}"
            elif len(remaining) == 1:
                # File is directly in screens/ (no subdirectory)
                return f"native.{file_stem}"
        # Components
        if "components" in parts:
            idx = list(parts).index("components")
            remaining = parts[idx + 1:]
            if len(remaining) > 1:
                comp_dir = remaining[0].lower()
                file_stem = re.sub(r'Screen$', '', name)
                file_stem = re.sub(r'([A-Z])', r'-\1', file_stem).lower().strip('-')
                file_stem = re.sub(r'-+', '-', file_stem)
                if comp_dir != file_stem:
                    return f"{comp_dir}.{file_stem}"
                return comp_dir
            else:
                clean = name.lower().replace("screen", "")
                return clean
        return name.lower().replace("screen", "")

    elif source_type == "web":
        # pages/alphaz/login.page.tsx -> "login"
        # pages/alphaz/recommendation/index.page.tsx -> "recommendation"
        name_clean = name.replace(".page", "").replace(".index", "")
        if name_clean == "index":
            # Use parent directory name
            return parts[-2].lower() if len(parts) >= 2 else "unknown"
        return name_clean.lower()

    return "unknown"


def _to_kebab(name: str) -> str:
    """Convert a component name to kebab-case for testID segment."""
    # CamelCase -> camel-case
    result = re.sub(r'([A-Z])', r'-\1', name).lower().strip('-')
    # Clean up double dashes
    result = re.sub(r'-+', '-', result)
    return result


def _generate_testid(screen_name: str, component_name: str, suffix: str,
                     counter: dict[str, int],
                     semantic_segment: str | None = None) -> str:
    """Generate a testID following the naming convention.

    Format: {screen}.{semantic_or_element}-{type}

    Priority for naming the element segment:
      1. semantic_segment (from handler name, children text, or placeholder)
      2. kebab-case of component_name (generic fallback)
    """
    if semantic_segment:
        element = semantic_segment
    else:
        element = _to_kebab(component_name)

    base = f"{screen_name}.{element}{suffix}"

    # Ensure uniqueness within a file by appending counter if needed
    key = base
    if key in counter:
        counter[key] += 1
        base = f"{screen_name}.{element}-{counter[key]}{suffix}"
    else:
        counter[key] = 0

    # Validate charset
    if not _VALID_CHARSET.match(base):
        # Clean invalid chars
        base = re.sub(r'[^a-z0-9._-]', '-', base)
        base = re.sub(r'-+', '-', base).strip('-')

    # Enforce max length
    if len(base) > 96:
        base = base[:96]

    return base


def _find_jsx_components_in_file(
    file_path: Path,
    target_components: dict[str, str],
    testid_pattern: re.Pattern[str],
    source_type: str,
) -> list[ComponentMatch]:
    """Scan a TSX file and find all target JSX component usages.

    Returns a list of ComponentMatch with testID status.
    Uses a line-by-line + lookahead approach for multi-line JSX tags.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return []

    lines = content.split('\n')
    matches: list[ComponentMatch] = []
    screen_name = _derive_screen_name(file_path, source_type)

    i = 0
    while i < len(lines):
        line = lines[i]
        for m in _JSX_OPEN_RE.finditer(line):
            comp_name = m.group(1)
            if comp_name not in target_components:
                continue

            # Gather the full JSX opening tag (may span multiple lines).
            # We need to find the matching > or /> that closes the opening tag,
            # while being careful about nested braces (JSX expressions like onClick={...}).
            tag_text = line[m.start():]
            j = i
            brace_depth = 0
            found_close = False
            for ch in tag_text:
                if ch == '{':
                    brace_depth += 1
                elif ch == '}':
                    brace_depth -= 1
                elif ch == '>' and brace_depth == 0:
                    found_close = True
                    break

            while not found_close and j - i < 20:
                j += 1
                if j >= len(lines):
                    break
                tag_text += '\n' + lines[j]
                # Re-scan from current position for closing >
                for ch in lines[j]:
                    if ch == '{':
                        brace_depth += 1
                    elif ch == '}':
                        brace_depth -= 1
                    elif ch == '>' and brace_depth == 0:
                        found_close = True
                        break

            has_tid = bool(testid_pattern.search(tag_text))
            existing_tid = None
            if has_tid:
                # Extract existing testID value.
                # testid_pattern already matches `testID\s*=` or `data-testid\s*=`,
                # so we just need to capture what comes after the `=`.
                tid_match = re.search(
                    testid_pattern.pattern + r'\s*["\']([^"\']+)["\']',
                    tag_text,
                )
                if tid_match:
                    existing_tid = tid_match.group(1)
                else:
                    # Could be expression: testID={...}
                    tid_match = re.search(
                        testid_pattern.pattern + r'\s*\{([^}]+)\}',
                        tag_text,
                    )
                    if tid_match:
                        existing_tid = f"{{expr: {tid_match.group(1).strip()}}}"

            matches.append(ComponentMatch(
                file_path=str(file_path),
                line_number=i + 1,
                component_name=comp_name,
                has_testid=has_tid,
                existing_testid=existing_tid,
            ))
        i += 1

    return matches


# ---------------------------------------------------------------------------
# AUDIT
# ---------------------------------------------------------------------------

def audit(source: Path, source_type: str) -> AuditReport:
    """Audit testID coverage for the given source directory.

    Args:
        source: Path to source directory (RN src/ or web pages/ dir)
        source_type: "rn" or "web"

    Returns:
        AuditReport with per-file and aggregate statistics.
    """
    if source_type == "rn":
        targets = RN_INTERACTIVE_COMPONENTS
        testid_re = _HAS_TESTID_RN
    elif source_type == "web":
        targets = {**WEB_INTERACTIVE_ELEMENTS, **WEB_INTERACTIVE_COMPONENTS}
        testid_re = _HAS_TESTID_WEB
    else:
        raise ValueError(f"Unknown source_type: {source_type}")

    report = AuditReport(source_type=source_type, source_path=str(source))

    tsx_files = sorted(source.rglob("*.tsx"))
    for fpath in tsx_files:
        if _should_skip_file(fpath):
            continue

        components = _find_jsx_components_in_file(fpath, targets, testid_re, source_type)
        if not components:
            continue

        screen_name = _derive_screen_name(fpath, source_type)
        n_with = sum(1 for c in components if c.has_testid)
        n_without = sum(1 for c in components if not c.has_testid)

        fa = FileAudit(
            file_path=str(fpath),
            screen_name=screen_name,
            total_interactive=len(components),
            with_testid=n_with,
            without_testid=n_without,
            components=components,
        )
        report.files.append(fa)

    return report


def print_audit_report(report: AuditReport) -> None:
    """Print a formatted audit report to stdout."""
    print(f"\n{'=' * 70}")
    print(f"  testID Audit Report ({report.source_type.upper()})")
    print(f"  Source: {report.source_path}")
    print(f"{'=' * 70}\n")

    if not report.files:
        print("  No TSX files with interactive components found.\n")
        return

    # Table header
    print(f"  {'Screen':<30} {'Total':>6} {'WithID':>7} {'NoID':>6} {'Coverage':>9}")
    print(f"  {'-' * 30} {'-' * 6} {'-' * 7} {'-' * 6} {'-' * 9}")

    for fa in sorted(report.files, key=lambda f: f.screen_name):
        print(
            f"  {fa.screen_name:<30} {fa.total_interactive:>6} "
            f"{fa.with_testid:>7} {fa.without_testid:>6} "
            f"{fa.coverage_pct:>8.1f}%"
        )

    print(f"  {'-' * 30} {'-' * 6} {'-' * 7} {'-' * 6} {'-' * 9}")
    print(
        f"  {'TOTAL':<30} {report.total_interactive:>6} "
        f"{report.total_with_testid:>7} {report.total_without_testid:>6} "
        f"{report.coverage_pct:>8.1f}%"
    )
    print()

    # List files with missing testIDs
    missing_files = [f for f in report.files if f.without_testid > 0]
    if missing_files:
        print(f"  Files missing testIDs ({len(missing_files)}):")
        for fa in sorted(missing_files, key=lambda f: -f.without_testid):
            print(f"    {fa.without_testid:>3} missing in {fa.file_path}")
        print()


# ---------------------------------------------------------------------------
# INJECT (dry-run / apply)
# ---------------------------------------------------------------------------

def inject(source: Path, source_type: str, rules_path: Path | None = None,
           dry_run: bool = True, selective: bool = False) -> list[InjectionPlan]:
    """Plan or apply testID injections.

    Args:
        source: Path to source directory
        source_type: "rn" or "web"
        rules_path: Optional path to testid-rules.yaml
        dry_run: If True, only plan; if False, modify files.
        selective: If True, only inject on elements where text matching fails
                   (icon-only, no text children, shared components).

    Returns:
        List of InjectionPlan entries.
    """
    rules = _load_rules(rules_path) if rules_path else None

    if source_type == "rn":
        targets = RN_INTERACTIVE_COMPONENTS
        testid_re = _HAS_TESTID_RN
        prop_name = "testID"
    elif source_type == "web":
        targets = {**WEB_INTERACTIVE_ELEMENTS, **WEB_INTERACTIVE_COMPONENTS}
        testid_re = _HAS_TESTID_WEB
        prop_name = "data-testid"
    else:
        raise ValueError(f"Unknown source_type: {source_type}")

    # Override targets from rules if available
    if rules:
        _apply_rules_overrides(rules, source_type, targets)

    plans: list[InjectionPlan] = []
    tsx_files = sorted(source.rglob("*.tsx"))

    for fpath in tsx_files:
        if _should_skip_file(fpath):
            continue

        file_plans = _plan_injections_for_file(
            fpath, targets, testid_re, source_type, prop_name,
            selective=selective,
        )
        plans.extend(file_plans)

    if not dry_run:
        _apply_injections(plans)

    return plans


def _plan_injections_for_file(
    file_path: Path,
    targets: dict[str, str],
    testid_re: re.Pattern[str],
    source_type: str,
    prop_name: str,
    selective: bool = False,
) -> list[InjectionPlan]:
    """Plan testID injections for a single file.

    When selective=True (Phase 2 mode), only inject testIDs on elements
    where text matching would fail: icon-only buttons, no text children,
    no placeholder, or shared components.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return []

    lines = content.split('\n')
    screen_name = _derive_screen_name(file_path, source_type)
    plans: list[InjectionPlan] = []
    counter: dict[str, int] = {}
    is_common = "/common/" in str(file_path) or "/components/" in str(file_path)

    for i, line in enumerate(lines):
        for m in _JSX_OPEN_RE.finditer(line):
            comp_name = m.group(1)
            if comp_name not in targets:
                continue

            # Check if this tag already has testID (look ahead for multi-line)
            tag_text = line[m.start():]
            j = i
            brace_depth = 0
            found_close = False
            for ch in tag_text:
                if ch == '{':
                    brace_depth += 1
                elif ch == '}':
                    brace_depth -= 1
                elif ch == '>' and brace_depth == 0:
                    found_close = True
                    break
            while not found_close and j - i < 20:
                j += 1
                if j >= len(lines):
                    break
                tag_text += '\n' + lines[j]
                for ch in lines[j]:
                    if ch == '{':
                        brace_depth += 1
                    elif ch == '}':
                        brace_depth -= 1
                    elif ch == '>' and brace_depth == 0:
                        found_close = True
                        break

            if testid_re.search(tag_text):
                continue  # Already has testID, skip

            # Gather lines after the tag for children text analysis
            after_tag_lines = lines[i + 1 : min(i + 8, len(lines))]

            # Selective mode: skip elements where text matching works
            if selective:
                has_text = _has_text_children(tag_text, after_tag_lines)
                has_placeholder = bool(_PLACEHOLDER_RE.search(tag_text))
                is_icon_only = _is_icon_only_component(tag_text, after_tag_lines)

                # Skip if text matching is sufficient (has Korean text or placeholder)
                if (has_text or has_placeholder) and not is_common and not is_icon_only:
                    continue

            # Extract semantic segment (priority: handler > children > placeholder)
            semantic = (
                _extract_handler_segment(tag_text)
                or _extract_children_text_segment(tag_text, after_tag_lines)
                or _extract_placeholder_segment(tag_text)
            )

            suffix = targets[comp_name]
            testid = _generate_testid(
                screen_name, comp_name, suffix, counter,
                semantic_segment=semantic,
            )

            # Build the modified line: insert prop after <ComponentName
            tag_end = m.end()
            insert_attr = f' {prop_name}="{testid}"'

            original = line
            # Insert right after the component name
            modified = line[:tag_end] + insert_attr + line[tag_end:]

            plans.append(InjectionPlan(
                file_path=str(file_path),
                line_number=i + 1,
                component_name=comp_name,
                testid=testid,
                prop_name=prop_name,
                original_line=original.strip(),
                modified_line=modified.strip(),
            ))

    return plans


def _apply_injections(plans: list[InjectionPlan]) -> None:
    """Apply injection plans by modifying source files."""
    # Group plans by file
    by_file: dict[str, list[InjectionPlan]] = {}
    for plan in plans:
        by_file.setdefault(plan.file_path, []).append(plan)

    for fpath_str, file_plans in by_file.items():
        fpath = Path(fpath_str)
        content = fpath.read_text(encoding="utf-8")
        lines = content.split('\n')

        # Apply in reverse order to maintain line numbers
        for plan in sorted(file_plans, key=lambda p: -p.line_number):
            line_idx = plan.line_number - 1
            if line_idx < len(lines):
                old_line = lines[line_idx]
                # Find the component tag and insert the prop
                m = re.search(
                    rf'<\s*{re.escape(plan.component_name)}(?=[\s/>]|$)',
                    old_line,
                )
                if m:
                    insert_pos = m.end()
                    insert_attr = f' {plan.prop_name}="{plan.testid}"'
                    lines[line_idx] = (
                        old_line[:insert_pos] + insert_attr + old_line[insert_pos:]
                    )

        fpath.write_text('\n'.join(lines), encoding="utf-8")
        logger.info("Modified: %s (%d injections)", fpath_str, len(file_plans))


def print_injection_plan(plans: list[InjectionPlan], source_type: str) -> None:
    """Print injection plan to stdout."""
    if not plans:
        print("\n  No injections needed -- all interactive components have testIDs.\n")
        return

    print(f"\n{'=' * 70}")
    print(f"  testID Injection Plan ({source_type.upper()}) -- {len(plans)} changes")
    print(f"{'=' * 70}\n")

    current_file = ""
    for plan in plans:
        if plan.file_path != current_file:
            current_file = plan.file_path
            print(f"  File: {current_file}")
            print(f"  {'-' * 60}")

        print(f"    L{plan.line_number}: <{plan.component_name}>")
        print(f"      + {plan.prop_name}=\"{plan.testid}\"")
        print(f"      - {plan.original_line[:80]}")
        print(f"      + {plan.modified_line[:80]}")
        print()


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def export_testids(source: Path, source_type: str) -> dict:
    """Export all found testIDs as a JSON manifest.

    Args:
        source: Path to source directory
        source_type: "rn" or "web"

    Returns:
        Dict suitable for JSON serialization.
    """
    if source_type == "rn":
        targets = RN_INTERACTIVE_COMPONENTS
        testid_re = _HAS_TESTID_RN
    elif source_type == "web":
        targets = {**WEB_INTERACTIVE_ELEMENTS, **WEB_INTERACTIVE_COMPONENTS}
        testid_re = _HAS_TESTID_WEB
    else:
        raise ValueError(f"Unknown source_type: {source_type}")

    pages: list[dict] = []
    all_testids: list[str] = []

    tsx_files = sorted(source.rglob("*.tsx"))
    for fpath in tsx_files:
        if _should_skip_file(fpath):
            continue

        components = _find_jsx_components_in_file(fpath, targets, testid_re, source_type)
        if not components:
            continue

        screen_name = _derive_screen_name(fpath, source_type)
        testids_in_file: list[dict] = []

        for comp in components:
            if comp.has_testid and comp.existing_testid:
                tid = comp.existing_testid
                # Skip expression-based testIDs for now
                if tid.startswith("{expr:"):
                    tid = tid[6:-1].strip()
                testids_in_file.append({
                    "id": tid,
                    "component": comp.component_name,
                    "type": "interactive",
                    "line": comp.line_number,
                })
                all_testids.append(tid)

        page_type = "native" if source_type == "rn" else "webview"
        pages.append({
            "page_name": screen_name,
            "file_path": str(fpath),
            "type": page_type,
            "total_interactive": len(components),
            "with_testid": sum(1 for c in components if c.has_testid),
            "testids": testids_in_file,
        })

    total_interactive = sum(p["total_interactive"] for p in pages)
    total_with = sum(p["with_testid"] for p in pages)

    return {
        "version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_type": source_type,
        "source_path": str(source),
        "stats": {
            "total_pages": len(pages),
            "total_testids": len(all_testids),
            "total_interactive": total_interactive,
            "coverage_pct": round(total_with / total_interactive * 100, 1) if total_interactive else 0,
        },
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# DIFF
# ---------------------------------------------------------------------------

def diff(source: Path, source_type: str) -> list[InjectionPlan]:
    """Show what would change (alias for inject --dry-run)."""
    return inject(source, source_type, dry_run=True)


# ---------------------------------------------------------------------------
# Rules loading
# ---------------------------------------------------------------------------

def _load_rules(rules_path: Path) -> dict:
    """Load testid-rules.yaml."""
    if yaml is None:
        raise ImportError("pyyaml is required to load rules files. Install with: pip install pyyaml")
    with open(rules_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _apply_rules_overrides(rules: dict, source_type: str, targets: dict[str, str]) -> None:
    """Override target components from rules YAML."""
    inject_targets = rules.get("inject_targets", {})
    if not inject_targets:
        # Try old-style rn/web sections
        section = rules.get(source_type, {})
        if "target_components" in section:
            for comp in section["target_components"]:
                if comp not in targets:
                    targets[comp] = "-btn"  # default suffix
        return

    for _level, items in inject_targets.items():
        if not isinstance(items, list):
            continue
        for item in items:
            comp = item.get("component")
            suffix = item.get("suffix", "-btn")
            if comp:
                targets[comp] = suffix


# ---------------------------------------------------------------------------
# CLI entry point (can be used standalone)
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Standalone CLI for testid_injector (used via python -m)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="testID injection tool for RN and WebView TSX files"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = sub.add_parser("audit", help="Audit testID coverage")
    p_audit.add_argument("--source", required=True, type=Path)
    p_audit.add_argument("--type", dest="source_type", required=True,
                         choices=["rn", "web"])
    p_audit.add_argument("--json", dest="output_json", action="store_true",
                         help="Output as JSON")

    # inject
    p_inject = sub.add_parser("inject", help="Inject testIDs")
    p_inject.add_argument("--source", required=True, type=Path)
    p_inject.add_argument("--type", dest="source_type", required=True,
                          choices=["rn", "web"])
    p_inject.add_argument("--rules", type=Path, default=None)
    p_inject.add_argument("--dry-run", action="store_true", default=True)
    p_inject.add_argument("--apply", action="store_true", default=False)
    p_inject.add_argument("--selective", action="store_true", default=False,
                          help="Only inject testIDs where text matching fails")

    # export
    p_export = sub.add_parser("export", help="Export testIDs as JSON")
    p_export.add_argument("--source", required=True, type=Path)
    p_export.add_argument("--type", dest="source_type", required=True,
                          choices=["rn", "web"])
    p_export.add_argument("--output", type=Path, default=None)

    # diff
    p_diff = sub.add_parser("diff", help="Show what would change")
    p_diff.add_argument("--source", required=True, type=Path)
    p_diff.add_argument("--type", dest="source_type", required=True,
                        choices=["rn", "web"])

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "audit":
        report = audit(args.source, args.source_type)
        if args.output_json:
            # Serialize as JSON
            data = {
                "source_type": report.source_type,
                "source_path": report.source_path,
                "total_interactive": report.total_interactive,
                "total_with_testid": report.total_with_testid,
                "total_without_testid": report.total_without_testid,
                "coverage_pct": report.coverage_pct,
                "files": [
                    {
                        "file_path": f.file_path,
                        "screen_name": f.screen_name,
                        "total_interactive": f.total_interactive,
                        "with_testid": f.with_testid,
                        "without_testid": f.without_testid,
                        "coverage_pct": f.coverage_pct,
                    }
                    for f in report.files
                ],
            }
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_audit_report(report)

    elif args.command == "inject":
        is_dry_run = not args.apply
        plans = inject(args.source, args.source_type, args.rules,
                       dry_run=is_dry_run, selective=args.selective)
        if is_dry_run:
            print_injection_plan(plans, args.source_type)
        else:
            print(f"\n  Applied {len(plans)} testID injections.\n")
            print_injection_plan(plans, args.source_type)

    elif args.command == "export":
        manifest = export_testids(args.source, args.source_type)
        output_str = json.dumps(manifest, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output_str, encoding="utf-8")
            print(f"  Exported to {args.output}")
        else:
            print(output_str)

    elif args.command == "diff":
        plans = diff(args.source, args.source_type)
        print_injection_plan(plans, args.source_type)


if __name__ == "__main__":
    _cli_main()
