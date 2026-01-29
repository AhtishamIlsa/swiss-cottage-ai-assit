#!/bin/bash
# Script to install systemd services for Swiss Cottage AI Assistant

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Installing Systemd Services ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Copy service files
echo "📋 Copying systemd service files..."
cp "$SCRIPT_DIR/swiss-cottage-api.service" /etc/systemd/system/
cp "$SCRIPT_DIR/swiss-cottage-streamlit.service" /etc/systemd/system/
echo "✅ Service files copied"

# Reload systemd
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload
echo "✅ Systemd daemon reloaded"

# Enable services
echo "🔧 Enabling services..."
systemctl enable swiss-cottage-api
systemctl enable swiss-cottage-streamlit
echo "✅ Services enabled"

echo ""
echo "🎉 Systemd services installed!"
echo ""
echo "📝 To start the services:"
echo "   sudo systemctl start swiss-cottage-api"
echo "   sudo systemctl start swiss-cottage-streamlit"
echo ""
echo "📝 To check status:"
echo "   sudo systemctl status swiss-cottage-api"
echo "   sudo systemctl status swiss-cottage-streamlit"
echo ""
echo "📝 To view logs:"
echo "   sudo journalctl -u swiss-cottage-api -f"
echo "   sudo journalctl -u swiss-cottage-streamlit -f"
echo ""
