#!/bin/bash
# Simple setup script for PubMed MCP API key and email

# Make sure Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3 first."
    exit 1
fi

# Run the Python setup script
python3 setup_api.py "$@"
