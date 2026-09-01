from datetime import date

import pytest

from app.assistant.periods import parse_day, parse_month, parse_period, parse_range

TODAY = date(2026, 9, 1)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("这个月支出怎么样", "2026-09"),
        ("本月流水", "2026-09"),
        ("当月费用统计", "2026-09"),
        ("查看上月支出", "2026-08"),
        ("查看上个月考勤", "2026-08"),
        ("前一个月的报销", "2026-08"),
        ("上上个月支出", "2026-07"),
        ("查看 7 月费用", "2026-07"),
        ("查看七月费用", "2026-07"),
        ("十二月的费用怎么样", "2025-12"),
        ("去年12月支出", "2025-12"),
        ("今年3月支出", "2026-03"),
        ("2026-07 的费用", "2026-07"),
        ("2025年11月支出", "2025-11"),
        ("8月15日考勤", "2026-08"),
        ("昨天的费用", None),
        ("公司的报销制度", None),
        ("查看费用", None),
    ],
)
def test_parse_month_resolves_spoken_periods(text, expected):
    """A missed month means a historical question silently answers for today."""
    assert parse_month(text, TODAY) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("今天考勤", date(2026, 9, 1)),
        ("查看今日打卡", date(2026, 9, 1)),
        ("昨天考勤情况", date(2026, 8, 31)),
        ("前天考勤", date(2026, 8, 30)),
        ("8月15日考勤", date(2026, 8, 15)),
        ("2026-07-20 的考勤", date(2026, 7, 20)),
        ("上个月15号考勤", date(2026, 8, 15)),
        ("查看上个月考勤", None),
        ("2月30日考勤", None),
        ("查看考勤", None),
    ],
)
def test_parse_day_resolves_explicit_and_relative_days(text, expected):
    """Guessing a day for a month question would report one date as the whole month."""
    assert parse_day(text, TODAY) == expected


def test_parse_period_always_supplies_the_month_of_a_resolved_day():
    """Expense summaries only aggregate by month, so a day question still needs its month."""
    period = parse_period("昨天的费用", TODAY)

    assert period.day == date(2026, 8, 31)
    assert period.month == "2026-08"

    month_only = parse_period("查看上月支出", TODAY)
    assert month_only.day is None
    assert month_only.month == "2026-08"

    empty = parse_period("公司的报销制度是什么", TODAY)
    assert empty.day is None and empty.month is None


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        # 2026-09-01 是星期二
        ("本周考勤情况", date(2026, 8, 31), date(2026, 9, 1)),
        ("上周支出", date(2026, 8, 24), date(2026, 8, 30)),
        ("上上周考勤", date(2026, 8, 17), date(2026, 8, 23)),
        ("最近7天费用", date(2026, 8, 26), date(2026, 9, 1)),
        ("最近 30 天支出", date(2026, 8, 3), date(2026, 9, 1)),
        ("最近一个月的费用", date(2026, 8, 3), date(2026, 9, 1)),
        ("今年费用统计", date(2026, 1, 1), date(2026, 9, 1)),
        ("去年支出情况", date(2025, 1, 1), date(2025, 12, 31)),
    ],
)
def test_parse_range_resolves_weeks_rolling_days_and_years(text, start, end):
    """Answering "上周" with a month would report the wrong period as if it were exact."""
    assert parse_range(text, TODAY) == (start, end)

    period = parse_period(text, TODAY)
    assert (period.start, period.end) == (start, end)
    assert period.day is None and period.month is None


def test_explicit_month_beats_a_year_range():
    """"去年12月" is one month, not the whole of last year."""
    period = parse_period("去年12月支出", TODAY)

    assert period.month == "2025-12"
    assert period.start is None and period.end is None
