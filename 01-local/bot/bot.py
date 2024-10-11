import asyncio
import sys
import os
import argparse
import json

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

def load_company_info():
    try:
        with open('/app/bot/necta.txt', 'r') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error reading company info: {e}")
        return 'Necta helps you source candidates using AI.'

def compose_system_prompt(client_info):
    company_info = load_company_info()
    return f"""You are Nelly from Necta, a friendly sales representative designed for phone conversations. You are speaking with the following prospect: {json.dumps(client_info)}. Your main goal is to keep the conversation short, focused, and oriented towards booking a demo with Jack, our COO. Greet the prospect and ask if they've considered using AI to source and shortlist amazing candidates. You can answer questions about Necta, but for anything outside Necta, simply state that you don't know. Always aim to book a demo, always keep asking questions to keep the conversation going and if asked admit you are an AI not a human. Respond only with spoken words, keeping answers concise. Instead of saying Pause, say 'One moment please'. Necta Information: {company_info}. Start with: 'Hello {client_info.get('name', 'there')}, how are you today?'"""

async def fetch_weather_from_api(llm, args):
    location = args.get('location', 'Unknown Location')
    # Implement actual API call here, for now we'll use a static response
    weather_info = {
        "conditions": "sunny",
        "temperature": "75°F",
        "location": location
    }
    return weather_info

async def main(room_url, token, client_info):
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

    function_definitions = [
        {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get the weather for"
                    }
                },
                "required": ["location"]
            }
        }
    ]

    # Prepare bot_config
    bot_config = {
        'llm': {
            'model': 'llama-3.1-70b-versatile',
            'messages': [
                {
                    'role': 'system',
                    'content': compose_system_prompt(client_info)
                }
            ],
            'functions': function_definitions
        },
        'tts': {
            'voice': '79a125e8-cd45-4c13-8a67-188112f4dd22'
        }
    }

    # Prepare function callbacks
    function_callbacks = {
        'get_current_weather': fetch_weather_from_api
    }

    # Initialize RTVISetup with function callbacks
    rtvi_setup = RTVISetup(
        config=RTVIConfig(**bot_config),
        function_callbacks=function_callbacks
    )

    rtai = RTVIProcessor(
        transport=transport,
        setup=rtvi_setup,
        llm_api_key="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",
        tts_api_key="c6e8b60d-7d5a-40e1-8f40-cc427ee8e747")

    # Remove the code that attempts to access rtai.llm.register_function
    # The functions are now registered via RTVISetup

    runner = PipelineRunner()

    pipeline = Pipeline([transport.input(), rtai])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            send_initial_empty_metrics=False,
        ))

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        transport.capture_participant_transcription(participant["id"])
        logger.info("First participant joined")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        await task.queue_frame(EndFrame())
        logger.info("Participant left. Exiting.")

    @transport.event_handler("on_call_state_updated")
    async def on_call_state_updated(transport, state):
        logger.info("Call state %s " % state)
        if state == "left":
            await task.queue_frame(EndFrame())

    await runner.run(task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sales Bot")
    parser.add_argument("-u", type=str, help="Room URL")
    parser.add_argument("-t", type=str, help="Token")
    parser.add_argument("-c", type=str, help="Client Info JSON")
    config = parser.parse_args()

    if config.u and config.t and config.c:
        client_info = json.loads(config.c)
        asyncio.run(main(config.u, config.t, client_info))
    else:
        logger.error("Room URL, Token, and Client Info are required")
