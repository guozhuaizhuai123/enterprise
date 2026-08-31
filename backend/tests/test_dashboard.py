import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.audit.service import AuditService
from app.dashboard.service import DashboardService
from app.db import Base
from app.deps import Principal
from app.expense.service import ExpenseService
from app.models import (
    ApprovalInstance,
    AuditLog,
    Department,
    EmployeeProfile,
    ExpenseClaim,
    User,
    UserDepartment,
    UserRole,
)
from app.organization.service import OrganizationService
from app.schemas import AdminEmployeeUpdate
from app.workflow.service import WorkflowService


class DashboardServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.session_factory = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.session_factory()
        self.db.add_all([Department(id="d1", name="研发部"), Department(id="d2", name="销售部")])
        self.db.add_all([
            User(id="hr", username="hr", password_encrypted="x", department_id="d1"),
            User(id="finance", username="finance", password_encrypted="x", department_id="d1"),
            User(id="manager", username="manager", password_encrypted="x", department_id="d1"),
            User(id="employee", username="alice", password_encrypted="x", department_id="d1"),
            User(id="sales", username="sales", password_encrypted="x", department_id="d2"),
        ])
        self.db.flush()
        for user_id, department_id in (("hr", "d1"), ("finance", "d1"), ("manager", "d1"), ("employee", "d1"), ("sales", "d2")):
            self.db.add(UserDepartment(user_id=user_id, department_id=department_id, is_primary=True))
            self.db.add(EmployeeProfile(user_id=user_id, full_name=user_id, status="active", manager_id="manager" if user_id == "employee" else None))
        self.db.add_all([
            UserRole(user_id="hr", role="hr"),
            UserRole(user_id="finance", role="finance", department_id="d1"),
            UserRole(user_id="manager", role="manager", department_id="d1"),
        ])
        self.db.commit()
        definition = WorkflowService.ensure_default_definitions(self.db)
        self.db.flush()
        now = datetime.now(UTC)
        self.db.add_all([
            ExpenseClaim(id="c1", claim_no="BX-1", requester_id="employee", department_id="d1", title="交通", total_amount=Decimal("100.00"), status="payment_pending", created_at=now),
            ExpenseClaim(id="c2", claim_no="BX-2", requester_id="sales", department_id="d2", title="招待", total_amount=Decimal("300.00"), status="paid", created_at=now),
            ExpenseClaim(id="old", claim_no="BX-OLD", requester_id="employee", department_id="d1", title="旧单", total_amount=Decimal("50.00"), status="paid", created_at=now - timedelta(days=60)),
            ApprovalInstance(id="a1", definition_id=definition.id, entity_type="expense_claim", entity_id="c1", requester_id="employee", status="pending_approval"),
        ])
        self.db.commit()
        self.start = date.today() - timedelta(days=7)
        self.end = date.today()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_overview_counts_and_date_boundaries(self):
        principal = Principal("hr", "hr", "employee", "d1", ("d1", "d2"), ("employee", "hr"))
        result = DashboardService.overview(self.db, principal, self.start, self.end)
        self.assertEqual(result["organization"]["active_employees"], 5)
        self.assertEqual(result["organization"]["departments"], 2)
        self.assertEqual(result["expenses"]["payment_pending"]["amount"], Decimal("100.00"))
        self.assertEqual(result["expenses"]["paid"]["amount"], Decimal("300.00"))
        self.assertEqual(result["approvals"]["pending"], 1)
        self.assertEqual(result["period_start"], self.start)

    def test_finance_is_restricted_to_role_department(self):
        principal = Principal("finance", "finance", "employee", "d1", ("d1",), ("employee", "finance"))
        result = DashboardService.overview(self.db, principal, self.start, self.end)
        self.assertEqual(result["expenses"]["payment_pending"]["amount"], Decimal("100.00"))
        self.assertEqual(result["expenses"]["paid"]["amount"], Decimal("0.00"))
        self.assertIsNone(result["organization"])

    def test_audit_sanitizes_secrets_and_records_business_actions(self):
        principal = Principal("hr", "hr", "employee", "d1", ("d1",), ("employee", "hr"))
        AuditService.record(
            self.db,
            principal,
            "test.secret",
            "test",
            "1",
            {"password": "before", "name": "safe"},
            {"api_key": "secret", "name": "changed"},
        )
        self.assertEqual(self.db.query(AuditLog).one().before_data["password"], "[REDACTED]")

        employee = self.db.get(User, "employee")
        OrganizationService.update_employee(self.db, employee, AdminEmployeeUpdate(level="P7"), "hr")
        self.assertIsNotNone(self.db.query(AuditLog).filter_by(action="employee.update").first())

    def test_expense_submit_approval_and_payment_are_audited(self):
        claim = ExpenseService.create_draft(
            self.db,
            requester_id="employee",
            title="审计测试",
            purpose="测试",
            items=[{"expense_date": date.today(), "category": "交通", "description": "", "amount": Decimal("20.00")}],
        )
        ExpenseService.submit(self.db, claim.id, "employee", "audit-submit-key")
        WorkflowService.act(self.db, claim.approval_instance_id, "manager", "approve", "同意", claim.approval_instance.version)
        WorkflowService.act(self.db, claim.approval_instance_id, "finance", "approve", "同意", claim.approval_instance.version)
        ExpenseService.pay(self.db, claim.id, "finance", {"payment_date": date.today(), "method": "bank", "reference": "AUDIT"}, "audit-pay-key", claim.version)
        actions = {row.action for row in self.db.query(AuditLog).all()}
        self.assertTrue({"expense.submit", "approval.approve", "expense.pay"}.issubset(actions))


if __name__ == "__main__":
    unittest.main()
