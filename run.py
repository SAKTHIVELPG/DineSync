import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure current directory is in sys.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    port = int(os.environ.get("PORT", 8000))
    is_render = os.environ.get("RENDER") is not None
    is_prod = os.environ.get("ENV", "").lower() == "production" or is_render
    reload = not is_prod

    print("==========================================================")
    print("[*] DINESYNC: Smart Restaurant IoT & AI Platform Starting")
    print(f"[*] Server URL: http://localhost:{port}")
    print(f"[*] WebSocket : ws://localhost:{port}/ws")
    print(f"[*] API Docs  : http://localhost:{port}/docs")
    print(f"[*] Mode      : {'Production (Render)' if is_prod else 'Development'}")
    print("==========================================================")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=reload)
