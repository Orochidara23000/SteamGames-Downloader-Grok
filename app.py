import gradio as gr
import os
import subprocess
import logging
import re
import time
import requests
from pyngrok import ngrok

# Configuration
DOWNLOAD_DIR = "./downloads"
STEAMCMD_PATH = "./steamcmd/steamcmd.sh" if os.name == 'posix' else "./steamcmd/steamcmd.exe"
LOG_FILE = "steamcmd.log"
PORT = int(os.environ.get("PORT", 7860))  # Railway assigns PORT
PUBLIC_URL = None  # Will be set dynamically

# Set up logging
logging.basicConfig(filename='steamcmd_downloader.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Step 1: Environment & System Check
def check_steamcmd():
    """Verify if SteamCMD is installed."""
    exists = os.path.exists(STEAMCMD_PATH)
    logging.info(f"SteamCMD check: {'Installed' if exists else 'Missing'}")
    return exists

def install_steamcmd():
    """Install SteamCMD if missing."""
    if os.name == 'posix':  # Linux (Railway default)
        os.makedirs("./steamcmd", exist_ok=True)
        subprocess.run("wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz -O steamcmd.tar.gz", shell=True)
        subprocess.run("tar -xvzf steamcmd.tar.gz -C ./steamcmd", shell=True)
        os.remove("steamcmd.tar.gz")
    elif os.name == 'nt':  # Windows (for local testing)
        # Note: Railway uses Linux, so this is optional
        subprocess.run("curl -o steamcmd.zip https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip", shell=True)
        subprocess.run("unzip steamcmd.zip -d ./steamcmd", shell=True)
        os.remove("steamcmd.zip")
    logging.info("SteamCMD installed successfully")
    return "SteamCMD installed. Please refresh the page."

def extract_game_id(input_str):
    """Extract game ID from URL or direct input."""
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
    """Parse SteamCMD output for progress or errors."""
    if "Login Failure" in output:
        return "Authentication failed"
    elif "Invalid App ID" in output:
        return "Invalid game ID"
    elif "ERROR" in output:
        return "Download error occurred"
    match = re.search(r'Progress: (\d+\.\d+)%', output) or re.search(r'(\d+\.\d+)%', output)
    if match:
        return float(match.group(1))
    return None

def start_download(game_id, username, password, anonymous):
    """Initiate download and yield progress updates."""
    game_id = extract_game_id(game_id)
    valid, message = validate_login(username, password, anonymous, game_id)
    if not valid:
        yield gr.update(value=0), "", "", "", message, ""
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
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
    files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
    links = [f"{PUBLIC_URL}/file/{os.path.join(DOWNLOAD_DIR, f)}" for f in files] if files else ["No files downloaded"]
    logging.info(f"Download completed for game {game_id}: {files}")
    yield gr.update(value=100), elapsed, "0 s", "N/A", "Download completed", "\n".join(links)

# Step 2: Gradio Interface Setup
def create_interface():
    with gr.Blocks(title="SteamCMD Downloader") as app:
        gr.Markdown("# SteamCMD Downloader")
        
        # System Check
        if not check_steamcmd():
            gr.Markdown("SteamCMD not found.")
            install_btn = gr.Button("Install SteamCMD")
            install_output = gr.Textbox(label="Installation Status")
            install_btn.click(install_steamcmd, outputs=install_output)
        else:
            gr.Markdown("SteamCMD is installed.")

        # Login Form
        with gr.Row():
            username = gr.Textbox(label="Username")
            password = gr.Textbox(label="Password", type="password")
            anonymous = gr.Checkbox(label="Login Anonymously (for free games)")
        
        # Game Input
        game_id = gr.Textbox(label="Game ID or URL")
        download_btn = gr.Button("Download")

        # Progress Display
        progress_bar = gr.Slider(0, 100, label="Download Progress", interactive=False)
        elapsed_time = gr.Textbox(label="Elapsed Time", interactive=False)
        remaining_time = gr.Textbox(label="Remaining Time", interactive=False)
        file_size = gr.Textbox(label="File Size", interactive=False)
        status = gr.Textbox(label="Status", interactive=False)
        links = gr.Textbox(label="Public Links", interactive=False)

        # Event Handler
        download_btn.click(
            start_download,
            inputs=[game_id, username, password, anonymous],
            outputs=[progress_bar, elapsed_time, remaining_time, file_size, status, links]
        )
    
    return app

# Deployment Setup for Railway
if __name__ == "__main__":
    # In development, use ngrok for public URL; on Railway, use assigned domain
    if os.environ.get("RAILWAY_ENVIRONMENT") is None:  # Local testing
        public_url = ngrok.connect(PORT).public_url
        logging.info(f"Local public URL: {public_url}")
        PUBLIC_URL = public_url
    else:  # Railway deployment
        PUBLIC_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", f"http://0.0.0.0:{PORT}")
        logging.info(f"Railway public URL: {PUBLIC_URL}")

    app = create_interface()
    app.launch(server_name="0.0.0.0", server_port=PORT)