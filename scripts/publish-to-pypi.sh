#!/usr/bin/env bash
#
# Manual publishing script for SDB
#
# This script builds and publishes SDB to PyPI or TestPyPI.
# For automated releases, use the GitHub Actions workflow instead.
#
# Prerequisites:
#   pip install build twine
#
# Usage:
#   ./scripts/publish-to-pypi.sh          # Publish to PyPI
#   ./scripts/publish-to-pypi.sh test     # Publish to TestPyPI
#
# Authentication:
#   You can authenticate using either:
#   1. API token (recommended): Set TWINE_USERNAME=__token__ and TWINE_PASSWORD=<your-token>
#   2. Interactive: The script will prompt for credentials
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check for required tools
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed."
    exit 1
fi

# Ensure build tools are installed
echo "==> Checking build tools..."
python3 -m pip install --quiet build twine

# Clean previous builds
echo "==> Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info

# Build the package
echo "==> Building package..."
python3 -m build

# Determine target repository
TARGET="${1:-pypi}"

if [[ "$TARGET" == "test" ]]; then
    echo "==> Publishing to TestPyPI..."
    REPOSITORY_URL="https://test.pypi.org/legacy/"
    python3 -m twine upload --repository-url "$REPOSITORY_URL" dist/*
    echo ""
    echo "Package published to TestPyPI!"
    echo "Install with: pip install --index-url https://test.pypi.org/simple/ sdb-debugger"
else
    echo "==> Publishing to PyPI..."
    python3 -m twine upload dist/*
    echo ""
    echo "Package published to PyPI!"
    echo "Install with: pip install sdb-debugger"
fi

echo ""
echo "Done!"
