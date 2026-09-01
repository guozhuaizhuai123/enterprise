import os
import unittest
from unittest.mock import patch

from app.config import Settings
from app.security import hash_password, verify_password


class SecurityConfigTest(unittest.TestCase):
    def test_hash_verification_and_wrong_password(self):
        encoded = hash_password("correct-password")
        self.assertTrue(verify_password("correct-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_production_settings_reject_default_secrets(self):
        settings = Settings(
            environment="production",
            jwt_secret="dev-secret-change-me",
            password_enc_key="dev-local-enc-key",
            llm_api_key="configured",
        )
        with self.assertRaises(ValueError):
            settings.require_runtime_secrets()

    def test_production_settings_accept_non_default_secrets(self):
        settings = Settings(
            environment="production",
            jwt_secret="a-long-production-jwt-secret-value",
            password_enc_key="a-long-production-password-key",
            llm_api_key="configured",
            bootstrap_admin_password="another-production-password",
        )
        settings.require_runtime_secrets()

    def test_public_defaults_use_generic_provider_and_reject_placeholder_password(self):
        defaults = Settings(_env_file=None)
        self.assertEqual(defaults.llm_base_url, "https://api.openai.com/v1")
        self.assertEqual(defaults.llm_model, "gpt-4.1-mini")
        self.assertEqual(defaults.bootstrap_admin_username, "admin")
        self.assertEqual(defaults.bootstrap_admin_password, "admin123")

        settings = Settings(
            _env_file=None,
            environment="production",
            jwt_secret="a-long-production-jwt-secret-value",
            password_enc_key="a-long-production-password-key",
            llm_api_key="configured",
            bootstrap_admin_password="replace-with-a-strong-password",
        )
        with self.assertRaises(ValueError):
            settings.require_runtime_secrets()


if __name__ == "__main__":
    unittest.main()
