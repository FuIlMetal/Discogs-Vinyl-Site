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

**Important:** Flask will run on port 8080 internally. We'll use nginx on port 80 to forward requests (see Step 5). This is necessary for DNS routing since DNS doesn't include port numbers.

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

**Note:** After setting up nginx in Step 5, your Flask app will be accessible on port 80 through the nginx reverse proxy, which is required for DNS routing.

## Step 5: Set Up Nginx Reverse Proxy (Required for DNS Routing)

**Why nginx?** DNS doesn't include port numbers - it always routes to port 80 (HTTP) or 443 (HTTPS). Since Flask runs on port 8080 to avoid permission issues, we use nginx on port 80 to forward requests to Flask. This is the standard, secure approach.

### Option A: Use Nginx as Reverse Proxy (Recommended)

1. **Install nginx:**

```bash
sudo apt update
sudo apt install nginx
```

2. **Copy the nginx configuration file:**

```bash
# Copy the provided config file
sudo cp nginx-discogs-vinyl-site.conf /etc/nginx/sites-available/discogs-vinyl-site
```

3. **Edit the configuration if needed:**

```bash
sudo nano /etc/nginx/sites-available/discogs-vinyl-site
```

If you have a specific domain name, update the `server_name` line:
```nginx
server_name your-domain.com;  # Replace with your actual domain
```

If you're using a dynamic DNS or just want to accept all requests, leave it as `server_name _;`

4. **Enable the site and test:**

```bash
# Create symlink to enable the site
sudo ln -s /etc/nginx/sites-available/discogs-vinyl-site /etc/nginx/sites-enabled/

# Remove default nginx site if it exists (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test the nginx configuration
sudo nginx -t

# If test passes, restart nginx
sudo systemctl restart nginx

# Enable nginx to start on boot
sudo systemctl enable nginx
```

5. **Verify it's working:**

- Check nginx status: `sudo systemctl status nginx`
- Visit your domain or Pi's IP address (without port number) - it should work!
- Check nginx logs if needed: `sudo tail -f /var/log/nginx/error.log`

**Alternative: Direct Port 80 Binding (Not Recommended)**

If you prefer Flask to run directly on port 80 (not recommended for security), you can use `setcap`:

```bash
# Install libcap2-bin if not already installed
sudo apt install libcap2-bin

# Give Python the capability to bind to port 80
sudo setcap 'cap_net_bind_service=+ep' /home/pi/Discogs-Vinyl-Site/venv/bin/python3

# Update your .env file to use port 80
# FLASK_PORT=80
```

**Note:** You'll need to re-run `setcap` if you recreate the virtual environment, and you won't need nginx if you use this approach.

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

- Check what's using the port: `sudo netstat -tulpn | grep :8080` (for Flask) or `grep :80` (for nginx)
- If port 80 is in use, check: `sudo systemctl status nginx` or `sudo netstat -tulpn | grep :80`
- Change the port in your `.env` file if needed (and update nginx config accordingly)

### Nginx Not Forwarding to Flask

- Verify Flask is running: `sudo systemctl status discogs-vinyl-site.service`
- Check nginx can reach Flask: `curl http://127.0.0.1:8080` (should return HTML)
- Check nginx error logs: `sudo tail -f /var/log/nginx/error.log`
- Verify nginx config: `sudo nginx -t`
- Make sure the proxy_pass URL in nginx config matches your Flask port (8080)

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

