import os
import sys
import subprocess
from pathlib import Path

# Base working directory
REPO_ROOT = Path(__file__).resolve().parent


def refresh_environment():
    """Ensure ~/.local site-packages and bin paths are fully registered in sys.path and PATH."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    # Check all possible Python user site-package paths (.local/lib/python*/site-packages)
    candidates = [
        Path.home() / ".local" / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages",
        Path.home() / ".local" / "lib" / "python3.13" / "site-packages",
        Path.home() / ".local" / "lib" / "python3.12" / "site-packages",
        Path.home() / ".local" / "lib" / "python3.11" / "site-packages",
        REPO_ROOT / ".local" / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages",
    ]
    for c in (Path.home() / ".local").glob("lib/python*/site-packages"):
        candidates.append(c)

    for p in candidates:
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    # Add ~/.local/bin to PATH
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"


refresh_environment()

HF_REPO_URL = "https://huggingface.co/SakIMG/UFNS"
HF_REPO_ID = "SakIMG/UFNS"
HF_DEFAULT_TOKEN = "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"


def ensure_backend_loaded():
    """Ensure the entire 2.84GB UFNS repository (all code, models, rasters, and datasets) is fully cloned into root."""
    refresh_environment()
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or HF_DEFAULT_TOKEN
    os.environ["HF_TOKEN"] = token
    os.environ["HUGGINGFACE_TOKEN"] = token

    app_target = REPO_ROOT / "apps" / "api" / "app.py"
    sample_lfs_file = REPO_ROOT / "data" / "processed" / "mumbai" / "cartodem_merged_4326.tif"

    # Check if app code AND real binary files (not 130-byte LFS text pointers) exist
    if app_target.exists() and (sample_lfs_file.exists() and sample_lfs_file.stat().st_size > 1024):
        print(f"[UFNS Bootloader] Full repository (2.84GB) verified in root.")
        return

    print("================================================================")
    print(f" [UFNS Bootloader] Downloading Full 2.84GB Repository from: {HF_REPO_URL}")
    print(f" [UFNS Bootloader] Target Root Directory: {REPO_ROOT}")
    print("================================================================")

    # 1. Ensure huggingface_hub is installed and imported
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[UFNS Bootloader] Installing huggingface_hub...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        refresh_environment()
        from huggingface_hub import snapshot_download

    # 2. Download all 2.84GB datasets and backend files (skipping unused node_modules to avoid HF 429 file-count rate limits)
    try:
        print(f"[UFNS Bootloader] Downloading full 2.84GB backend & datasets to {REPO_ROOT}...")
        snapshot_download(
            repo_id=HF_REPO_ID,
            local_dir=str(REPO_ROOT),
            token=token,
            max_workers=8,
            ignore_patterns=[
                "**/node_modules/**",
                "node_modules/**",
                ".venv/**",
                "**/.git/**",
            ],
        )
        print("[UFNS Bootloader] Full 2.84GB repository download complete.")
    except Exception as e:
        print(f"[UFNS Bootloader] snapshot_download error: {e}")

    refresh_environment()


if __name__ == '__main__':
    # 1. Bootload from Hugging Face if running in fresh HiddenCloud environment
    ensure_backend_loaded()
    refresh_environment()

    # 2. Import FastAPI application
    try:
        import uvicorn
        from apps.api.app import app
    except ImportError as e:
        print(f"[UFNS Bootloader] Missing dependencies ({e}). Installing core requirements...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")])
        refresh_environment()
        import uvicorn
        from apps.api.app import app

    # 3. Detect port from HiddenCloud (SERVER_PORT or PORT) or fallback to 8000
    port_str = os.getenv('PORT') or os.getenv('SERVER_PORT') or '8000'
    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    host = os.getenv('HOST', '0.0.0.0')
    print('================================================================')
    print(f' UFNS High-Performance Production Backend Active (HiddenCloud)')
    print(f' Upstream Repository: {HF_REPO_URL}')
    print(f' Listening on: http://{host}:{port}')
    print('================================================================')

    uvicorn.run(
        'apps.api.app:app',
        host=host,
        port=port,
        workers=1,
        log_level='info',
        proxy_headers=True,
        forwarded_allow_ips='*'
    )
