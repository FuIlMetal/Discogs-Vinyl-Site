# Raspberry Pi Setup Guide

This guide will help you set up the Discogs Vinyl Site on your Raspberry Pi.

## Prerequisites

1. Raspberry Pi with Raspberry Pi OS (or similar Linux distribution)
2. Python 3 installed
3. Git installed

## Step 1: Clone and Install Dependencies

```bash
# Clone the repository (adjust path as needed)
cd ~
git clone <your-repo-url> Discogs-Vinyl-Site
cd Discogs-Vinyl-Site

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Environment Variables

Create a `.env` file in the project root:

```bash
nano .env
```

Add your Discogs credentials:

```
DISCOGS_USERNAME=your_discogs_username
DISCOGS_TOKEN=your_discogs_token
FLASK_PORT=8080
FLASK_DEBUG=False
```

**Note:** The default port is now 8080 (instead of 80) to avoid permission issues. If you want to use port 80, see the "Using Port 80" section below.

## Step 3: Test the Application

Before setting up as a service, test that it works:

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Run the app
python app.py
```

Visit `http://your-pi-ip:8080` in your browser to verify it works. Press `Ctrl+C` to stop.

## Step 4: Set Up as a Systemd Service

1. **Copy the service file to systemd directory:**

```bash
sudo cp discogs-vinyl-site.service /etc/systemd/system/
```

2. **Edit the service file to match your setup:**

```bash
sudo nano /etc/systemd/system/discogs-vinyl-site.service
```

Update these paths if your setup is different:
- `User=pi` - Change if you're using a different user
- `WorkingDirectory=/home/pi/Discogs-Vinyl-Site` - Update to your actual path
- `ExecStart=/home/pi/Discogs-Vinyl-Site/venv/bin/python` - Update to your Python path

3. **Reload systemd and enable the service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable discogs-vinyl-site.service
sudo systemctl start discogs-vinyl-site.service
```

4. **Check the service status:**

```bash
sudo systemctl status discogs-vinyl-site.service
```

5. **View logs if there are issues:**

```bash
sudo journalctl -u discogs-vinyl-site.service -f
```

## Step 5: Using Port 80 (Optional)

If you want to access the site on port 80 (standard HTTP port), you have two options:

### Option A: Use Nginx as Reverse Proxy (Recommended)

1. **Install nginx:**

```bash
sudo apt update
sudo apt install nginx
```

2. **Create nginx configuration:**

```bash
sudo nano /etc/nginx/sites-available/discogs-vinyl-site
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name your-pi-hostname.local;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

3. **Enable the site:**

```bash
sudo ln -s /etc/nginx/sites-available/discogs-vinyl-site /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

### Option B: Allow Python to Bind to Port 80 (Less Secure)

If you want Flask to run directly on port 80, you can use `setcap`:

```bash
# Install libcap2-bin if not already installed
sudo apt install libcap2-bin

# Give Python the capability to bind to port 80
sudo setcap 'cap_net_bind_service=+ep' /home/pi/Discogs-Vinyl-Site/venv/bin/python3

# Update your .env file to use port 80
# FLASK_PORT=80
```

**Note:** This requires updating the service file to use the full path to the Python executable, and you'll need to re-run `setcap` if you recreate the virtual environment.

## Troubleshooting

### Permission Denied Errors

- Make sure the database file (`vinyl_collection.db`) and the project directory are owned by the user running the service:
  ```bash
  sudo chown -R pi:pi /home/pi/Discogs-Vinyl-Site
  ```

### Service Won't Start

- Check the logs: `sudo journalctl -u discogs-vinyl-site.service -n 50`
- Verify the paths in the service file are correct
- Make sure the virtual environment exists and has all dependencies installed
- Verify the `.env` file exists and has correct credentials

### Port Already in Use

- Check what's using the port: `sudo netstat -tulpn | grep :8080`
- Change the port in your `.env` file if needed

### Database Permission Issues

- Ensure the database file is writable:
  ```bash
  chmod 664 vinyl_collection.db
  ```

## Useful Commands

```bash
# Start the service
sudo systemctl start discogs-vinyl-site.service

# Stop the service
sudo systemctl stop discogs-vinyl-site.service

# Restart the service
sudo systemctl restart discogs-vinyl-site.service

# View service status
sudo systemctl status discogs-vinyl-site.service

# View live logs
sudo journalctl -u discogs-vinyl-site.service -f

# Disable service from starting on boot
sudo systemctl disable discogs-vinyl-site.service
```

