#!/bin/bash

# Initial setup script for Orb Weaver Code Website
# Domain: codeweaver.certsig.com

set -e  # Exit on any error

PROJECT_DIR="/home/bryan/projects/Orb_Weaver_Code_Website"
DOMAIN="codeweaver.certsig.com"
SERVICE_NAME="orb-weaver-code"
MONITOR_SERVICE_NAME="code-weaver-session-monitor"

echo "========================================="
echo "Orb Weaver Code Website - Initial Setup"
echo "========================================="
echo ""

cd "$PROJECT_DIR"

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "❌ Please do not run this script as root"
    echo "   Run it as your regular user. It will ask for sudo when needed."
    exit 1
fi

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm install
echo ""

# Build application
echo "🔨 Building application..."
npm run build
echo ""

# Setup systemd service
echo "⚙️  Setting up systemd service..."
if [ ! -f /etc/systemd/system/"$SERVICE_NAME.service" ]; then
    sudo cp orb-weaver-code.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME.service"
    echo "✅ Systemd service installed and enabled"
else
    echo "ℹ️  Systemd service already exists. Updating..."
    sudo cp orb-weaver-code.service /etc/systemd/system/
    sudo systemctl daemon-reload
fi
echo ""

# Setup Session Monitor systemd service
echo "Setting up Session Monitor systemd service..."
sudo cp systemd/"$MONITOR_SERVICE_NAME.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$MONITOR_SERVICE_NAME.service"
sudo systemctl restart "$MONITOR_SERVICE_NAME.service"
echo "Session Monitor service installed, enabled, and started"
echo ""

# Start the service
echo "🚀 Starting service..."
sudo systemctl start "$SERVICE_NAME.service"
sleep 2

# Check if service is running
if sudo systemctl is-active --quiet "$SERVICE_NAME.service"; then
    echo "✅ Service started successfully!"
else
    echo "❌ Service failed to start. Check logs with:"
    echo "   sudo journalctl -u $SERVICE_NAME.service -n 50"
    exit 1
fi
echo ""

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "⚠️  Nginx is not installed. Would you like to install it? (y/n)"
    read -r install_nginx
    if [ "$install_nginx" = "y" ]; then
        echo "📦 Installing nginx..."
        sudo apt update
        sudo apt install -y nginx
    fi
fi

# Setup nginx configuration
if command -v nginx &> /dev/null; then
    echo "⚙️  Setting up nginx configuration..."
    
    if [ ! -f /etc/nginx/sites-available/"$DOMAIN" ]; then
        sudo cp nginx.conf /etc/nginx/sites-available/"$DOMAIN"
        sudo ln -sf /etc/nginx/sites-available/"$DOMAIN" /etc/nginx/sites-enabled/
        echo "✅ Nginx configuration installed"
    else
        echo "ℹ️  Nginx configuration already exists. Updating..."
        sudo cp nginx.conf /etc/nginx/sites-available/"$DOMAIN"
    fi
    
    # Test nginx configuration
    echo "🔍 Testing nginx configuration..."
    sudo nginx -t
    
    # Check if SSL certificate exists
    if [ ! -d /etc/letsencrypt/live/"$DOMAIN" ]; then
        echo ""
        echo "⚠️  SSL certificate not found for $DOMAIN"
        echo "   You need to obtain an SSL certificate. Options:"
        echo ""
        echo "   1. Install certbot and get a certificate:"
        echo "      sudo apt install certbot python3-certbot-nginx"
        echo "      sudo certbot --nginx -d $DOMAIN"
        echo ""
        echo "   2. Or manually place your certificate files at:"
        echo "      /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        echo "      /etc/letsencrypt/live/$DOMAIN/privkey.pem"
        echo ""
        echo "   For now, you can edit /etc/nginx/sites-available/$DOMAIN"
        echo "   to comment out the SSL server block and use HTTP only."
        echo ""
    fi
    
    # Reload nginx
    echo "🔄 Reloading nginx..."
    sudo systemctl reload nginx
    echo ""
fi

# Setup firewall
if command -v ufw &> /dev/null; then
    echo "🔒 Checking firewall status..."
    if sudo ufw status | grep -q "Status: active"; then
        echo "   Ensuring HTTP and HTTPS ports are open..."
        sudo ufw allow 'Nginx Full' 2>/dev/null || true
        sudo ufw allow 80/tcp 2>/dev/null || true
        sudo ufw allow 443/tcp 2>/dev/null || true
    fi
    echo ""
fi

# Final status check
echo "========================================="
echo "✨ Setup Complete!"
echo "========================================="
echo ""
echo "📊 Service Status:"
sudo systemctl status "$SERVICE_NAME.service" --no-pager -l | head -15
echo ""

if command -v nginx &> /dev/null && sudo systemctl is-active --quiet nginx; then
    echo "🌐 Nginx Status: Running"
else
    echo "⚠️  Nginx Status: Not running or not installed"
fi
echo ""

# Test local connection
echo "🔍 Testing local connection..."
if curl -s http://localhost:41000 > /dev/null; then
    echo "✅ Application is responding on localhost:41000"
else
    echo "❌ Application is not responding on localhost:41000"
fi
echo ""

echo "========================================="
echo "Next Steps:"
echo "========================================="
echo ""
echo "1. Ensure DNS is configured:"
echo "   $DOMAIN → $(curl -s ifconfig.me 2>/dev/null || echo 'your-server-ip')"
echo ""
echo "2. If SSL certificate is not set up, run:"
echo "   sudo certbot --nginx -d $DOMAIN"
echo ""
echo "3. Visit your site:"
echo "   https://$DOMAIN"
echo ""
echo "4. For future deployments, run:"
echo "   ./deploy.sh"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u $SERVICE_NAME.service -f"
echo "   sudo journalctl -u $MONITOR_SERVICE_NAME.service -f"
echo ""
