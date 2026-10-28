import uvicorn
from backend.app.main import create_app
from backend.app.core.config import server_port, server_host
import os

if __name__ == "__main__":
    uvicorn.run(create_app(), host=server_host(), port=server_port(), access_log=False,
                forwarded_allow_ips=os.environ.get("CIRCULAR_TRUSTED_PROXIES", "127.0.0.1"))
