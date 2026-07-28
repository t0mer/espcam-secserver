import os
import time
import hmac
import shutil
import tempfile
import uvicorn
import requests
import ipaddress
from loguru import logger
from os.path import basename
from urllib.parse import urlparse
from whatsapp_api_client_python import API
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, File, Form, UploadFile,HTTPException


GREEN_API_INSTANCE_ID = os.getenv("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")
TARGET = os.getenv("TARGET")
MESSAGE = os.getenv("MESSAGE")
# Shared secret required to trigger the capture endpoint. Required: when unset
# the endpoint refuses every request (fail closed).
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
# Timeout (seconds) for outbound requests to the camera.
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))


def _redact_secrets(record):
    """Scrub credentials from log messages. The GreenAPI SDK embeds the token
    in request URLs, so an exception message can otherwise leak it to the logs."""
    message = record["message"]
    for secret in (GREEN_API_TOKEN, GREEN_API_INSTANCE_ID, AUTH_TOKEN):
        if secret:
            message = message.replace(secret, "***")
    record["message"] = message


logger = logger.patch(_redact_secrets)
greenAPI = API.GreenAPI(GREEN_API_INSTANCE_ID,GREEN_API_TOKEN)


def validate_config():
    """Fail fast if required configuration is missing."""
    required = {
        "GREEN_API_INSTANCE_ID": GREEN_API_INSTANCE_ID,
        "GREEN_API_TOKEN": GREEN_API_TOKEN,
        "TARGET": TARGET,
        "AUTH_TOKEN": AUTH_TOKEN,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))

class Server:
    def __init__(self):
       
        self.app = FastAPI(title="esp32 cam security server", description="Capture and send images taken with esp32 cam", version='1.0.0',  contact={"name": "Tomer Klein", "email": "tomer.klein@gmail.com", "url": "https://github.com/t0mer/espcam-secserver"})
        # Only allow the origins explicitly configured via CORS_ORIGINS (comma
        # separated). Default is no cross-origin access. Never combine a wildcard
        # origin with credentials.
        self.origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

        @self.app.get("/")
        def home(request: Request):
            """
            Get Images
            """
            # Authenticate before doing any work. Kept outside the try/except
            # below so the 401 is not swallowed and turned into "OK".
            if not AUTH_TOKEN:
                logger.error("AUTH_TOKEN not configured - refusing request")
                raise HTTPException(status_code=503, detail="Server not configured: AUTH_TOKEN is required")
            provided = request.headers.get("X-Auth-Token") or request.query_params.get("token") or ""
            if not hmac.compare_digest(provided, AUTH_TOKEN):
                raise HTTPException(status_code=401, detail="Unauthorized")

            # Validate the client address before making any outbound request.
            # Kept outside the try/except so the error is not turned into "OK".
            client_host = request.client.host if request.client else None
            if not client_host:
                raise HTTPException(status_code=400, detail="Unable to determine client address")
            try:
                client_ip = ipaddress.ip_address(client_host)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid client address")
            # Only fetch from a camera on a private/loopback network. This stops
            # the server from being coerced into requesting arbitrary external
            # hosts (SSRF).
            if not client_ip.is_private:
                raise HTTPException(status_code=403, detail="Camera must be on a private network")
            host_for_url = f"[{client_host}]" if client_ip.version == 6 else client_host
            url = f"http://{host_for_url}/capture"

            # Unique per-request working directory avoids filename collisions
            # between concurrent triggers and is always cleaned up below.
            tmpdir = tempfile.mkdtemp(prefix="espcam_")
            try:
                saved = []
                for i in range(3):
                    # Fetch the image. The timeout prevents a hung camera from
                    # blocking the worker indefinitely.
                    try:
                        response = requests.get(url, timeout=REQUEST_TIMEOUT)
                    except requests.RequestException as e:
                        logger.error(f"Failed to fetch image {i+1}: {e}")
                        time.sleep(1)
                        continue
                    if response.status_code == 200:
                        # Save the image to a local file
                        path = os.path.join(tmpdir, f"image{i+1}.jpg")
                        with open(path, 'wb') as file:
                            file.write(response.content)
                        saved.append(path)
                        logger.info(f"Image saved as {path}")
                    else:
                        logger.error(f"Failed to retrieve image {i+1}: HTTP {response.status_code}")

                    # Wait for 1 second before the next request
                    time.sleep(1)

                # Send only the images that were actually captured.
                for path in saved:
                    try:
                        upload_file_response = greenAPI.sending.uploadFile(path)
                        if upload_file_response.code != 200:
                            logger.error("Failed to upload file: " + path)
                            continue
                        url_file = upload_file_response.data["urlFile"]
                        file_name = basename(urlparse(url_file).path)
                        send_file_by_url_response = greenAPI.sending.sendFileByUrl(TARGET, url_file, file_name, caption=MESSAGE)
                        logger.info(send_file_by_url_response)
                    except Exception as e:
                        logger.error(f"Failed to send {path}: {e}")
            except Exception as e:
                logger.error(str(e))
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            return "OK"

    
  
    def start(self):
        validate_config()
        uvicorn.run(self.app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
        
        
if __name__=="__main__":
    server = Server()
    server.start()