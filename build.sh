#!/bin/bash

# Exit on error
set -e

echo "Building Photo Categorizer to executable..."

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

# Install dependencies including PyInstaller
echo "Installing requirements (including PyInstaller)..."
pip install -r requirements.txt

# Create directories for output if they don't exist
mkdir -p dist

echo "Building executable with PyInstaller..."

# Build with PyInstaller
# --onefile: Create a single executable
# --windowed: Don't show console window when running the app
# --name: Name of the output executable
# --add-data: Include data files
# --icon: Add icon (if you have one)
pyinstaller --onefile --windowed \
    --name="PhotoCategorizer" \
    --add-data="config.json:." \
    photo_categorizer.py

echo "Build complete! Executable is in the 'dist' directory."

# Create a basic example structure in the dist folder
mkdir -p dist/PhotoCategorizer/in
mkdir -p dist/PhotoCategorizer/out

# Copy the config file
cp config.json dist/PhotoCategorizer/

# Create a simple launcher script for Windows
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "Creating Windows launcher..."
    cat > dist/PhotoCategorizer/launch.bat << EOF
@echo off
echo Starting Photo Categorizer...
start PhotoCategorizer.exe
EOF
fi

echo "Distribution package created in 'dist/PhotoCategorizer'"
echo "You can now distribute the 'dist/PhotoCategorizer' folder."

# Deactivate the virtual environment
deactivate 