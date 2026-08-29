import os
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uvicorn
from apps.api.app import app

if __name__ == '__main__':
    # Detect port from HiddenCloud (SERVER_PORT or PORT) or fallback to 8000
    port_str = os.getenv('PORT') or os.getenv('SERVER_PORT') or '8000'
    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    host = os.getenv('HOST', '0.0.0.0')
    print('==================================================')
    print(f' Starting UFNS High-Performance Production Backend')
    print(f' Listening on: http://{host}:{port}')
    print('==================================================')
    
    uvicorn.run(
        'apps.api.app:app',
        host=host,
        port=port,
        workers=1,
        log_level='info',
        proxy_headers=True,
        forwarded_allow_ips='*'
    )
