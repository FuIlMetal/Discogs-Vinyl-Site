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

## Raspberry Pi Setup

For detailed instructions on setting up this application as a systemd service on Raspberry Pi, see **[RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md)**.

The setup guide includes:
- Service configuration for automatic startup
- Port configuration (defaults to 8080 to avoid permission issues)
- Optional nginx reverse proxy setup for port 80
- Troubleshooting tips
