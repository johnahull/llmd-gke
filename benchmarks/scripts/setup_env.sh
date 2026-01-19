#!/bin/bash
# Setup environment for RHAIIS vLLM benchmarks
# Installs dependencies and verifies tools

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$BENCHMARK_DIR")"
VENV_PATH="/home/jhull/devel/venv"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "====================================="
echo "  RHAIIS Benchmark Environment Setup"
echo "====================================="
echo ""

# Check for Python 3
echo -n "Checking Python 3... "
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi

# Check for venv
echo -n "Checking virtual environment... "
if [ -d "$VENV_PATH" ]; then
    echo -e "${GREEN}✓ Found at $VENV_PATH${NC}"
else
    echo -e "${YELLOW}⚠ Not found at $VENV_PATH${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✓ Created${NC}"
fi

# Activate venv
echo -n "Activating virtual environment... "
source "$VENV_PATH/bin/activate"
echo -e "${GREEN}✓ Activated${NC}"

# Install/upgrade pip
echo -n "Upgrading pip... "
pip install --quiet --upgrade pip
echo -e "${GREEN}✓ Done${NC}"

# Install requirements
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements-benchmarks.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Installing Python dependencies..."
    pip install --quiet -r "$REQUIREMENTS_FILE"
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠ requirements-benchmarks.txt not found${NC}"
    echo "Installing core dependencies..."
    pip install --quiet aiohttp requests locust pandas numpy matplotlib seaborn pyyaml jinja2
    echo -e "${GREEN}✓ Core dependencies installed${NC}"
fi

# Check for required tools
echo ""
echo "Checking required tools:"

echo -n "  curl... "
if command -v curl &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Not found (install with: sudo apt-get install curl)${NC}"
fi

echo -n "  jq... "
if command -v jq &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠ Not found (install with: sudo apt-get install jq)${NC}"
    echo "    jq is optional but recommended for JSON parsing"
fi

echo -n "  ab (Apache Bench)... "
if command -v ab &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠ Not found (install with: sudo apt-get install apache2-utils)${NC}"
    echo "    ab is optional, used for simple HTTP load testing"
fi

echo ""
echo -e "${GREEN}====================================="
echo "  Setup complete!"
echo "=====================================${NC}"
echo ""
echo "To activate the virtual environment manually:"
echo "  source $VENV_PATH/bin/activate"
echo ""
echo "To run benchmarks:"
echo "  ./benchmarks/scripts/quick_test.sh"
echo "  python benchmarks/python/benchmark_async.py --help"
