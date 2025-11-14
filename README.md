# Vinyl-Website
This is my custom website to be hosted on a Raspberry Pi that hits Discogs

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the root directory with your Discogs credentials:
   ```
   DISCOGS_USERNAME=your_discogs_username
   DISCOGS_TOKEN=your_discogs_token
   ```

3. Run the application:
   ```bash
   python app.py
   ```

The `.env` file is excluded from git, so your credentials won't be committed to the repository.
