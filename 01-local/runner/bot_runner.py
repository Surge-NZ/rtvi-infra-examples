# bot_runner.py

import os
import argparse
import subprocess
from pathlib import Path
import base64
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse





from pipecat.transports.services.helpers.daily_rest import DailyRESTHelper, DailyRoomObject, DailyRoomProperties, DailyRoomParams
import boto3  # For S3 interaction
import requests  # For downloading the recording
from dotenv import load_dotenv
import traceback
from loguru import logger
import json
from fastapi.responses import Response

# Import Twilio Client
from twilio.rest import Client

# Load environment variables
load_dotenv(override=True)

# S3 Client initialization
s3_client = boto3.client('s3')

class TwilioMediaTransport:
    """
    Custom transport to handle incoming and outgoing media between Twilio WebSocket and RTVI.
    """
    def __init__(self):
        self.websocket = None

    def set_websocket(self, websocket):
        """
        Set the Twilio WebSocket for media streaming.
        """
        self.websocket = websocket

    async def send_audio(self, audio_data):
        """
        Send processed audio back to the Twilio WebSocket.
        """
        if self.websocket:
            audio_payload = base64.b64encode(audio_data).decode('utf-8')
            media_msg = {
                "event": "media",
                "media": {
                    "payload": audio_payload
                }
            }
            await self.websocket.send(json.dumps(media_msg))

# Twilio Client initialization
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")  # Add your Twilio Account SID
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")    # Add your Twilio Auth Token
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio phone number

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ------------ FastAPI Config ------------ #
MAX_SESSION_TIME = 15 * 60  # 15 minutes
DAILY_API_URL = "https://api.daily.co/v1"
DAILY_API_KEY = os.getenv("DAILY_API_KEY")  # Ensure this is set in your environment variables

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ Helper Methods ------------ #

def check_host_whitelist(request: Request):
    host_whitelist = ""
    request_host_url = request.headers.get("host")

    if not host_whitelist:
        return True

    allowed_hosts = host_whitelist.split(",")

    if len(allowed_hosts) < 1:
        return True

    if any(domain in allowed_hosts for domain in [request_host_url, f"www.{request_host_url}"]):
        return True

    return False

def get_s3_bucket_name(bot_type):
    """
    Return the appropriate S3 bucket name based on the bot type.
    """
    if bot_type == 'salesBot':
        return "nectasalescalls"  # S3 bucket for sales bot
    elif bot_type == 'customerCareBot':
        return "nectacustomercarecalls"  # S3 bucket for customer care bot
    else:
        return "nectadefaultcalls"  # Default bucket for other bots

def upload_to_s3(file_url, file_name, bucket_name):
    try:
        # Fetch the recording file
        response = requests.get(file_url, stream=True)
        if response.status_code == 200:
            # Upload the file to the appropriate S3 bucket
            s3_client.upload_fileobj(response.raw, bucket_name, file_name)
            print(f"Successfully uploaded {file_name} to S3 bucket: {bucket_name}")
        else:
            print(f"Failed to fetch the recording file. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")

def delete_recording(room_id, recording_id):
    try:
        delete_url = f"{DAILY_API_URL}/rooms/{room_id}/recordings/{recording_id}"
        response = requests.delete(delete_url, headers={'Authorization': f'Bearer {DAILY_API_KEY}'})

        if response.status_code == 200:
            print(f"Successfully deleted recording {recording_id} from Daily.co")
        else:
            print(f"Failed to delete recording. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error deleting recording: {e}")

def handle_recording(room_id, bot_type):
    try:
        recordings_url = f"{DAILY_API_URL}/rooms/{room_id}/recordings"
        response = requests.get(recordings_url, headers={'Authorization': f'Bearer {DAILY_API_KEY}'})

        if response.status_code == 200:
            recordings = response.json().get('data', [])
            bucket_name = get_s3_bucket_name(bot_type)
            for recording in recordings:
                file_url = recording['url']
                recording_id = recording['id']
                file_name = f"recordings/{room_id}_{recording_id}.mp4"

                # Upload the recording to the appropriate S3 bucket
                upload_to_s3(file_url, file_name, bucket_name)

                # After successful upload, delete the recording from Daily.co
                delete_recording(room_id, recording_id)
        else:
            print(f"Failed to fetch recordings for room {room_id}. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error handling recording: {e}")

def initiate_twilio_call(client_info):
    try:
        to_phone_number = client_info.get('phone')
        if not to_phone_number:
            raise ValueError("Client phone number is missing.")

        # Use your actual ngrok URL
        twiml_url = "https://8224-114-23-148-116.ngrok-free.app/twiml"

        call = client.calls.create(
            url=twiml_url,
            to=to_phone_number,
            from_=TWILIO_PHONE_NUMBER
        )
        logger.debug(f"Initiated Twilio call: {call.sid}")
        return call.sid
    except Exception as e:
        logger.error(f"Failed to initiate Twilio call: {e}")
        raise
# ------------ FastAPI Routes ------------ #

