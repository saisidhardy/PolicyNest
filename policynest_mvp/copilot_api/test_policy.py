"""ABAC unit tests. Run with: python -m unittest test_policy.py"""
import unittest
from policy import allows


class PolicyTest(unittest.TestCase):
    APP = {"applicant_id": 7, "reviewer_id": 9, "status": "DRAFT", "sensitivity": "applicant"}

    def test_applicant_owner_only(self):
        self.assertTrue(allows({"id": 7, "role": "applicant"}, "application.read", self.APP))
        self.assertFalse(allows({"id": 8, "role": "applicant"}, "application.read", self.APP))

    def test_reviewer_must_be_assigned(self):
        self.assertTrue(allows({"id": 9, "role": "reviewer"}, "review.decide", self.APP))
        self.assertFalse(allows({"id": 10, "role": "reviewer"}, "review.decide", self.APP))

    def test_applicant_never_reads_reviewer_only_data(self):
        private = dict(self.APP, sensitivity="reviewer_only")
        self.assertFalse(allows({"id": 7, "role": "applicant"}, "application.read", private))


if __name__ == "__main__":
    unittest.main()
