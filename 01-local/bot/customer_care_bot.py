import asyncio
import sys
import os
import argparse
import json

# Import necessary modules from pipecat and other dependencies
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frameworks.rtvi import (
    RTVIConfig,
    RTVIProcessor,
    RTVISetup)
from pipecat.frames.frames import EndFrame
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.vad.silero import SileroVADAnalyzer

from loguru import logger

from dotenv import load_dotenv
load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# Define any specific functions or configurations for the customer care bot

def compose_system_prompt():
    # Define the system prompt specific to the customer care bot
    return "You are a friendly customer care assistant..."

async def main(room_url, token):
    transport = DailyTransport(
        room_url,
        token,
        "Realtime AI",
        DailyParams(
            audio_out_enabled=True,
            transcription_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer()
        ))

    # Prepare bot_config specific to customer care bot
    bot_config = {
        'llm': {
            'model': 'llama-3.1-70b-versatile',
            'messages': [
                {
                    'role': 'system',
                    'content': compose_system_prompt()
                }
            ],
            # Add functions if needed
        },
        'tts': {
            'voice': 'YOUR_TTS_VOICE_ID'
        }
    }

    rtai = RTVIProcessor(
        transport=transport,
        setup=RTVISetup(config=RTVIConfig(**bot_config)),
        llm_api_key=os.getenv("LLM_API_KEY"),
        tts_api_key=os.getenv("TTS_API_KEY"))

    # Register functions if any

    runner = PipelineRunner()

    pipeline = Pipeline([transport.input(), rtai])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            send_initial_empty_metrics=False,
        ))

    # Event handlers as needed

    await runner.run(task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Customer Care Bot")
    parser.add_argument("-u", type=str, help="Room URL")
    parser.add_argument("-t", type=str, help="Token")
    config = parser.parse_args()

    if config.u and config.t:
        asyncio.run(main(config.u, config.t))
    else:
        logger.error("Room URL and Token are required")
