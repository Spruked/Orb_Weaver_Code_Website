# Deployment Instructions for Orb Weaver Code Website

## Domain Configuration
**Domain:** codeweaver.certsig.com

## Prerequisites

1. **Node.js and npm installed**
   ```bash
   node --version  # Should be v18 or higher
   npm --version
   ```

2. **Build the application**
   ```bash
   cd /home/bryan/projects/Orb_Weaver_Code_Website
   npm install
   npm run build
   ```

## Option 1: Systemd Service (Recommended)

### Setup Steps

1. **Copy the service file to systemd directory**
   ```bash
   sudo cp orb-weaver-code.service /etc/systemd/system/
   ```

2. **Reload systemd daemon**
   ```bash
   sudo systemctl daemon-reload
   ```

3. **Enable the service (auto-start on boot)**
   ```bash
   sudo systemctl enable orb-weaver-code.service
   ```

4. **Start the service**
   ```bash
   sudo systemctl start orb-weaver-code.service
   ```

5. **Check service status**
   ```bash
   sudo systemctl status orb-weaver-code.service
   ```

### Service Management Commands

```bash
# Start service
sudo systemctl start orb-weaver-code.service

# Stop service
sudo systemctl stop orb-weaver-code.service

# Restart service
sudo systemctl restart orb-weaver-code.service

# View logs
sudo journalctl -u orb-weaver-code.service -f

# Check if enabled on boot
sudo systemctl is-enabled orb-weaver-code.service
```

## Option 2: PM2 (Alternative)

### Setup Steps

1. **Install PM2 globally**
   ```bash
   npm install -g pm2
   ```

2. **Start the application with PM2**
   ```bash
   cd /home/bryan/projects/Orb_Weaver_Code_Website
   pm2 start ecosystem.config.js
   ```

3. **Save PM2 process list**
   ```bash
   pm2 save
   ```

4. **Enable PM2 startup script**
   ```bash
   pm2 startup systemd
   # Follow the command output to run the generated startup command
   ```

### PM2 Management Commands

```bash
# View running applications
pm2 list

# View logs
pm2 logs orb-weaver-code

# Restart application
pm2 restart orb-weaver-code

# Stop application
pm2 stop orb-weaver-code

# Delete application from PM2
pm2 delete orb-weaver-code

# Monitor resources
pm2 monit
```

## Nginx Configuration

### Setup Steps

1. **Install nginx (if not already installed)**
   ```bash
   sudo apt update
   sudo apt install nginx
   ```

2. **Copy nginx configuration**
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/codeweaver.certsig.com
   ```

3. **Enable the site**
   ```bash
   sudo ln -s /etc/nginx/sites-available/codeweaver.certsig.com /etc/nginx/sites-enabled/
   ```

4. **Test nginx configuration**
   ```bash
   sudo nginx -t
   ```

5. **Install SSL certificate with Certbot**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d codeweaver.certsig.com
   ```

   **Note:** If you already have the SSL certificates in `/etc/letsencrypt/`, skip this step.

6. **Reload nginx**
   ```bash
   sudo systemctl reload nginx
   ```

### Nginx Management Commands

```bash
# Start nginx
sudo systemctl start nginx

# Stop nginx
sudo systemctl stop nginx

# Restart nginx
sudo systemctl restart nginx

# Reload configuration (no downtime)
sudo systemctl reload nginx

# Check status
sudo systemctl status nginx

# View error logs
sudo tail -f /var/log/nginx/codeweaver.certsig.com.error.log

# View access logs
sudo tail -f /var/log/nginx/codeweaver.certsig.com.access.log
```

## Environment Variables

Create a `.env.local` file in the project root with required environment variables:

```bash
# Database
DATABASE_URL="your_database_connection_string"

# JWT Secret
JWT_SECRET="your_secure_jwt_secret_here"

# Node Environment
NODE_ENV=production

# Port (optional, default is 3000)
PORT=41000
```

## SSL Certificate Renewal

Certbot automatically sets up certificate renewal. To test:

```bash
sudo certbot renew --dry-run
```

## Firewall Configuration

Ensure ports are open:

```bash
# Allow nginx
sudo ufw allow 'Nginx Full'

# Or manually
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check status
sudo ufw status
```

## DNS Configuration

Ensure your DNS has an A record pointing to your server:

```
Type: A
Name: codeweaver (or @)
Value: Your_Server_IP_Address
TTL: 3600
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u orb-weaver-code.service -n 50

# Check if port 41000 is already in use
sudo lsof -i :41000

# Verify application builds successfully
cd /home/bryan/projects/Orb_Weaver_Code_Website
npm run build
```

### Nginx errors
```bash
# Check nginx error log
sudo tail -f /var/log/nginx/error.log

# Verify nginx syntax
sudo nginx -t

# Check if Next.js is running
curl http://localhost:41000
```

### SSL issues
```bash
# Verify certificate files exist
sudo ls -la /etc/letsencrypt/live/codeweaver.certsig.com/

# Force certificate renewal
sudo certbot renew --force-renewal
```

## Quick Deployment Script

Create a `deploy.sh` script for easy updates:

```bash
#!/bin/bash

cd /home/bryan/projects/Orb_Weaver_Code_Website

echo "Pulling latest changes..."
git pull

echo "Installing dependencies..."
npm install

echo "Running database migrations..."
npm run db:push

echo "Building application..."
npm run build

echo "Restarting service..."
sudo systemctl restart orb-weaver-code.service

echo "Checking service status..."
sudo systemctl status orb-weaver-code.service

echo "Deployment complete!"
```

Make it executable:
```bash
chmod +x deploy.sh
```

## Monitoring

### Check if site is accessible
```bash
curl -I https://codeweaver.certsig.com
```

### Monitor system resources
```bash
# Check memory usage
free -h

# Check disk space
df -h

# Check process
ps aux | grep next
```

## Complete Setup Commands (Quick Reference)

```bash
# Build application
cd /home/bryan/projects/Orb_Weaver_Code_Website
npm install
npm run build

# Setup systemd service
sudo cp orb-weaver-code.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable orb-weaver-code.service
sudo systemctl start orb-weaver-code.service

# Setup nginx
sudo cp nginx.conf /etc/nginx/sites-available/codeweaver.certsig.com
sudo ln -s /etc/nginx/sites-available/codeweaver.certsig.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d codeweaver.certsig.com
sudo systemctl reload nginx

# Verify everything is working
sudo systemctl status orb-weaver-code.service
curl -I https://codeweaver.certsig.com
```
