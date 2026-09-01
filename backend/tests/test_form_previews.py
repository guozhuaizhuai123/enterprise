from datetime import date

import pytest

from app.assistant.form_previews import preview_form


def test_shared_form_previews_extract_fields():
    """Removing any shared parser branch would leave a supported form without useful fields."""
    leave = preview_form("leave", "我要从明天开始请假两天，家里有事", today=date(2026, 8, 31))
    ticket = preview_form("ticket", "电脑网络有问题，帮我找信息部处理")
    expense = preview_form("expense", "报销昨天打车 86 元")

    assert leave["start_date"] == "2026-09-01"
    assert leave["end_date"] == "2026-09-02"
    assert ticket["is_ticket_request"] is True
    assert expense["total_amount"] == "86"


def test_shared_form_preview_rejects_unknown_form():
    """Accepting an arbitrary form name would turn the closed preview catalog into an open dispatcher."""
    with pytest.raises(ValueError, match="unsupported form"):
        preview_form("https://attacker.example", "anything")


@pytest.mark.parametrize(
    "text",
    [
        "电脑坏了帮我找人处理",
        "打印机连不上网，麻烦找信息部处理",
        "报表数据不对，请找财务处理",
    ],
)
def test_ticket_preview_recognizes_the_same_fault_reports_as_the_planner(text):
    """A planner ticket route whose preview says "not a ticket" would open an empty dialog."""
    preview = preview_form("ticket", text)

    assert preview["is_ticket_request"] is True
    assert preview["ticket_type"] == "issue"
    assert preview["description"] == text


def test_fault_report_subject_names_the_broken_thing_not_the_helper():
    """A subject like "人处理" would reach the handler with no idea what is broken."""
    preview = preview_form("ticket", "打印机连不上网，麻烦找信息部处理")

    assert preview["subject"] == "打印机连不上网"
    assert preview["department_name"] == "信息部"
    assert preview_form("ticket", "电脑坏了帮我找人处理")["subject"] == "电脑坏了"
