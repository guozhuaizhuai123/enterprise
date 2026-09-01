"""Side-effect-free previews for the closed set of assistant business forms."""

import re
from datetime import date, timedelta
from typing import Any

from app.schedule.service import preview_leave
from app.schemas import ExpensePreviewOut, TicketPreviewOut


# Spoken fault reports rarely contain the word 工单: they name the broken thing
# and ask for someone to handle it.  Both halves must appear, and a policy
# question ("报修流程是什么") must still reach the knowledge base.  The planner
# and this module share the rule so a routed form always has a filled preview.
_FAULT_CUE = re.compile(
    r"(?:有问题|有故障|故障|异常|报错|出错|错误|bug|坏了|打不开|连不上|用不了|不能用|"
    r"无法(?:使用|访问|打开|登录|提交)|不对|卡住|卡死|失败)",
    re.IGNORECASE,
)
_HELP_CUE = re.compile(
    r"(?:帮我|帮忙|麻烦|请|谁能|找)[^。！？]{0,12}?(?:找|处理|协助|支持|看一下|看看|修)"
)
_POLICY_QUESTION_CUE = re.compile(r"(?:是什么|为什么|如何|怎么|制度|流程|规定|政策|说明|含义)")


def is_reported_fault(text: str) -> bool:
    """Return True for a spoken problem report that should become a ticket."""
    return (
        _FAULT_CUE.search(text) is not None
        and _HELP_CUE.search(text) is not None
        and _POLICY_QUESTION_CUE.search(text) is None
    )


def _fault_subject(text: str) -> str:
    """Return the clause naming the broken thing, not the requested helper."""
    clause = re.split(r"(?:帮我|帮忙|麻烦|请|谁能)", text, maxsplit=1)[0]
    return clause.strip().strip("，,。.！!？? ")[:30]


def _preview_ticket(text: str) -> TicketPreviewOut:
    direct_request = bool(
        re.search(r"(?:帮我|替我|给我|我要|我想|我需要).{0,30}(?:发|提|创|建).{0,10}(?:工单|协助|请求|ticket)", text)
    )
    question_request = bool(re.search(r"(?:问|咨询|询问).{0,20}(?:业务|问题|管理员|行政|财务|人事)", text))
    issue_request = bool(re.search(r"(?:反馈|报|反映).{0,20}(?:问题|bug|错误|异常)", text))
    assisted_issue_request = bool(
        re.search(r"(?:有问题|故障|异常|bug|错误).*(?:帮我|麻烦|请).*(?:找|处理|协助)", text, re.IGNORECASE)
    ) or is_reported_fault(text)
    cross_request = bool(re.search(r"(?:跨部门|别的部门|其他部门|别的组)", text))
    same_request = bool(re.search(r"(?:同部门|我们部门|本部门|部门内|同事|找|给).{0,15}(?:同事|同学|员工)", text))

    if not (direct_request or question_request or issue_request or assisted_issue_request or cross_request or same_request):
        return TicketPreviewOut(is_ticket_request=False)

    subject = ""
    if is_reported_fault(text):
        subject = _fault_subject(text)
    if not subject:
        match = re.search(r"(?:关于|帮我对接|请帮忙核对|帮我核对|帮我确认|请协助|帮我联系|找)\s*(.{2,30}?)(?:，|,|。|\.\s|$)", text)
        if match:
            subject = match.group(1).strip().rstrip("，。.")
    if not subject:
        subject = text.strip()[:30]

    target_username = None
    for pattern in (
        r"(?:给|找|让|叫|让).{0,2}([^，,。\s]{2,12})(?:处理|跟进|核对|看|办)",
        r"(?:处理人|负责人|协助人).{0,2}([^，,。\s]{2,12})",
        r"(?:同事|同学)([^，,。\s]{2,12})",
    ):
        match = re.search(pattern, text)
        if match:
            target_username = match.group(1).strip()
            break

    department_name = None
    match = re.search(r"([^\s]{1,10}部门)", text)
    if match:
        department_name = match.group(1).strip()
    else:
        # 口语里常说"找信息部处理"，只在明确的委派动词后面接受"…部"
        match = re.search(r"(?:找|给|由|让|转)([^\s，,。]{2,8}部)(?![门长])", text)
        if match:
            department_name = match.group(1).strip()

    ticket_type = None
    if cross_request:
        ticket_type = "cross_department"
    elif question_request:
        ticket_type = "question"
    elif issue_request or assisted_issue_request:
        ticket_type = "issue"
    elif same_request or direct_request:
        ticket_type = "same_department"

    return TicketPreviewOut(
        is_ticket_request=True,
        ticket_type=ticket_type,
        subject=subject or None,
        description=text.strip(),
        target_username=target_username,
        department_name=department_name,
    )


