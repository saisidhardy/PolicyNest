"""Run isolated backend tests without reading project secrets."""
import os
from pathlib import Path
import sys
import unittest
os.environ['POLICYNEST_SKIP_DOTENV']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'policynest_mvp'/'copilot_api'))
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in ['test_auth','test_policy','test_main','test_workflows','test_services'])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
