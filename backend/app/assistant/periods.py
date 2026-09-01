"""Shared relative-period parsing for conversational business queries.

Spoken business questions rarely name an ISO period: "上个月支出怎么样",
"查看 8 月考勤", "昨天的费用".  This module turns that text into an explicit
day or `YYYY-MM` month so the planner can bind a registered query input and the
adapters never have to guess.  It is pure: the caller supplies "today".
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")

_CN_MONTHS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
    "元": 1,
}
_CN_MONTH_ALTERNATIVES = "十一|十二|一|二|三|四|五|六|七|八|九|十|元"

_ISO_DAY = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?")
_ISO_MONTH = re.compile(r"(\d{4})[-/年](\d{1,2})月?(?![-/\d])")
_MONTH_DAY = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
# 只要求日/号后缀，前面允许"上个月15号"这样的相对月份；真正的"8月15日"在此之前
# 已由 _MONTH_DAY 命中。
_BARE_DAY = re.compile(r"(?<![\d年/-])(\d{1,2})\s*[日号](?!\d)")
_LAST_YEAR_MONTH = re.compile(rf"去年\s*(?:(\d{{1,2}})|({_CN_MONTH_ALTERNATIVES}))\s*月")
_THIS_YEAR_MONTH = re.compile(rf"今年\s*(?:(\d{{1,2}})|({_CN_MONTH_ALTERNATIVES}))\s*月")
_PLAIN_MONTH = re.compile(
    rf"(?<![\d年])(?:(\d{{1,2}})|({_CN_MONTH_ALTERNATIVES}))\s*月(?!\s*\d*\s*[日号])"
)


@dataclass(frozen=True)
class Period:
    """A resolved period.  `month` is always filled when `day` is."""

    day: date | None
    month: str | None
    start: date | None = None
    end: date | None = None


def business_today() -> date:
    """Today in the company's business timezone, matching the expense adapter."""
    return datetime.now(BUSINESS_TIMEZONE).date()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + month - 1) + delta
    return index // 12, index % 12 + 1


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _monday(today: date, week_offset: int) -> date:
    """Monday of the week `week_offset` weeks away from today's week."""
    return today.fromordinal(today.toordinal() - today.weekday() + week_offset * 7)


def _resolve_year(month: int, today: date, *, allow_future: bool = False) -> int:
    """A bare month name means the most recent one unless it is still ahead."""
    if allow_future or month <= today.month:
        return today.year
    return today.year - 1


def _month_number(digits: str | None, chinese: str | None) -> int | None:
    if digits:
        value = int(digits)
        return value if 1 <= value <= 12 else None
    if chinese:
        return _CN_MONTHS.get(chinese)
    return None


def parse_month(text: str, today: date) -> str | None:
    """Return `YYYY-MM` for a spoken month reference, or None when absent."""
    iso_day = _ISO_DAY.search(text)
    if iso_day is not None:
        month = int(iso_day.group(2))
        if 1 <= month <= 12:
            return _month_key(int(iso_day.group(1)), month)

    iso_month = _ISO_MONTH.search(text)
    if iso_month is not None:
        month = int(iso_month.group(2))
        if 1 <= month <= 12:
            return _month_key(int(iso_month.group(1)), month)

    for pattern, year_offset in ((_LAST_YEAR_MONTH, -1), (_THIS_YEAR_MONTH, 0)):
        match = pattern.search(text)
        if match is not None:
            month = _month_number(match.group(1), match.group(2))
            if month is not None:
                return _month_key(today.year + year_offset, month)

    month_day = _MONTH_DAY.search(text)
    if month_day is not None:
        month = int(month_day.group(1))
        if 1 <= month <= 12:
            return _month_key(_resolve_year(month, today), month)

    if re.search(r"上上(?:个)?月|前两(?:个)?月", text):
        return _month_key(*_shift_month(today.year, today.month, -2))
    if re.search(r"上(?:一)?(?:个)?月|前(?:一)?个月|前个月", text):
        return _month_key(*_shift_month(today.year, today.month, -1))
    if re.search(r"下(?:一)?(?:个)?月", text):
        return _month_key(*_shift_month(today.year, today.month, 1))
    if re.search(r"本月|这个月|这月|当月|本个月|今个月|当前月", text):
        return _month_key(today.year, today.month)

    plain_month = _PLAIN_MONTH.search(text)
    if plain_month is not None:
        month = _month_number(plain_month.group(1), plain_month.group(2))
        if month is not None:
            return _month_key(_resolve_year(month, today), month)
    return None


