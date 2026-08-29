#!/bin/bash

# Deployment script for Orb Weaver Code Website
# Domain: codeweaver.certsig.com

set -e  # Exit on any error

PROJECT_DIR="/home/bryan/projects/Orb_Weaver_Code_Website"
SERVICE_NAME="orb-weaver-code"

echo "========================================="
echo "Orb Weaver Code Website - Deployment"
echo "========================================="
echo ""

cd "$PROJECT_DIR"

# Pull latest changes if git repo
if [ -d .git ]; then
    echo "📦 Pulling latest changes..."
    git pull
    echo ""
fi

# Install dependencies
echo "📦 Installing dependencies..."
npm install
echo ""

# Run database migrations
if [ -f "prisma/schema.prisma" ]; then
    echo "🗄️  Running database migrations..."
    npm run db:generate
    npm run db:push
    echo ""
fi

# Build application
echo "🔨 Building application..."
npm run build
echo ""

# Restart service
echo "🔄 Restarting service..."
sudo systemctl restart "$SERVICE_NAME.service"
echo ""

# Wait a moment for service to start
sleep 2

# Check service status
echo "✅ Checking service status..."
if sudo systemctl is-active --quiet "$SERVICE_NAME.service"; then
    echo "✅ Service is running!"
    sudo systemctl status "$SERVICE_NAME.service" --no-pager -l
else
    echo "❌ Service failed to start!"
    sudo journalctl -u "$SERVICE_NAME.service" -n 20 --no-pager
    exit 1
fi

echo ""
echo "========================================="
echo "✨ Deployment complete!"
echo "========================================="
echo ""
echo "Site URL: https://codeweaver.certsig.com"
echo ""
echo "Useful commands:"
echo "  View logs:    sudo journalctl -u $SERVICE_NAME.service -f"
echo "  Restart:      sudo systemctl restart $SERVICE_NAME.service"
echo "  Stop:         sudo systemctl stop $SERVICE_NAME.service"
echo "  Status:       sudo systemctl status $SERVICE_NAME.service"
echo ""
