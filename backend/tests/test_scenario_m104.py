"""Run full M-104 Scenario test as pytest collector."""
from tests.scenario_m104 import test_full_m104_service_lifecycle

def test_m104_full_flow():
    test_full_m104_service_lifecycle()