def _preview_expense(text: str) -> ExpensePreviewOut:
    action = bool(re.search(r"(?:帮我|替我|给我|我要|我想|我需要).{0,30}(?:报销|申请报销|报账|填报销|提报销)", text))
    if not action and not re.search(r"(?:报销|费用|发票|出差|交通|餐饮|招待)", text):
        return ExpensePreviewOut(is_expense_request=False)

    title = None
    for pattern in (r"(?:报销|费用)\s*([^\d，,。\s]{2,20})", r"(?:关于|用于)\s*([^\d，,。\s]{2,20})"):
        match = re.search(pattern, text)
        if match:
            title = match.group(1).strip().rstrip("，。")
            break
    if not title:
        title = "费用报销"

    total_amount = None
    for pattern in (r"(\d+(?:\.\d{1,2})?)\s*(?:元|块|CNY|RMB)", r"(?:金额|共|总计|合计).{0,3}(\d+(?:\.\d{1,2})?)"):
        match = re.search(pattern, text)
        if match:
            total_amount = match.group(1)
            break

    category = None
    category_keywords = {
        "交通": ("交通", "打车", "出租车", "地铁", "公交", "高铁", "火车", "机票", "油费", "停车费"),
        "餐饮": ("餐饮", "吃饭", "餐费", "午餐", "晚餐", "招待", "宴请"),
        "住宿": ("住宿", "酒店", "宾馆", "旅店"),
        "办公": ("办公", "文具", "打印", "耗材"),
        "通讯": ("通讯", "电话", "手机", "宽带", "网络"),
        "差旅": ("差旅", "出差", "差费"),
    }
    for candidate, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            category = candidate
            break

    department_name = None
    match = re.search(r"([^\s]{1,10}部门)", text)
    if match:
        department_name = match.group(1).strip()

    purpose = text.strip()[:200]
    return ExpensePreviewOut(
        is_expense_request=True,
        title=title,
        purpose=purpose,
        total_amount=total_amount,
        category=category,
        department_name=department_name,
        description=purpose,
    )


def _leave_preview(text: str, today: date) -> dict[str, Any]:
    preview = preview_leave(text, today).model_dump(mode="json")
    duration = re.search(r"(?:请假|休假)(?:共|一共)?\s*([一二两三四五六七八九十\d]+)天", text)
    if duration is None:
        duration = re.search(r"([一二两三四五六七八九十\d]+)天", text)
    chinese_numbers = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if duration and preview.get("start_date"):
        raw_days = duration.group(1)
        days = int(raw_days) if raw_days.isdigit() else chinese_numbers.get(raw_days)
        if days:
            start = date.fromisoformat(preview["start_date"])
            preview["end_date"] = (start + timedelta(days=days - 1)).isoformat()
    return preview


def preview_form(form: str, text: str, today: date | None = None) -> dict[str, Any]:
    """Return a JSON-safe preview for a server-owned form key."""
    if form == "leave":
        return _leave_preview(text, today or date.today())
    if form == "ticket":
        return _preview_ticket(text).model_dump(mode="json")
    if form == "expense":
        return _preview_expense(text).model_dump(mode="json")
    raise ValueError("unsupported form")
