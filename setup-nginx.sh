#!/bin/bash
# Quick setup script for nginx reverse proxy
# Run this after setting up the Flask service

echo "Setting up nginx reverse proxy for Discogs Vinyl Site..."

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    sudo apt update
    sudo apt install -y nginx
fi

# Copy nginx config
echo "Copying nginx configuration..."
sudo cp nginx-discogs-vinyl-site.conf /etc/nginx/sites-available/discogs-vinyl-site

# Enable the site
echo "Enabling nginx site..."
sudo ln -sf /etc/nginx/sites-available/discogs-vinyl-site /etc/nginx/sites-enabled/

# Remove default site if it exists (both symlink and any conflicting configs)
echo "Disabling default nginx site..."
if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "  Removed default site symlink"
fi
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "  Removed default site file"
fi

# Also check for any other conflicting configs
if ls /etc/nginx/sites-enabled/*.conf 2>/dev/null | grep -v discogs-vinyl-site > /dev/null; then
    echo "  Warning: Other nginx configs found. You may need to disable them manually."
fi

# Test nginx configuration
echo "Testing nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "Nginx configuration is valid. Restarting nginx..."
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    echo "✓ Nginx is now running on port 80 and forwarding to Flask on port 8080"
    echo "✓ Your site should now be accessible via DNS without specifying a port"
else
    echo "✗ Nginx configuration test failed. Please check the configuration manually."
    exit 1
fi

