#!/bin/bash
# Update .env file for production domain

set -e

DOMAIN="swisscottaggesai.nextassistai.com"
ENV_FILE=".env"

echo "=== Updating .env for Production Domain ==="
echo ""

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found!"
    exit 1
fi

# Backup
cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
echo "✅ Backup created"

# Update CORS_ORIGINS
if grep -q "CORS_ORIGINS=" "$ENV_FILE"; then
    sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=http://${DOMAIN},https://${DOMAIN}|" "$ENV_FILE"
    echo "✅ Updated CORS_ORIGINS"
else
    echo "CORS_ORIGINS=http://${DOMAIN},https://${DOMAIN}" >> "$ENV_FILE"
    echo "✅ Added CORS_ORIGINS"
fi

# Update API_BASE_URL
if grep -q "API_BASE_URL=" "$ENV_FILE"; then
    sed -i "s|API_BASE_URL=.*|API_BASE_URL=http://${DOMAIN}|" "$ENV_FILE"
    echo "✅ Updated API_BASE_URL"
else
    echo "API_BASE_URL=http://${DOMAIN}" >> "$ENV_FILE"
    echo "✅ Added API_BASE_URL"
fi

echo ""
echo "🎉 .env file updated for production!"
echo ""
echo "Updated values:"
echo "  CORS_ORIGINS=http://${DOMAIN},https://${DOMAIN}"
echo "  API_BASE_URL=http://${DOMAIN}"
echo ""
echo "⚠️  You need to restart services for changes to take effect:"
echo "   ./stop_all_services.sh"
echo "   ./start_all_services.sh"
echo ""
