import unittest

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.access import resolve_department_scope
from app.db import Base
from app.models import Department


class DepartmentScopeTest(unittest.TestCase):
    def test_defaults_to_all_allowed_departments(self):
        self.assertEqual(resolve_department_scope(("sales", "hr"), None), ("sales", "hr"))

    def test_rejects_requested_department_outside_memberships(self):
        with self.assertRaises(PermissionError):
            resolve_department_scope(("sales", "hr"), ["finance"])


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_root_scope_is_read_from_all_departments_in_stable_order(db):
    """Returning the root principal's memberships would hide departments from root queries."""
    db.add_all((Department(id="d2", name="研发"), Department(id="d1", name="销售")))
    db.commit()

    assert resolve_department_scope((), None, is_root=True, db=db) == ("d1", "d2")


def test_root_explicit_scope_rejects_department_missing_from_database(db):
    """Skipping root validation would allow a fabricated department filter into later queries."""
    db.add(Department(id="d1", name="销售"))
    db.commit()

    with pytest.raises(PermissionError):
        resolve_department_scope((), ("does-not-exist",), is_root=True, db=db)


if __name__ == "__main__":
    unittest.main()
