import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.expense.service import ExpenseService
from app.models import (
    AuditLog,
    Department,
    EmployeeProfile,
    Notification,
    User,
    UserDepartment,
    UserRole,
)
from app.workflow.service import WorkflowService


class PhaseOneSmokeTest(unittest.TestCase):
    def test_end_to_end_expense_flow(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        try:
            db.add(Department(id="d1", name="交付部", code="DELIVERY"))
            for user_id, role in (
                ("admin", "admin"),
                ("hr", "employee"),
                ("manager", "employee"),
                ("finance", "employee"),
                ("employee", "employee"),
                ("other", "employee"),
            ):
                db.add(User(id=user_id, username=user_id, password_encrypted="x", role=role, department_id="d1" if role == "employee" else None))
            db.flush()
            for user_id in ("hr", "manager", "finance", "employee", "other"):
                db.add(UserDepartment(user_id=user_id, department_id="d1", is_primary=True))
                db.add(EmployeeProfile(user_id=user_id, full_name=user_id, manager_id="manager" if user_id == "employee" else None))
            db.add_all([
                EmployeeProfile(user_id="admin", full_name="admin"),
                UserRole(user_id="hr", role="hr"),
                UserRole(user_id="manager", role="manager", department_id="d1"),
                UserRole(user_id="finance", role="finance", department_id="d1"),
            ])
            WorkflowService.ensure_default_definitions(db)
            db.commit()

            claim = ExpenseService.create_draft(
                db,
                requester_id="employee",
                title="客户交付差旅",
                purpose="项目验收",
                items=[
                    {"expense_date": date.today(), "category": "交通", "vendor": "地铁", "amount": Decimal("12.30")},
                    {"expense_date": date.today(), "category": "餐饮", "vendor": "餐厅", "amount": Decimal("87.70")},
                ],
            )
            self.assertEqual(claim.total_amount, Decimal("100.00"))
            ExpenseService.submit(db, claim.id, "employee", "smoke-submit-key")
            instance = claim.approval_instance
            WorkflowService.act(db, instance.id, "manager", "approve", "同意", instance.version)
            WorkflowService.act(db, instance.id, "finance", "approve", "财务核验", instance.version)
            self.assertEqual(claim.status, "payment_pending")
            ExpenseService.pay(
                db,
                claim.id,
                "finance",
                {"payment_date": date.today(), "method": "bank", "reference": "SMOKE-001"},
                "smoke-payment-key",
                claim.version,
            )
            db.commit()

            self.assertEqual(claim.status, "paid")
            self.assertTrue(db.query(Notification).filter_by(recipient_id="employee", expense_claim_id=claim.id).count() >= 1)
            self.assertTrue(db.query(AuditLog).filter_by(entity_id=claim.id).count() >= 2)
            self.assertFalse(ExpenseService.can_view(db, claim, "other"))
        finally:
            db.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
