"""TC Parser -- Parse real QA test case CSV files.

Handles the messy reality of the alphaz QA spreadsheet:
- Summary rows at the top (결과값)
- Multi-line step fields with numbered steps
- Korean content throughout
- Merged cell patterns (empty cells inherit from above)
- Empty / filler rows
- Category hierarchy (대분류 > 중분류 > 소분류)
"""

from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path
from typing import TextIO

import click

from qa_harness.types import (
    DefectSeverity,
    DefectType,
    TCCategory,
    TCParseError,
    TCParseResult,
    TCPriority,
    TCResult,
    TCStep,
    TCSummary,
    TestCase,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants for CSV column indices (0-based)
# ---------------------------------------------------------------------------

_COL_TC_ID = 0
_COL_PRIORITY = 1
_COL_MAJOR = 2
_COL_MIDDLE = 3
_COL_MINOR = 4
_COL_FUNCTION = 5
_COL_PRE_CONDITION = 6
_COL_STEP_START = 7
_COL_EXPECTED_RESULT = 13
_COL_RESULT_ANDROID = 14
_COL_RESULT_IOS = 15
_COL_ISSUE_ID = 16
_COL_DEFECT_SEVERITY = 17
_COL_DEFECT_TYPE = 18
_COL_CHANGE_NOTE = 19
_COL_REMARK = 20

_SUMMARY_LABELS = ("Android", "iOS", "Project 전체 상태")
_HEADER_MARKERS = {"TC ID", "TC_ID", "대분류", "Category"}
_SKIP_MARKERS = ("결과값", "Test Case information", "ㄴ")


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------

def _cell(row: list[str], idx: int) -> str:
    if idx < len(row):
        return (row[idx] or "").strip()
    return ""


def _is_summary_row(row: list[str]) -> bool:
    first = _cell(row, 0)
    second = _cell(row, 1)
    if any(first.startswith(label) for label in _SUMMARY_LABELS):
        return True
    if any(m in first or m in second for m in _SKIP_MARKERS):
        return True
    return False


def _is_header_row(row: list[str]) -> bool:
    first = _cell(row, 0)
    third = _cell(row, 2)
    return first in _HEADER_MARKERS or third in _HEADER_MARKERS


def _is_empty_row(row: list[str]) -> bool:
    return all((c or "").strip() == "" for c in row)


# ---------------------------------------------------------------------------
# Step parsing
# ---------------------------------------------------------------------------

_STEP_RE = re.compile(r"(?:^|\n)\s*(\d+)\.\s*")


def parse_steps(raw_text: str) -> list[TCStep]:
    """Parse numbered steps from multi-line text such as
    ``1. 알파 앱 실행\\n2. [멤버십 신청] 버튼 클릭``."""
    text = raw_text.replace("\r\n", "\n").strip()
    if not text:
        return []

    matches = list(_STEP_RE.finditer(text))
    if not matches:
        return [TCStep(number=1, description=text)]

    steps: list[TCStep] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        desc = text[start:end].strip()
        if desc:
            steps.append(TCStep(number=int(m.group(1)), description=desc))
    return steps


# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------

def _normalize_priority(raw: str) -> TCPriority:
    try:
        n = int(raw.strip())
        if n in (1, 2, 3):
            return TCPriority(n)
    except (ValueError, TypeError):
        pass
    return TCPriority.LOW


_RESULT_MAP: dict[str, TCResult] = {
    "Pass": "Pass",
    "Fail": "Fail",
    "Block": "Block",
    "N/A": "N/A",
    "N/T": "N/T",
}

_SEVERITY_MAP: dict[str, DefectSeverity] = {
    "Critical": "Critical",
    "Major": "Major",
    "Minor": "Minor",
    "Trivial": "Trivial",
}

_DEFECT_MAP: dict[str, DefectType] = {
    "Bug": "Bug",
    "Design": "Design",
    "Etc": "Etc",
}


# ---------------------------------------------------------------------------
# Summary row parsing
# ---------------------------------------------------------------------------

def _parse_summary_row(row: list[str]) -> TCSummary | None:
    platform_raw = _cell(row, 0)
    if platform_raw.startswith("Android"):
        platform = "Android"
    elif platform_raw.startswith("iOS"):
        platform = "iOS"
    elif platform_raw.startswith("Project"):
        platform = "Project"
    else:
        return None

    def _int(idx: int) -> int:
        try:
            return int(_cell(row, idx)) if _cell(row, idx) else 0
        except ValueError:
            return 0

    return TCSummary(
        platform=platform,
        total_tc=_int(5),
        coverage=_cell(row, 6),
        pass_rate=_cell(row, 7),
        passed=_int(8),
        fail=_int(9),
        block=_int(10),
        na=_int(11),
        nt=_int(12),
        note=_cell(row, 13),
    )


# ---------------------------------------------------------------------------
# Main parsing
# ---------------------------------------------------------------------------

def _extract_step_text(row: list[str]) -> str:
    """Concatenate step columns (7-12) into a single text block."""
    parts = [_cell(row, i) for i in range(_COL_STEP_START, _COL_EXPECTED_RESULT) if _cell(row, i)]
    return "\n".join(parts)


def parse_tc_csv(csv_content: str) -> TCParseResult:
    """Parse a CSV string and return structured test cases."""
    summaries: list[TCSummary] = []
    test_cases: list[TestCase] = []
    errors: list[TCParseError] = []

    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
    except csv.Error as exc:
        errors.append(TCParseError(row=0, message=f"CSV parse error: {exc}"))
        return TCParseResult(summary=summaries, test_cases=test_cases, errors=errors)

    # Merged-cell inheritance tracker
    major = middle = minor = ""
    header_seen = False

    for row_idx, row in enumerate(rows):
        if _is_empty_row(row):
            continue

        if not header_seen and _is_summary_row(row):
            s = _parse_summary_row(row)
            if s:
                summaries.append(s)
            continue

        if _is_header_row(row):
            header_seen = True
            continue

        if not header_seen:
            continue

        tc_id = _cell(row, _COL_TC_ID)
        if not tc_id or not re.match(r"^[A-Za-z]", tc_id):
            continue

        # Category inheritance
        raw_major = _cell(row, _COL_MAJOR)
        raw_middle = _cell(row, _COL_MIDDLE)
        raw_minor = _cell(row, _COL_MINOR)
        if raw_major:
            major = raw_major
        if raw_middle:
            middle = raw_middle
        if raw_minor:
            minor = raw_minor

        raw_step_text = _extract_step_text(row)
        steps = parse_steps(raw_step_text)

        try:
            tc = TestCase(
                id=tc_id,
                priority=_normalize_priority(_cell(row, _COL_PRIORITY)),
                category=TCCategory(major=major, middle=middle, minor=minor),
                function_type=_cell(row, _COL_FUNCTION) or "UI",
                pre_condition=_cell(row, _COL_PRE_CONDITION),
                steps=steps,
                raw_step_text=raw_step_text,
                expected_result=_cell(row, _COL_EXPECTED_RESULT),
                result_android=_RESULT_MAP.get(_cell(row, _COL_RESULT_ANDROID), ""),
                result_ios=_RESULT_MAP.get(_cell(row, _COL_RESULT_IOS), ""),
                issue_id=_cell(row, _COL_ISSUE_ID),
                defect_severity=_SEVERITY_MAP.get(_cell(row, _COL_DEFECT_SEVERITY), ""),
                defect_type=_DEFECT_MAP.get(_cell(row, _COL_DEFECT_TYPE), ""),
                change_note=_cell(row, _COL_CHANGE_NOTE),
                remark=_cell(row, _COL_REMARK),
            )
            test_cases.append(tc)
        except Exception as exc:
            errors.append(
                TCParseError(
                    row=row_idx + 1,
                    message=f"Parse error at row {row_idx + 1}: {exc}",
                    raw_data=" | ".join(row[:6]),
                )
            )

    return TCParseResult(summary=summaries, test_cases=test_cases, errors=errors)


# ---------------------------------------------------------------------------
# File-level helper
# ---------------------------------------------------------------------------

def parse_tc_file(input_path: Path) -> TCParseResult:
    """Read a CSV file and return parsed test cases."""
    content = input_path.read_text(encoding="utf-8")
    return parse_tc_csv(content)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("parse-tc")
@click.option("-i", "--input", "input_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", "output_path", required=True, type=click.Path(path_type=Path))
def parse_tc_cmd(input_path: Path, output_path: Path) -> None:
    """Parse TC CSV spreadsheet into normalized JSON."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("[tc-parser] Reading CSV from: %s", input_path)
    result = parse_tc_file(input_path)

    logger.info("[tc-parser] Parsed %d test cases", len(result.test_cases))
    logger.info("[tc-parser] Summary rows: %d", len(result.summary))

    if result.errors:
        logger.warning("[tc-parser] %d parse errors:", len(result.errors))
        for err in result.errors:
            logger.warning("  Row %d: %s", err.row, err.message)

    for s in result.summary:
        logger.info(
            "[tc-parser] %s: %d TCs, %s pass rate (P:%d F:%d B:%d NA:%d NT:%d)",
            s.platform,
            s.total_tc,
            s.pass_rate,
            s.passed,
            s.fail,
            s.block,
            s.na,
            s.nt,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    logger.info("[tc-parser] Output written to: %s", output_path)
