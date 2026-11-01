# Vinyl-Website
This is my custom website to be hosted on a Raspberry Pi that hits Discogs

## Quick Setup (Windows/Local Development)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the root directory with your Discogs credentials:
   ```
   DISCOGS_USERNAME=your_discogs_username
   DISCOGS_TOKEN=your_discogs_token
   FLASK_PORT=8080
   FLASK_DEBUG=True
   ```

3. Run the application:
   ```bash
   python app.py
   ```

The `.env` file is excluded from git, so your credentials won't be committed to the repository.

## Raspberry Pi Setup (DNS Routing)

**For DNS routing:** Since DNS doesn't include port numbers, you need nginx on port 80 to forward to Flask on port 8080.

See **[RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md)** for complete setup instructions, including:
- Systemd service configuration
- **Nginx reverse proxy setup (required for DNS)**
- Troubleshooting

**Quick nginx setup:** After setting up the Flask service, run:
```bash
chmod +x setup-nginx.sh && ./setup-nginx.sh
```

## Deployment

After pulling new code, use the deployment script:
```bash
chmod +x deploy.sh  # First time only
./deploy.sh
```

This automatically:
- Updates dependencies
- Reloads systemd
- Restarts the service
- Shows status

## LED Strip Setup

If you're using the WS2812B LED strip feature, see **[LED_SETUP.md](LED_SETUP.md)** for:
- Hardware wiring (GPIO 10 / Physical Pin 19)
- Software setup and permissions
- Troubleshooting guide

## Automatic deploys on the Raspberry Pi

Once set up, the Pi checks GitHub every 5 minutes. If `main` has new commits it pulls them, installs requirements, and restarts `discogs-vinyl-site.service`. To deploy, merge to `main`.

One-time setup on the Pi, from the repo directory:

```bash
git pull
bash deploy/install-auto-update.sh
```

Check recent deploys with `journalctl -u vinyl-update -n 20`. Run `sudo systemctl start vinyl-update` to deploy right away.

## Adding records and play counts

The **➕ Add Record** button searches Discogs and adds releases to your collection.

If your Discogs collection has a custom field named **Plays** (Discogs > Collection > Settings > Custom fields, type text), play counts are stored there so every device sees the same counts. After creating the field, upload existing counts once from the Pi with `venv/bin/python migrate_plays_to_discogs.py --dry-run`, then without `--dry-run`.
