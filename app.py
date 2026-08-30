import os
import sys
import subprocess
from pathlib import Path

# Base working directory
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HF_REPO_URL = "https://huggingface.co/SakIMG/UFNS"
HF_REPO_ID = "SakIMG/UFNS"


def ensure_backend_loaded():
    """Ensure the complete UFNS backend and hydrodynamic datasets are present from Hugging Face."""
    app_target = REPO_ROOT / "apps" / "api" / "app.py"
    if app_target.exists():
        print(f"[UFNS Bootloader] Local backend verified at {app_target}.")
        return

    print("================================================================")
    print(f" [UFNS Bootloader] Fetching backend from Hugging Face: {HF_REPO_URL}")
    print("================================================================")

    # 1. Try Hugging Face Hub snapshot download (supports LFS & caching)
    try:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("[UFNS Bootloader] Installing huggingface_hub...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub", "hf_xet"])
            from huggingface_hub import snapshot_download

        print(f"[UFNS Bootloader] Downloading snapshot for {HF_REPO_ID}...")
        snapshot_download(
            repo_id=HF_REPO_ID,
            local_dir=str(REPO_ROOT),
            local_dir_use_symlinks=False,
            resume_download=True,
            token=os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"),
        )
    except Exception as e:
        print(f"[UFNS Bootloader] snapshot_download notice: {e}")

    # 2. Fallback: Git clone if files still missing
    if not app_target.exists():
        print(f"[UFNS Bootloader] Falling back to git clone: {HF_REPO_URL}...")
        try:
            import shutil
            temp_clone = REPO_ROOT / "_temp_hf_clone"
            if temp_clone.exists():
                shutil.rmtree(temp_clone, ignore_errors=True)
            subprocess.run(["git", "clone", f"{HF_REPO_URL}.git", str(temp_clone)], check=True)
            for item in temp_clone.iterdir():
                if item.name == ".git":
                    continue
                dest = REPO_ROOT / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            shutil.rmtree(temp_clone, ignore_errors=True)
        except Exception as err:
            print(f"[UFNS Bootloader] Git clone fallback failed: {err}")

    # Ensure REPO_ROOT is in sys.path after download
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


if __name__ == '__main__':
    # 1. Bootload from Hugging Face if running in fresh HiddenCloud environment
    ensure_backend_loaded()

    # 2. Import FastAPI application
    try:
        import uvicorn
        from apps.api.app import app
    except ImportError as e:
        print(f"[UFNS Bootloader] Missing dependencies ({e}). Installing core requirements...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")])
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
