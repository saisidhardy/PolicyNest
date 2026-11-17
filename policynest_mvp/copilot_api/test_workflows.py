import unittest
import auth
import workflows
import test_auth


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        test_auth.AuthStoreTest.setUp(self)

    def test_assignment_appeal_and_cross_user_denial(self):
        applicant = auth.register('owner@example.test','correct horse battery','Applicant')
        other = auth.register('other@example.test','correct horse battery','Other')
        reviewer = auth.register('review@example.test','correct horse battery','Reviewer')
        admin = auth.register('admin@example.test','correct horse battery','Admin')
        with auth._db() as db:
            db.execute("UPDATE users SET role='reviewer' WHERE id=?",(reviewer['id'],))
            db.execute("UPDATE users SET role='admin' WHERE id=?",(admin['id'],))
        reviewer['role']='reviewer'
        admin['role']='admin'
        case=workflows.own_case(applicant)
        appeal=workflows.appeals(applicant,case['id'],'Please reassess this document mismatch.')
        with self.assertRaises(ValueError): workflows.appeals(other,case['id'])
        with self.assertRaises(ValueError): workflows.resolve(reviewer,appeal['reference'],'RESOLVED','A human reviewed the evidence.')
        with self.assertRaises(ValueError): workflows.assign(reviewer,case['id'],reviewer['id'])
        workflows.assign(admin,case['id'],reviewer['id'])
        self.assertEqual(len(workflows.queue(reviewer)),1)
        workflows.resolve(reviewer,appeal['reference'],'RESOLVED','A human reviewed the evidence.')
        self.assertEqual(workflows.appeals(applicant,case['id'])[0]['status'],'RESOLVED')
        self.assertEqual(workflows.own_case(applicant)['status'],'DRAFT')


if __name__=='__main__': unittest.main()
