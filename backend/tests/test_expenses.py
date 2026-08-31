import unittest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.expense.service import ExpenseService
from app.models import (
    Department,
    EmployeeProfile,
    PaymentRecord,
    User,
    UserDepartment,
    UserRole,
)
from app.workflow.service import WorkflowService


class ExpenseServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.db = self.session_factory()
        self.db.add(Department(id="d1", name="研发部", code="DEV"))
        self.db.add_all(
            [
                User(id="employee", username="alice", password_encrypted="x", department_id="d1"),
                User(id="no-manager", username="newbie", password_encrypted="x", department_id="d1"),
                User(id="manager", username="manager", password_encrypted="x", department_id="d1"),
                User(id="finance", username="finance", password_encrypted="x", department_id="d1"),
                User(id="outsider", username="outsider", password_encrypted="x", department_id="d1"),
            ]
        )
        self.db.flush()
        for user_id in ("employee", "no-manager", "manager", "finance", "outsider"):
            self.db.add(UserDepartment(user_id=user_id, department_id="d1", is_primary=True))
        self.db.add_all(
            [
                EmployeeProfile(user_id="employee", full_name="艾丽丝", manager_id="manager"),
                EmployeeProfile(user_id="no-manager", full_name="新人"),
                EmployeeProfile(user_id="manager", full_name="马经理"),
                EmployeeProfile(user_id="finance", full_name="方财务"),
                EmployeeProfile(user_id="outsider", full_name="路人"),
                UserRole(user_id="manager", role="manager", department_id="d1"),
                UserRole(user_id="finance", role="finance", department_id="d1"),
            ]
        )
        self.db.commit()
        WorkflowService.ensure_default_definitions(self.db)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_claim(self, requester_id: str = "employee"):
        claim = ExpenseService.create_draft(
            self.db,
            requester_id=requester_id,
            title="客户现场交通费",
            purpose="项目交付",
            items=[
                {"expense_date": date(2026, 8, 20), "category": "交通", "description": "地铁", "amount": Decimal("12.30")},
                {"expense_date": date(2026, 8, 21), "category": "交通", "description": "公交", "amount": Decimal("7.70")},
            ],
        )
        self.db.flush()
        return claim

    def approve_claim(self, claim):
        ExpenseService.submit(self.db, claim.id, "employee", "submit-key-1")
        self.db.flush()
        instance = claim.approval_instance
        WorkflowService.act(self.db, instance.id, "manager", "approve", "同意", instance.version)
        WorkflowService.act(self.db, instance.id, "finance", "approve", "核验完成", instance.version)
        self.db.flush()

    def test_total_is_recalculated_with_decimal_rounding(self):
        claim = self.create_claim()
        self.assertEqual(claim.total_amount, Decimal("20.00"))

    def test_negative_amount_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            ExpenseService.create_draft(
                self.db,
                requester_id="employee",
                title="错误金额",
                purpose="测试",
                items=[{"expense_date": date.today(), "category": "交通", "description": "", "amount": Decimal("-1")}],
            )
        self.assertEqual(context.exception.status_code, 422)

    def test_only_draft_can_be_edited_or_deleted(self):
        claim = self.create_claim()
        ExpenseService.submit(self.db, claim.id, "employee", "submit-key-1")
        with self.assertRaises(HTTPException) as context:
            ExpenseService.update_draft(self.db, claim.id, "employee", title="不能修改")
        self.assertEqual(context.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            ExpenseService.delete_draft(self.db, claim.id, "employee")

    def test_submit_requires_direct_manager_and_is_idempotent(self):
        claim = self.create_claim()
        first = ExpenseService.submit(self.db, claim.id, "employee", "submit-key-1")
        second = ExpenseService.submit(self.db, claim.id, "employee", "submit-key-1")
        self.assertEqual(first.approval_instance_id, second.approval_instance_id)
        missing = self.create_claim("no-manager")
        with self.assertRaises(HTTPException) as context:
            ExpenseService.submit(self.db, missing.id, "no-manager", "submit-key-2")
        self.assertEqual(context.exception.status_code, 422)

    def test_employee_and_manager_visibility(self):
        claim = self.create_claim()
        self.assertTrue(ExpenseService.can_view(self.db, claim, "employee"))
        self.assertTrue(ExpenseService.can_view(self.db, claim, "manager"))
        self.assertFalse(ExpenseService.can_view(self.db, claim, "outsider"))

    def test_only_finance_can_pay_and_payment_is_exactly_once(self):
        claim = self.create_claim()
        self.approve_claim(claim)
        self.assertEqual(claim.status, "payment_pending")
        with self.assertRaises(HTTPException) as context:
            ExpenseService.pay(
                self.db,
                claim.id,
                "manager",
                {"payment_date": date.today(), "method": "bank", "reference": "NO-1"},
                "pay-key-1",
                claim.version,
            )
        self.assertEqual(context.exception.status_code, 403)
        payment = ExpenseService.pay(
            self.db,
            claim.id,
            "finance",
            {"payment_date": date.today(), "method": "bank", "reference": "NO-1"},
            "pay-key-1",
            claim.version,
        )
        duplicate = ExpenseService.pay(
            self.db,
            claim.id,
            "finance",
            {"payment_date": date.today(), "method": "bank", "reference": "NO-1"},
            "pay-key-1",
            claim.version,
        )
        self.assertEqual(payment.id, duplicate.id)
        self.assertEqual(self.db.query(PaymentRecord).count(), 1)
        self.assertEqual(claim.status, "paid")


if __name__ == "__main__":
    unittest.main()
