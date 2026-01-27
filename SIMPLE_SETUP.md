# Simple Chatbot Setup Guide

This guide will help you get the chatbot running quickly and easily.

## Quick Start

### Option 1: Using the Simple Script (Recommended)

```bash
./run_chatbot.sh
```

Or with custom parameters:
```bash
./run_chatbot.sh llama-3.1 1024
```

### Option 2: Using Streamlit Directly

```bash
streamlit run chatbot/chatbot_app.py -- --model llama-3.1 --max-new-tokens 512
```

## Prerequisites

1. **Python 3.10+** installed
2. **System build dependencies** (required for llama-cpp-python):
   ```bash
   # Ubuntu/Debian:
   sudo apt-get install -y build-essential cmake ninja-build python3-dev python3-pip
   
   # Fedora/RHEL/CentOS:
   sudo dnf install -y gcc gcc-c++ make cmake ninja-build python3-devel python3-pip
   ```

3. **Python dependencies installed**:
   ```bash
   # Easy way (recommended):
   ./install_dependencies.sh
   
   # Or manually:
   pip3 install --user streamlit llama-cpp-python sentence-transformers chromadb rich pyfiglet
   ```

4. **Model file** (will be downloaded automatically if missing):
   - The model file (~4-5 GB) will be downloaded automatically when you first run the chatbot
   - Make sure you have enough disk space and a stable internet connection

## Common Issues and Solutions

### Issue: "Model file not found"
**Solution**: The model will be downloaded automatically. Just wait for the download to complete (this may take 10-30 minutes depending on your internet speed).

### Issue: "llama-cpp-python is not installed" or "ninja not found"
**Solution**: 
First install build dependencies:
```bash
# Ubuntu/Debian:
sudo apt-get install -y build-essential cmake ninja-build python3-dev

# Then install llama-cpp-python:
pip3 install --user llama-cpp-python
```

**Or use the automated script:**
```bash
./install_dependencies.sh
```

For GPU acceleration (NVIDIA):
```bash
sudo apt-get install -y build-essential cmake ninja-build python3-dev
CMAKE_ARGS="-DGGML_CUDA=on" pip3 install --user llama-cpp-python
```

For Metal GPU (macOS):
```bash
brew install cmake ninja
CMAKE_ARGS="-DGGML_METAL=on" pip3 install --user llama-cpp-python
```

### Issue: "Streamlit is not installed"
**Solution**:
```bash
pip install streamlit
```

### Issue: Out of Memory
**Solution**: 
- Close other applications
- Use a smaller model (e.g., `llama-3.2:1b` instead of `llama-3.1`)
- Reduce `max-new-tokens` parameter

### Issue: Chatbot is slow
**Solution**:
- Make sure you're using GPU acceleration if available
- Reduce `max-new-tokens` parameter
- Use a smaller model

## Available Models

- `llama-3.1` - Recommended, 8B parameters
- `llama-3.2:1b` - Smaller, faster, 1B parameters
- `llama-3.2` - 3B parameters
- `phi-3.5` - 3.8B parameters
- `qwen-2.5:3b` - 3B parameters
- `stablelm-zephyr` - 3B parameters

## Features

✅ **Simple and Easy to Use**: Just run the script and start chatting
✅ **Better Error Messages**: Clear messages when something goes wrong
✅ **Automatic Model Download**: Downloads models automatically if missing
✅ **Error Handling**: Graceful error handling with helpful suggestions
✅ **Progress Indicators**: Shows loading states and progress

## Troubleshooting

If you encounter any issues:

1. Check that all dependencies are installed
2. Verify Python version is 3.10+
3. Check available disk space (need at least 5 GB for model)
4. Check internet connection (for model download)
5. Review error messages - they now provide helpful suggestions

## Need Help?

Check the main README.md for more detailed information about the project.
