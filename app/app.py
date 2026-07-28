import os
import time
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
# Shared secret required to trigger the capture endpoint. If unset the endpoint
# stays open (bootstrap mode) but a warning is logged on every request.
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
greenAPI = API.GreenAPI(GREEN_API_INSTANCE_ID,GREEN_API_TOKEN)

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
            if AUTH_TOKEN:
                provided = request.headers.get("X-Auth-Token") or request.query_params.get("token")
                if provided != AUTH_TOKEN:
                    raise HTTPException(status_code=401, detail="Unauthorized")
            else:
                logger.warning("AUTH_TOKEN not set - capture endpoint is UNAUTHENTICATED")

            try:
                client_host = request.client.host
                ipv4_address = str(client_host)
                ip = ipaddress.IPv4Address(ipv4_address)
                last_octet = ip.packed[-1]
                # logger.info(client_host)
                url = f'http://{str(client_host)}/capture'
                file_names = [f'{last_octet}_image1.jpg', f'{last_octet}_image2.jpg', f'{last_octet}_image3.jpg']

                for i in range(3):
                    # Make the request to fetch the image
                    response = requests.get(url)
                    # Check if the request was successful
                    if response.status_code == 200:
                        # Save the image to a local file
                        with open(file_names[i], 'wb') as file:
                            file.write(response.content)
                        print(f"Image saved as {file_names[i]}")
                    else:
                        print(f"Failed to retrieve image {i+1}")
                    
                    # Wait for 1 second before the next request
                    time.sleep(1)
                
                #Send the images
                for i in range(3):
                    upload_file_response = greenAPI.sending.uploadFile(file_names[i]) 
                    if upload_file_response.code != 200:
                        logger.error("Failed to upload file: " + file_names[i])
                    else:
                        url_file = upload_file_response.data["urlFile"]
                        logger.debug(url_file)
                        url = urlparse(url_file)
                        file_name = basename(url.path)
                        logger.warning(file_name)
                        send_file_by_url_response = greenAPI.sending.sendFileByUrl(TARGET, url_file, file_name, caption=MESSAGE)
                        logger.info(send_file_by_url_response)
                        os.remove(file_names[i])
            except Exception as e:
                logger.error(str(e)) 
            return "OK"

    
  
    def start(self):
        uvicorn.run(self.app, host="0.0.0.0", port=80)
        
        
if __name__=="__main__":
    server = Server()
    server.start()