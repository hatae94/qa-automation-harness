"""Shared pytest fixtures for the QA Automation Harness tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_harness.knowledge.catalog import ScreenCatalog, load_catalog
from qa_harness.types import (
    AppScreen,
    FlowGraph,
    FlowTransition,
    TCCategory,
    TCStep,
    TestCase,
    UIElement,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SCREENS_DIR = Path(__file__).resolve().parent.parent / "src" / "knowledge" / "screens"
FLOW_GRAPH_PATH = Path(__file__).resolve().parent.parent / "src" / "knowledge" / "flow-graph.json"


@pytest.fixture()
def sample_tc_path() -> Path:
    return FIXTURES_DIR / "sample-tc.json"


@pytest.fixture()
def test_accounts_path() -> Path:
    return FIXTURES_DIR / "test-accounts.json"


@pytest.fixture()
def catalog() -> ScreenCatalog:
    """Load the real screen catalog from the project knowledge base."""
    return load_catalog(SCREENS_DIR, FLOW_GRAPH_PATH)


@pytest.fixture()
def sample_test_case() -> TestCase:
    return TestCase(
        id="LoginPage_5",
        priority=2,
        category=TCCategory(major="인트로", middle="권한", minor="알림 권한 허용"),
        function_type="기능",
        pre_condition="",
        steps=[
            TCStep(number=1, description="알파 앱 실행"),
            TCStep(number=2, description="인트로 > 앱 추적 권한 팝업 > 알림 받기(허용)"),
            TCStep(number=3, description="앱 종료 후 임의 알림 전송"),
        ],
        raw_step_text="1. 알파 앱 실행\n2. 인트로 > 앱 추적 권한 팝업 > 알림 받기(허용)\n3. 앱 종료 후 임의 알림 전송",
        expected_result="알림 허용되어 팝업 미노출",
        result_android="Pass",
        result_ios="Pass",
    )


@pytest.fixture()
def sample_csv_content() -> str:
    """Minimal CSV content mimicking the real spreadsheet."""
    lines = [
        '"결과값","","","","","","","","","","","","","",""',
        '"Android","","","","","606","100.00%","93%","466","33","4","67","36",""',
        '"TC ID","Priority","대분류","중분류","소분류","UI/기능","Pre-Condition","Step1","","","","","","Expected Result","Android","iOS"',
        '"LoginPage_1","1","스플래시","스플래시화면","스플래시 이미지","UI","","1. 알파 앱 실행","","","","","","스플래시 이미지 노출","Pass","Pass"',
        '"LoginPage_2","1","인트로","인트로화면","인트로 이미지","UI","","1. 알파 앱 실행","","","","","","인트로 이미지 노출","Pass","Pass"',
        '"LoginPage_3","1","인트로","권한","IDFA 권한","UI","","1. 알파 앱 실행","2. 인트로 > 앱 추적 권한 팝업","","","","","앱 추적 권한 팝업 노출","N/T","Pass"',
    ]
    return "\n".join(lines)
