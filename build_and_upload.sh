#!/bin/bash

# Build and upload script for apple-search-ads-client

echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info src/*.egg-info

echo "📦 Building distribution packages..."
python3 -m pip install --upgrade build
python3 -m build

echo "📋 Checking distribution..."
python3 -m pip install --upgrade twine
python3 -m twine check dist/*

echo ""
echo "✅ Build complete! Distribution files:"
ls -la dist/

echo ""
echo "To upload to TEST PyPI (recommended first):"
echo "  python3 -m twine upload --repository testpypi dist/*"
echo ""
echo "To upload to PRODUCTION PyPI:"
echo "  python3 -m twine upload dist/*"
echo ""
echo "Make sure you have configured your PyPI credentials in ~/.pypirc"