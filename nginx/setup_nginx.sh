#!/bin/bash
# Script to set up nginx for Swiss Cottage AI Assistant

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NGINX_CONF="swiss-cottage-ai.conf"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
NGINX_CONF_PATH="$SCRIPT_DIR/$NGINX_CONF"

echo "=== Nginx Setup for Swiss Cottage AI Assistant ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "⚠️  Nginx is not installed"
    echo "📦 Installing nginx..."
    apt-get update
    apt-get install -y nginx
    echo "✅ Nginx installed"
fi

# Check if nginx configuration file exists
if [ ! -f "$NGINX_CONF_PATH" ]; then
    echo "❌ Nginx configuration file not found: $NGINX_CONF_PATH"
    exit 1
fi

# Copy configuration to sites-available
echo "📋 Copying nginx configuration..."
cp "$NGINX_CONF_PATH" "$NGINX_SITES_AVAILABLE/$NGINX_CONF"
echo "✅ Configuration copied to $NGINX_SITES_AVAILABLE/$NGINX_CONF"

# Create symlink to sites-enabled
if [ -L "$NGINX_SITES_ENABLED/$NGINX_CONF" ]; then
    echo "⚠️  Site already enabled, removing old symlink..."
    rm "$NGINX_SITES_ENABLED/$NGINX_CONF"
fi

echo "🔗 Creating symlink to enable site..."
ln -s "$NGINX_SITES_AVAILABLE/$NGINX_CONF" "$NGINX_SITES_ENABLED/$NGINX_CONF"
echo "✅ Site enabled"

# Remove default nginx site if it exists
if [ -L "$NGINX_SITES_ENABLED/default" ]; then
    echo "⚠️  Removing default nginx site..."
    rm "$NGINX_SITES_ENABLED/default"
    echo "✅ Default site removed"
fi

# Test nginx configuration
echo "🧪 Testing nginx configuration..."
if nginx -t; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration test failed!"
    echo "   Please check the configuration file and try again"
    exit 1
fi

# Reload nginx
echo "🔄 Reloading nginx..."
systemctl reload nginx
echo "✅ Nginx reloaded"

# Check nginx status
if systemctl is-active --quiet nginx; then
    echo "✅ Nginx is running"
else
    echo "⚠️  Starting nginx..."
    systemctl start nginx
    echo "✅ Nginx started"
fi

# Enable nginx to start on boot
systemctl enable nginx

echo ""
echo "🎉 Nginx setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Make sure FastAPI is running on port 8000:"
echo "      cd $PROJECT_DIR && ./run_api.sh"
echo ""
echo "   2. Make sure Streamlit is running on port 8501:"
echo "      cd $PROJECT_DIR && ./run_rag_chatbot.sh"
echo ""
echo "   3. Access your site at:"
echo "      - Streamlit UI: http://localhost/"
echo "      - API: http://localhost/api/"
echo "      - API Docs: http://localhost/docs"
echo ""
echo "   4. If you have a domain name, edit the configuration:"
echo "      sudo nano $NGINX_SITES_AVAILABLE/$NGINX_CONF"
echo "      Change 'server_name _;' to 'server_name your-domain.com;'"
echo "      Then: sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "   5. For HTTPS/SSL, install certbot:"
echo "      sudo apt-get install certbot python3-certbot-nginx"
echo "      sudo certbot --nginx -d your-domain.com"
echo ""
