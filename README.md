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