@app.route("/twiml", methods=["GET", "POST"])
async def twiml_response():
    # Use your actual ngrok URL
    ngrok_ws_url = "wss://8224-114-23-148-116.ngrok-free.app/twilio-media-stream"
    response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="{ngrok_ws_url}" bidirectional="true"/> 
        </Connect>
    </Response>"""
    return Response(content=response, media_type="application/xml")

# Initialize the twilio_transport globally
twilio_transport = TwilioMediaTransport()

@app.websocket("/twilio-media-stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    try:
        while True:
            message = await websocket.receive_text()
            logger.info(f"Received message: {message}")
            data = json.loads(message)
            if data['event'] == 'media':
                await twilio_transport.send_audio(data['media']['payload'])
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        await websocket.close()


@app.middleware("http")
async def allowed_hosts_middleware(request: Request, call_next):
    # Middleware to optionally check for hosts in a whitelist
    if not check_host_whitelist(request):
        raise HTTPException(status_code=403, detail="Host access denied")
    response = await call_next(request)
    return response

@app.post("/")
async def index(request: Request) -> JSONResponse:
    try:
        # Log the raw request body
        logger.debug("Received request body:")
        body = await request.body()
        logger.debug(body)

        # Parse the request JSON
        data = await request.json()
        if "test" in data:
            return JSONResponse({"test": True})

        if "config" not in data:
            raise Exception("Missing configuration object for bot")

        logger.debug("Configuration found in request")
    except Exception as e:
        logger.error(f"Error parsing request: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Missing or malformed configuration object")

    try:
        # Parse the botType and clientInfo from the request
        bot_type = data["config"].get("botType", "defaultBot")
        client_info = data["config"].get("clientInfo", {})
        logger.debug(f"Bot type: {bot_type}")
        logger.debug(f"Client info: {client_info}")
    except Exception as e:
        logger.error(f"Failed to parse bot type or client info: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to parse bot type or client info")

    try:
        # Decide which bot script to run based on bot_type
        if bot_type == 'salesBot':
            bot_file_path = Path("/app/bot/test.py")
            # For salesBot, we need to initiate a Twilio call
            call_sid = initiate_twilio_call(client_info)

            # Pass necessary info to bot.py
            client_info_json = json.dumps(client_info)

            subprocess.Popen(
                ["python3", str(bot_file_path), "-s", call_sid, "-c", client_info_json],
                shell=False,
                bufsize=1,
                cwd=bot_file_path.parent
            )
            logger.debug(f"Started bot subprocess for bot type '{bot_type}' successfully")

            return JSONResponse({
                "message": "Twilio call initiated.",
                "call_sid": call_sid
            })

        else:
            # For other bot types, use Daily.co rooms
            # Create a Daily REST helper instance
            bot_file_path = Path("/app/bot/bot.py")
            daily_rest_helper = DailyRESTHelper(DAILY_API_KEY, DAILY_API_URL)
            logger.debug("Initialized DailyRESTHelper successfully")

            # Create a new room or use a debug room
            debug_room = None
            if debug_room:
                room: DailyRoomObject = daily_rest_helper.get_room_from_url(debug_room)
                logger.debug(f"Using debug room: {debug_room}")
            else:
                params = DailyRoomParams(properties=DailyRoomProperties())
                room: DailyRoomObject = daily_rest_helper.create_room(params=params)
                logger.debug(f"Created new room: {room.url}")

            # Get a token for the room
            token = daily_rest_helper.get_token(room.url, MAX_SESSION_TIME)
            logger.debug(f"Generated token for room: {room.url}")

            # Ensure that bot_file_path is a file, not a directory
            if not bot_file_path.is_file():
                logger.error(f"Bot file does not exist: {bot_file_path}")
                raise FileNotFoundError(f"Bot file does not exist at path: {bot_file_path}")

            # Pass client_info to the bot script as a JSON string
            client_info_json = json.dumps(client_info)

            subprocess.Popen(
                ["python3", str(bot_file_path), "-u", room.url, "-t", token, "-c", client_info_json],
                shell=False,
                bufsize=1,
                cwd=bot_file_path.parent
            )
            logger.debug(f"Started bot subprocess for bot type '{bot_type}' successfully")

            # Handle recording after the bot finishes, using bot_type to determine the S3 bucket
            handle_recording(room.id, bot_type)

            # Get a token for the user to join with
            user_token = daily_rest_helper.get_token(room.url, MAX_SESSION_TIME)
            return JSONResponse({
                "room_name": room.name,
                "room_url": room.url,
                "token": user_token,
            })
    except Exception as e:
        logger.error(f"Failed to start subprocess or handle bot: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to start subprocess or handle bot")

# ------------ Main ------------ #

import uvicorn
import argparse

if __name__ == "__main__":
    # Parse command-line arguments if needed
    parser = argparse.ArgumentParser(
        description="RTVI Bot Runner for both HTTP and WebSocket"
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8765, help="Port number")  # Single port for both HTTP and WebSocket
    parser.add_argument("--reload", action="store_true", help="Reload on change")
    
    config = parser.parse_args()

    # Run a single instance of Uvicorn for both HTTP and WebSocket
    uvicorn.run(
        "bot_runner:app",  # Assuming app is your FastAPI instance
        host=config.host,
        port=config.port,  # Use the same port for both HTTP and WebSocket
        reload=config.reload
    )