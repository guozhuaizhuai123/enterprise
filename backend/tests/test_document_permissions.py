import unittest
from types import SimpleNamespace

from app.deps import Principal
from app.routers.kb import assert_document_owner, assert_department_write_access


class EmployeeDocumentPermissionTest(unittest.TestCase):
    def setUp(self):
        self.principal = Principal(
            user_id="employee-1",
            username="alice",
            role="employee",
            department_id="finance",
            department_ids=("finance", "hr"),
        )

    def test_employee_can_write_authorized_department(self):
        assert_department_write_access(self.principal, "hr")

    def test_employee_cannot_write_unauthorized_department(self):
        with self.assertRaises(PermissionError):
            assert_department_write_access(self.principal, "legal")

    def test_employee_can_only_write_owned_document(self):
        assert_document_owner(self.principal, SimpleNamespace(owner_id="employee-1"))
        with self.assertRaises(PermissionError):
            assert_document_owner(self.principal, SimpleNamespace(owner_id="employee-2"))


if __name__ == "__main__":
    unittest.main()
