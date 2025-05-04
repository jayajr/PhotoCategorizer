#!/bin/bash

# Exit on error
set -e

echo "Setting up Photo Categorizer with PyQt5..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3 and try again."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing requirements (including PyQt5)..."
pip3 install -r requirements.txt

# Ensure the input and output directories exist
mkdir -p in
mkdir -p out

echo "Starting Photo Categorizer with modern PyQt5 UI..."
echo "Place your photos in the 'in' directory."

# Run the categorizer
python3 main.py

# Deactivate the virtual environment
deactivate

echo "Photo Categorizer closed." 