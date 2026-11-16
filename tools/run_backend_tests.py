"""Run isolated backend tests without reading project secrets."""
import os
from pathlib import Path
import sys
import unittest
os.environ['POLICYNEST_SKIP_DOTENV']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'policynest_mvp'/'copilot_api'))
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in ['test_auth','test_policy','test_main','test_workflows','test_services','test_assistant','test_milestone1_security','test_milestone2_persistence','test_milestone3_documents','test_milestone4_review_ops','test_milestone5_fraud','test_milestone6_training','test_milestone7_exam'])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
