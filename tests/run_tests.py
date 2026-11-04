"""
Run the project's standard-library unittest suite.

This file exists so the test suite can run with:

    uv run test

without needing pytest or any other third-party testing tool.
"""

import unittest


def main():
    """
    Run every test file in the tests folder.

    PARAMETERS:
    - None

    RETURNS:
    - 0 when all tests pass
    - 1 when at least one test fails
    """
    print("[INFO] Running tests with Python's built-in unittest module")

    # Step 1: Ask unittest to find files named test_*.py inside tests/.
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover("tests")

    # Step 2: Run the tests with useful detail.
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_result = test_runner.run(test_suite)

    # Step 3: Return a shell-friendly exit code.
    if test_result.wasSuccessful():
        print("[INFO] Tests passed")
        return 0

    print("[ERROR] Tests failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
