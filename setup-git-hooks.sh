#!/bin/bash
#
# Setup script to install Git hooks for the repository
# This ensures cache files and other unwanted files cannot be committed
#

echo "Setting up Git hooks..."

# Copy hooks from .githooks to .git/hooks
if [ -d ".githooks" ]; then
    for hook in .githooks/*; do
        if [ -f "$hook" ]; then
            hook_name=$(basename "$hook")
            cp "$hook" ".git/hooks/$hook_name"
            chmod +x ".git/hooks/$hook_name"
            echo "  ✓ Installed $hook_name"
        fi
    done
    echo ""
    echo "✅ Git hooks installed successfully!"
    echo "   Cache files and other unwanted files will now be blocked from commits."
else
    echo "❌ Error: .githooks directory not found!"
    exit 1
fi
