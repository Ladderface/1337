import unittest
from agent.scenario_runner import ScenarioRunner

class DummySession:
    def __init__(self):
        pass

class TestScenarioRunner(unittest.TestCase):
    def test_run_stub(self):
        runner = ScenarioRunner(DummySession(), scenario={})
        self.assertIsNone(runner.run())

if __name__ == '__main__':
    unittest.main() 