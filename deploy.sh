#!/bin/bash
# Deployment script for Discogs Vinyl Site
# Run this after pulling new code to update and restart the service

set -e  # Exit on error

echo "🚀 Starting deployment..."

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run initial setup first."
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📥 Installing/updating dependencies..."
pip install -r requirements.txt --quiet

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Make sure it exists with your Discogs credentials."
fi

# Reload systemd daemon (in case service file changed)
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Restart the service
echo "🔄 Restarting discogs-vinyl-site service..."
sudo systemctl restart discogs-vinyl-site.service

# Wait a moment for service to start
sleep 2

# Check service status
echo "📊 Checking service status..."
if sudo systemctl is-active --quiet discogs-vinyl-site.service; then
    echo "✅ Service is running!"
    echo ""
    echo "📋 Service status:"
    sudo systemctl status discogs-vinyl-site.service --no-pager -l
else
    echo "❌ Service failed to start!"
    echo ""
    echo "📋 Last 20 lines of logs:"
    sudo journalctl -u discogs-vinyl-site.service -n 20 --no-pager
    exit 1
fi

echo ""
echo "✨ Deployment complete!"
echo ""
echo "💡 Useful commands:"
echo "   View logs: sudo journalctl -u discogs-vinyl-site.service -f"
echo "   Check status: sudo systemctl status discogs-vinyl-site.service"
echo "   Test LEDs: curl -X POST http://localhost:8080/api/leds/test"

