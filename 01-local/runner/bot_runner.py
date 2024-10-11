import os
import argparse
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pipecat.transports.services.helpers.daily_rest import DailyRESTHelper, DailyRoomObject, DailyRoomProperties, DailyRoomParams

from dotenv import load_dotenv
import traceback
from loguru import logger
import json

# Load environment variables
load_dotenv(override=True)

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

# ------------ FastAPI Routes ------------ #

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
        # Create a Daily REST helper instance
        daily_rest_helper = DailyRESTHelper(DAILY_API_KEY, DAILY_API_URL)
        logger.debug("Initialized DailyRESTHelper successfully")
    except Exception as e:
        logger.error(f"Error initializing DailyRESTHelper: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to initialize DailyRESTHelper")

    try:
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
    except Exception as e:
        logger.error(f"Failed to create room or get token: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create room or get token")

    try:
        # Decide which bot script to run based on bot_type
        if bot_type == 'salesBot':
            bot_file_path = Path("/app/bot/bot.py")
        elif bot_type == 'customerCareBot':
            bot_file_path = Path("/app/bot/customer_care_bot.py")
        # Add more elif statements for other bot types
        else:
            # Default bot
            bot_file_path = Path("/app/bot/default_bot.py")

        # Ensure that `bot_file_path` is a file, not a directory
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
    except Exception as e:
        logger.error(f"Failed to start subprocess: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to start subprocess")

    try:
        # Get a token for the user to join with
        user_token = daily_rest_helper.get_token(room.url, MAX_SESSION_TIME)
        return JSONResponse({
            "room_name": room.name,
            "room_url": room.url,
            "token": user_token,
        })
    except Exception as e:
        logger.error(f"Failed to get user token: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to get user token")

# ------------ Main ------------ #

if __name__ == "__main__":
    import uvicorn

    default_host = "0.0.0.0"
    default_port = int(os.getenv("PORT", "7860"))

    parser = argparse.ArgumentParser(
        description="RTVI Bot Runner")
    parser.add_argument("--host", type=str,
                        default=default_host, help="Host address")
    parser.add_argument("--port", type=int,
                        default=default_port, help="Port number")
    parser.add_argument("--reload", action="store_true",
                        help="Reload code on change")

    config = parser.parse_args()

    uvicorn.run(
        "bot_runner:app",
        host=config.host,
        port=config.port,
        reload=config.reload
    )
