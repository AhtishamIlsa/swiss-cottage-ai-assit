#!/bin/bash
# Script to install all dependencies needed for the chatbot

set -e

echo "=== Installing Chatbot Dependencies ==="
echo ""

# Check if running as root (for apt install)
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else
    SUDO="sudo"
    echo "⚠️  This script will need sudo privileges to install system packages"
    echo ""
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "❌ Cannot detect OS. Please install dependencies manually."
    exit 1
fi

echo "📦 Detected OS: $OS"
echo ""

# Install system dependencies
echo "🔧 Installing system build dependencies..."
if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    $SUDO apt-get update
    $SUDO apt-get install -y \
        build-essential \
        cmake \
        ninja-build \
        python3-dev \
        python3-pip \
        git
elif [ "$OS" = "fedora" ] || [ "$OS" = "rhel" ] || [ "$OS" = "centos" ]; then
    $SUDO dnf install -y \
        gcc \
        gcc-c++ \
        make \
        cmake \
        ninja-build \
        python3-devel \
        python3-pip \
        git
else
    echo "⚠️  Unknown OS. Please install manually:"
    echo "   - build-essential / gcc, g++, make"
    echo "   - cmake"
    echo "   - ninja-build"
    echo "   - python3-dev / python3-devel"
    echo "   - python3-pip"
    exit 1
fi

echo "✅ System dependencies installed"
echo ""

# Check Python version
echo "🐍 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Python version: $PYTHON_VERSION"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "❌ Python 3.10+ is required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python version OK"
echo ""

# Install Python dependencies
echo "📚 Installing Python dependencies..."
pip3 install --user --upgrade pip setuptools wheel

# Try to install llama-cpp-python
echo ""
echo "🔨 Installing llama-cpp-python..."
echo "   This may take 5-10 minutes as it needs to compile from source..."
echo ""

if pip3 install --user llama-cpp-python; then
    echo "✅ llama-cpp-python installed successfully"
else
    echo "❌ Failed to install llama-cpp-python"
    echo ""
    echo "💡 Alternative: Try installing with pre-built wheel (if available):"
    echo "   pip3 install --user llama-cpp-python --only-binary :all:"
    echo ""
    echo "💡 Or try installing from a specific version:"
    echo "   pip3 install --user llama-cpp-python==0.2.20"
    exit 1
fi

echo ""
echo "📦 Installing other Python dependencies..."
pip3 install --user streamlit sentence-transformers chromadb rich pyfiglet requests tqdm numpy

echo ""
echo "✅ All dependencies installed!"
echo ""
echo "🚀 You can now run the chatbot with:"
echo "   ./run_chatbot.sh"
echo ""
