"""Server-owned navigation keys available to each authenticated surface."""

from app.deps import Principal


_ADMIN_ROUTE_KEYS = frozenset(
    {
        "tickets",
        "expenses",
        "organization",
        "projects",
        "contracts",
        "knowledge",
        "schedules",
        "payroll",
        "overview",
        "assistant",
    }
)
_EMPLOYEE_ROUTE_KEYS = frozenset(
    {
        "tickets",
        "expenses",
        "organization",
        "overview",
        "assistant",
    }
)


def allowed_route_keys(principal: Principal) -> frozenset[str]:
    """Return route identifiers, never URLs, for the principal's UI shell."""
    return _ADMIN_ROUTE_KEYS if principal.has_role("admin") else _EMPLOYEE_ROUTE_KEYS
