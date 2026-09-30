"""
test_engine.py - Winter Arc Test Discovery Runner

Discovers and executes all modular test suites inside the tests/ package.
Maintains backward compatibility with:
    python test_engine.py
    python -m unittest test_engine.py
"""
import sys
import os
import unittest


def load_tests(loader, tests, pattern):
    """Standard unittest hook for test discovery when invoked via unittest test_engine.py."""
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    return loader.discover(start_dir=tests_dir, pattern="test_*.py")


def main():
    """CLI entry point for python test_engine.py."""
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
