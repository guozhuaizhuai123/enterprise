import unittest

from app.access import resolve_department_scope


class DepartmentScopeTest(unittest.TestCase):
    def test_defaults_to_all_allowed_departments(self):
        self.assertEqual(resolve_department_scope(("sales", "hr"), None), ("sales", "hr"))

    def test_rejects_requested_department_outside_memberships(self):
        with self.assertRaises(PermissionError):
            resolve_department_scope(("sales", "hr"), ["finance"])


if __name__ == "__main__":
    unittest.main()