def parse_day(text: str, today: date) -> date | None:
    """Return an explicit calendar day, or None when the text names none."""
    iso_day = _ISO_DAY.search(text)
    if iso_day is not None:
        try:
            return date(int(iso_day.group(1)), int(iso_day.group(2)), int(iso_day.group(3)))
        except ValueError:
            return None

    if re.search(r"前天|前日", text):
        return today.fromordinal(today.toordinal() - 2)
    if re.search(r"昨天|昨日|上一天", text):
        return today.fromordinal(today.toordinal() - 1)
    if re.search(r"今天|今日|本日|当天", text):
        return today

    month_day = _MONTH_DAY.search(text)
    if month_day is not None:
        month = int(month_day.group(1))
        day = int(month_day.group(2))
        try:
            return date(_resolve_year(month, today), month, day)
        except ValueError:
            return None

    bare_day = _BARE_DAY.search(text)
    if bare_day is not None:
        month_key = parse_month(text, today) or _month_key(today.year, today.month)
        year, month = (int(part) for part in month_key.split("-", 1))
        try:
            return date(year, month, int(bare_day.group(1)))
        except ValueError:
            return None
    return None


def parse_range(text: str, today: date) -> tuple[date, date] | None:
    """Resolve week, rolling-day and year references that no single month covers."""
    if re.search(r"上上(?:个)?(?:周|星期)", text):
        monday = _monday(today, -2)
        return monday, monday.fromordinal(monday.toordinal() + 6)
    if re.search(r"上(?:一)?(?:个)?(?:周|星期)|前(?:一)?(?:周|星期)", text):
        monday = _monday(today, -1)
        return monday, monday.fromordinal(monday.toordinal() + 6)
    if re.search(r"(?:本|这|这个|当)(?:周|星期)", text):
        return _monday(today, 0), today

    rolling = re.search(r"(?:最近|近|过去)\s*(\d{1,3})\s*(天|日)", text)
    if rolling is not None:
        days = max(1, min(int(rolling.group(1)), 366))
        return today.fromordinal(today.toordinal() - days + 1), today
    if re.search(r"(?:最近|近|过去)\s*(?:一|1)?\s*(?:周|星期)", text):
        return today.fromordinal(today.toordinal() - 6), today
    if re.search(r"(?:最近|近|过去)\s*(?:一|1)?\s*个月", text):
        return today.fromordinal(today.toordinal() - 29), today
    if re.search(r"(?:最近|近|过去)\s*(?:三|3)\s*个月|(?:本|这)?季度", text):
        return today.fromordinal(today.toordinal() - 89), today

    if re.search(r"前年", text):
        return date(today.year - 2, 1, 1), date(today.year - 2, 12, 31)
    if re.search(r"去年|上一年|上年", text):
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if re.search(r"今年|本年|本年度", text):
        return date(today.year, 1, 1), today
    return None


def parse_period(text: str, today: date | None = None) -> Period:
    """Resolve the period a business question refers to: day, then month, then range."""
    resolved_today = today or business_today()
    day = parse_day(text, resolved_today)
    month = parse_month(text, resolved_today)
    if day is not None:
        return Period(day=day, month=month or _month_key(day.year, day.month))
    if month is not None:
        return Period(day=None, month=month)
    span = parse_range(text, resolved_today)
    if span is not None:
        return Period(day=None, month=None, start=span[0], end=span[1])
    return Period(day=None, month=None)
