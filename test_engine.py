"""
test_engine.py - Winter Arc Automated Test Discovery & Execution Suite
"""
import sys
import os
import time
import unittest


def run_all_tests():
    """CLI entry point for running the Winter Arc automated test suite."""
    start_time = time.time()
    print("=" * 65)
    print("🛡️  WINTER ARC BOT — AUTOMATED TEST SUITE")
    print("=" * 65)

    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time
    print("=" * 65)
    total_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)

    if result.wasSuccessful():
        print(f"✅ ALL {total_run} TESTS PASSED in {elapsed:.2f}s (100% Success)")
    else:
        print(f"❌ TEST SUITE FAILED: {failures} failures, {errors} errors out of {total_run} tests in {elapsed:.2f}s")
    print("=" * 65)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
