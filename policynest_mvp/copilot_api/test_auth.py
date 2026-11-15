"""Auth-store unit tests. Run with: python -m unittest test_auth.py"""
import os
import tempfile
import unittest

os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hmac-signing"
os.environ["JWT_TTL_SECONDS"] = "60"
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ["POLICYNEST_DB_PATH"] = _tmp.name
import auth  # noqa: E402


class AuthStoreTest(unittest.TestCase):
    def setUp(self):
        try: os.unlink(_tmp.name)
        except FileNotFoundError: pass

    def test_register_login_and_owner_snapshot(self):
        user = auth.register("applicant@example.test", "correct horse battery", "Test Applicant")
        self.assertEqual(user["role"], "applicant")
        token = auth.issue(auth.login("applicant@example.test", "correct horse battery"))
        current = auth.authenticate("Bearer " + token)
        self.assertEqual(current["email"], "applicant@example.test")
        auth.save_snapshot(current, {"stage": "Your details", "pan": "SENSITIVE-CANARY"})
        self.assertEqual(auth.load_snapshot(current)["snapshot"]["stage"], "Your details")
        self.assertNotIn('SENSITIVE-CANARY', str(auth.load_snapshot(current)))

    def test_bad_password_and_tampered_token_fail(self):
        auth.register("applicant@example.test", "correct horse battery", "Test Applicant")
        with self.assertRaises(ValueError): auth.login("applicant@example.test", "wrong password")
        token = auth.issue(auth.login("applicant@example.test", "correct horse battery"))
        with self.assertRaises(ValueError): auth.authenticate("Bearer " + token[:-1] + "x")

    def test_refresh_reuse_revokes_replacement(self):
        user = auth.register("a@example.test", "correct horse battery", "Applicant")
        original = auth.new_refresh(user)
        _, replacement = auth.rotate_refresh(original)
        with self.assertRaises(ValueError): auth.rotate_refresh(original)
        with self.assertRaises(ValueError): auth.rotate_refresh(replacement)

    def test_reset_single_use_and_revokes_refresh(self):
        user = auth.register("a@example.test", "correct horse battery", "Applicant")
        refresh = auth.new_refresh(user)
        reset = auth.create_reset(user["email"])
        auth.reset_password(reset, "another secure password")
        with self.assertRaises(ValueError): auth.reset_password(reset, "third secure password")
        with self.assertRaises(ValueError): auth.rotate_refresh(refresh)
        with self.assertRaises(ValueError): auth.login(user["email"], "correct horse battery")
        self.assertEqual(auth.login(user["email"], "another secure password")["id"], user["id"])

    def test_logout_revokes_family(self):
        user = auth.register("a@example.test", "correct horse battery", "Applicant")
        token = auth.new_refresh(user)
        auth.revoke_refresh(token)
        with self.assertRaises(ValueError): auth.rotate_refresh(token)

    def test_logout_invalidates_access_jwt(self):
        user = auth.register('a@example.test', 'correct horse battery', 'Applicant')
        access = auth.issue(user)
        refresh = auth.new_refresh(user)
        auth.revoke_refresh(refresh)
        with self.assertRaises(ValueError): auth.authenticate('Bearer ' + access)

    def test_reset_invalidates_access_jwt(self):
        user = auth.register('a@example.test', 'correct horse battery', 'Applicant')
        access = auth.issue(user)
        auth.reset_password(auth.create_reset(user['email']), 'another secure password')
        with self.assertRaises(ValueError): auth.authenticate('Bearer ' + access)

    def test_expired_access_jwt(self):
        from unittest.mock import patch
        user = auth.register('a@example.test', 'correct horse battery', 'Applicant')
        with patch.object(auth.time, 'time', return_value=100): access = auth.issue(user)
        with self.assertRaises(ValueError): auth.authenticate('Bearer ' + access)


if __name__ == "__main__":
    unittest.main()
