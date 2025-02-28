# SteamCMD Downloader Web Interface

A web-based interface for downloading Steam games and content using SteamCMD.

## Features

- Web interface for downloading Steam games
- Anonymous login support for free games
- Progress tracking and status updates
- Download links generation
- Works locally or deployed on Railway

## Setup Instructions

### Local Development

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```
4. Open the URL displayed in the console (ngrok will be used to create a public URL)

### Railway Deployment

1. Create a new Railway project
2. Link your GitHub repository or use the Dockerfile provided
3. Deploy the application
4. (Optional) Set up a Railway volume mount for persistent storage:
   ```
   RAILWAY_VOLUME_MOUNT_PATH=/data
   ```

## Usage

1. If SteamCMD is not installed, click the "Install SteamCMD" button
2. Choose login method:
   - Anonymous login for free games
   - Steam account credentials for games you own
3. Enter the Game ID (App ID) or Steam Store URL
4. Click "Download Game" and monitor the progress
5. Once complete, use the provided download links

## Security Notes

- When providing Steam credentials, they are used only to authenticate with Steam servers
- For security reasons, prefer anonymous login when downloading free content
- All credentials are used only for the current session and are not stored

## Technical Details

- Built with Gradio, FastAPI, and SteamCMD
- Uses ngrok for local tunneling
- Implements real-time progress tracking
- Provides file serving via FastAPI endpoints

## Troubleshooting

If you encounter issues:

- Check the log file (`steamcmd_downloader.log`) for details
- Ensure you have sufficient disk space
- For authentication failures, verify your credentials
- For game ID errors, confirm you're using the correct App ID