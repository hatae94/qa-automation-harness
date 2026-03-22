"""Tests for the TC CSV parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_harness.tools.tc_parser import parse_steps, parse_tc_csv, parse_tc_file
from qa_harness.types import TCPriority


class TestParseSteps:
    def test_single_step(self) -> None:
        steps = parse_steps("1. 알파 앱 실행")
        assert len(steps) == 1
        assert steps[0].number == 1
        assert steps[0].description == "알파 앱 실행"

    def test_multiple_steps(self) -> None:
        text = "1. 알파 앱 실행\n2. [멤버십 신청] 버튼 클릭\n3. 전화번호 입력"
        steps = parse_steps(text)
        assert len(steps) == 3
        assert steps[0].number == 1
        assert steps[1].number == 2
        assert steps[2].description == "전화번호 입력"

    def test_empty_text(self) -> None:
        assert parse_steps("") == []
        assert parse_steps("   ") == []

    def test_unnumbered_text(self) -> None:
        steps = parse_steps("알파 앱 실행하여 확인")
        assert len(steps) == 1
        assert steps[0].number == 1
        assert steps[0].description == "알파 앱 실행하여 확인"

    def test_crlf_normalized(self) -> None:
        text = "1. Step A\r\n2. Step B"
        steps = parse_steps(text)
        assert len(steps) == 2


class TestParseCSV:
    def test_parse_sample_csv(self, sample_csv_content: str) -> None:
        result = parse_tc_csv(sample_csv_content)
        assert len(result.errors) == 0
        assert len(result.test_cases) == 3

    def test_summary_rows_extracted(self, sample_csv_content: str) -> None:
        result = parse_tc_csv(sample_csv_content)
        assert len(result.summary) == 1
        assert result.summary[0].platform == "Android"
        assert result.summary[0].total_tc == 606

    def test_category_inheritance(self, sample_csv_content: str) -> None:
        result = parse_tc_csv(sample_csv_content)
        # LoginPage_3 should inherit "인트로" from LoginPage_2
        tc3 = result.test_cases[2]
        assert tc3.id == "LoginPage_3"
        assert tc3.category.major == "인트로"
        assert tc3.category.middle == "권한"

    def test_priority_normalization(self, sample_csv_content: str) -> None:
        result = parse_tc_csv(sample_csv_content)
        assert result.test_cases[0].priority == TCPriority.HIGH

    def test_empty_csv(self) -> None:
        result = parse_tc_csv("")
        assert len(result.test_cases) == 0
        assert len(result.errors) == 0


class TestParseFile:
    def test_parse_sample_json(self, sample_tc_path: Path) -> None:
        """The sample-tc.json is already parsed JSON; test round-trip
        through the pydantic model by loading it directly."""
        from qa_harness.types import TCParseResult

        raw = json.loads(sample_tc_path.read_text(encoding="utf-8"))
        result = TCParseResult.model_validate(raw)
        assert len(result.test_cases) == 5
        assert result.test_cases[0].id == "LoginPage_1"
