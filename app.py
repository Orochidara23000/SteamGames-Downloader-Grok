import gradio as gr
import os
import subprocess
import logging
import re
import time
import requests
from pyngrok import ngrok
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Configuration
IS_RAILWAY = os.environ.get("RAILWAY_ENVIRONMENT") is not None
BASE_DIR = os.getcwd()
STEAMCMD_DIR = os.path.join(BASE_DIR, "steamcmd")
LOG_FILE = os.path.join(BASE_DIR, "steamcmd.log")
PORT = int(os.environ.get("PORT", 7860))  # Railway assigns PORT
PUBLIC_URL = None  # Will be set dynamically

# Adjust download directory for Railway's ephemeral filesystem
if IS_RAILWAY:
    # Consider using Railway's volume mount point if configured
    VOLUME_MOUNT = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if VOLUME_MOUNT:
        DOWNLOAD_DIR = os.path.join(VOLUME_MOUNT, "downloads")
    else:
        DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    
    # Set public URL correctly
    PUBLIC_URL = f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')}"
else:
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

STEAMCMD_PATH = os.path.join(STEAMCMD_DIR, "steamcmd.sh" if os.name == 'posix' else "steamcmd.exe")

# Set up logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'steamcmd_downloader.log'),
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Create directories at startup
def ensure_directories():
    """Ensure all required directories exist."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(STEAMCMD_DIR, exist_ok=True)
    logging.info(f"Directories ensured: {DOWNLOAD_DIR}, {STEAMCMD_DIR}")

# Step 1: Environment & System Check
def check_steamcmd():
    """Verify if SteamCMD is installed."""
    exists = os.path.exists(STEAMCMD_PATH)
    logging.info(f"SteamCMD check: {'Installed' if exists else 'Missing'}")
    return exists

def install_steamcmd():
    """Install SteamCMD if missing."""
    try:
        ensure_directories()
        
        if os.name == 'posix':  # Linux (Railway default)
            subprocess.run("wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz -O steamcmd.tar.gz", shell=True, check=True)
            subprocess.run(f"tar -xvzf steamcmd.tar.gz -C {STEAMCMD_DIR}", shell=True, check=True)
            os.remove("steamcmd.tar.gz")
        elif os.name == 'nt':  # Windows (for local testing)
            subprocess.run("curl -o steamcmd.zip https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip", shell=True, check=True)
            subprocess.run(f"unzip steamcmd.zip -d {STEAMCMD_DIR}", shell=True, check=True)
            os.remove("steamcmd.zip")
        
        logging.info("SteamCMD installed successfully")
        return "SteamCMD installed successfully. Please refresh the page."
    except Exception as e:
        logging.error(f"SteamCMD installation failed: {str(e)}")
        return f"Installation failed: {str(e)}"

def extract_game_id(input_str):
    """Extract game ID from URL or direct input."""
    if not input_str:
        return None
        
    if input_str.startswith("http"):
        match = re.search(r'store\.steampowered\.com/app/(\d+)', input_str)
        return match.group(1) if match else None
    return input_str if input_str.isdigit() else None

# Step 3: User Authentication & Validation
def validate_login(username, password, anonymous, game_id):
    """Validate login credentials or anonymous access."""
    if not game_id:
        return False, "Invalid Game ID or URL"
    if anonymous:
        return True, "Proceeding with anonymous login"
    if not username or not password:
        return False, "Username and password required for non-anonymous login"
    # Basic validation (actual verification happens via SteamCMD output parsing)
    return True, "Credentials provided"

# Step 4 & 5: Download Management & Real-Time Progress
def parse_progress(output):
    """Improved progress parsing with better error detection."""
    if "Login Failure" in output or "Invalid Password" in output:
        return "Authentication failed: Invalid username or password"
    elif "Invalid App ID" in output:
        return "Invalid game ID"
    elif "No space left on device" in output:
        return "Error: Insufficient disk space"
    elif "ERROR" in output:
        # Extract specific error message
        error_match = re.search(r'ERROR\s*:\s*(.+)$', output, re.MULTILINE)
        if error_match:
            return f"Error: {error_match.group(1)}"
        return "Download error occurred"
        
    # Try multiple progress patterns
    patterns = [
        r'Progress: (\d+\.\d+)%',
        r'(\d+\.\d+)% complete',
        r'(\d+)% \(\d+/\d+\)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
                
    return None

def start_download(game_id, username, password, anonymous):
    """Initiate download and yield progress updates."""
    game_id = extract_game_id(game_id)
    valid, message = validate_login(username, password, anonymous, game_id)
    if not valid:
        yield gr.update(value=0), "", "", "", message, ""
        return

    ensure_directories()  # Make sure directories exist
    login_cmd = "+login anonymous" if anonymous else f"+login {username} {password}"
    cmd = f"{STEAMCMD_PATH} {login_cmd} +force_install_dir {DOWNLOAD_DIR} +app_update {game_id} validate +quit"

    # Start download in subprocess
    with open(LOG_FILE, "w") as log:
        process = subprocess.Popen(cmd, shell=True, stdout=log, stderr=log)

    start_time = time.time()
    while process.poll() is None:
        time.sleep(1)
        with open(LOG_FILE, "r") as log:
            output = log.read()
            progress = parse_progress(output)
            if isinstance(progress, str):  # Error detected
                yield gr.update(value=0), "", "", "", progress, ""
                process.terminate()
                return
            elif progress is not None:
                elapsed = f"{time.time() - start_time:.2f} s"
                # Placeholder for remaining time and file size (requires more parsing)
                yield gr.update(value=progress), elapsed, "Calculating...", "N/A", "Downloading...", ""
    
    # Download completed
    elapsed = f"{time.time() - start_time:.2f} s"
    
    # Get all files in the download directory recursively
    file_paths = []
    for root, _, files in os.walk(DOWNLOAD_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, DOWNLOAD_DIR)
            file_paths.append(rel_path)
    
    # Create download links
    links = [f"{PUBLIC_URL}/downloads/{file}" for file in file_paths] if file_paths else ["No files downloaded"]
    
    logging.info(f"Download completed for game {game_id}: {len(file_paths)} files")
    yield gr.update(value=100), elapsed, "0 s", "N/A", "Download completed", "\n".join(links[:20]) + ("\n...\n(more files available)" if len(links) > 20 else "")

# Step 2: Gradio Interface Setup
def create_interface():
    with gr.Blocks(title="SteamCMD Downloader") as app:
        gr.Markdown("# SteamCMD Downloader")
        
        # System Check
        steamcmd_status = gr.Markdown("Checking SteamCMD status...")
        
        # Installation section
        with gr.Row(visible=not check_steamcmd()) as install_row:
            gr.Markdown("SteamCMD not found.")
            install_btn = gr.Button("Install SteamCMD")
            install_output = gr.Textbox(label="Installation Status")
        
        # Login Form
        with gr.Group():
            gr.Markdown("## Game Selection")
            anonymous = gr.Checkbox(label="Login Anonymously (for free games)", value=True)
            
            with gr.Row(visible=lambda: not anonymous.value):
                username = gr.Textbox(label="Username")
                password = gr.Textbox(label="Password", type="password")
                
            gr.Markdown("⚠️ Warning: Credentials are transmitted to the server. Use anonymous login when possible.")
            
            # Game Input
            game_id = gr.Textbox(label="Game ID or Steam Store URL")
            game_id_info = gr.Markdown("Example: 570 (for Dota 2) or https://store.steampowered.com/app/570/Dota_2/")
            download_btn = gr.Button("Download Game")

        # Progress Display
        with gr.Group():
            gr.Markdown("## Download Status")
            progress_bar = gr.Slider(0, 100, label="Download Progress", interactive=False)
            
            with gr.Row():
                elapsed_time = gr.Textbox(label="Elapsed Time", interactive=False)
                remaining_time = gr.Textbox(label="Remaining Time", interactive=False)
                file_size = gr.Textbox(label="File Size", interactive=False)
                
            status = gr.Textbox(label="Status", interactive=False)
            links = gr.Textbox(label="Download Links", interactive=False)

        # Set initial status
        if check_steamcmd():
            steamcmd_status.value = "✅ SteamCMD is installed and ready to use."
            install_row.visible = False
        else:
            steamcmd_status.value = "❌ SteamCMD is not installed."
            install_row.visible = True

        # Event Handlers
        install_btn.click(
            install_steamcmd,
            outputs=[install_output]
        )
        
        anonymous.change(
            lambda x: (not x, not x),
            inputs=[anonymous],
            outputs=[username, password]
        )
        
        download_btn.click(
            start_download,
            inputs=[game_id, username, password, anonymous],
            outputs=[progress_bar, elapsed_time, remaining_time, file_size, status, links]
        )
    
    return app

# FastAPI setup
app_fastapi = FastAPI(title="SteamCMD Downloader")

# Initialize and mount Gradio app
app_gradio = create_interface()

# Mount static file directory for downloads
@app_fastapi.on_event("startup")
async def startup_event():
    ensure_directories()
    app_fastapi.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# Add file serving endpoint
@app_fastapi.get("/file/{file_path:path}")
async def serve_file(file_path: str):
    full_path = os.path.abspath(file_path)
    # Security check - ensure the path is within the allowed directories
    if os.path.commonpath([full_path, DOWNLOAD_DIR]) != DOWNLOAD_DIR:
        return {"error": "Access denied"}
    return FileResponse(full_path)

# Mount Gradio app
app_fastapi.mount("/", gr.routes.App.create_app(app_gradio))

# Deployment Setup
if __name__ == "__main__":
    # In development, use ngrok for public URL; on Railway, use assigned domain
    if not IS_RAILWAY:
        # Local testing with ngrok
        public_url = ngrok.connect(PORT).public_url
        logging.info(f"Local public URL: {public_url}")
        PUBLIC_URL = public_url
    else:
        logging.info(f"Railway public URL: {PUBLIC_URL}")

    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=PORT)