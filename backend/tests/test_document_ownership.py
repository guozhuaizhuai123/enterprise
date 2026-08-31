import unittest
import inspect

from app.kb import service as kb_service
from app.models import Document


class DocumentOwnershipModelTest(unittest.TestCase):
    def test_document_has_owner_snapshot_fields(self):
        self.assertIn("owner_id", Document.__table__.columns)
        self.assertIn("owner_name", Document.__table__.columns)
        self.assertTrue(Document.__table__.columns["owner_id"].nullable)

    def test_document_service_accepts_owner_metadata(self):
        create_params = inspect.signature(kb_service.create_document).parameters
        update_params = inspect.signature(kb_service.update_document).parameters
        self.assertIn("owner_id", create_params)
        self.assertIn("owner_name", create_params)
        self.assertIn("owner_id", update_params)
        self.assertIn("owner_name", update_params)


if __name__ == "__main__":
    unittest.main()
