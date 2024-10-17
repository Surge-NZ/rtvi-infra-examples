# test.py

import asyncio
import sys
import os
import argparse
import json
import aiohttp
from datetime import datetime
# import pipecat.processors.frameworks.rtvi as rtvi
# print(dir(rtvi))
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

from twilio_media_streams import TwilioTransport, TwilioParams

from loguru import logger

from dotenv import load_dotenv
load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

def generate_function_prompt(function_definitions):
    function_descriptions = "\n".join([f"{fn['name']}: {fn['description']}" for fn in function_definitions])
    return f"You can also call these functions if needed:\n{function_descriptions}"

def load_company_info():
    try:
        with open('/app/bot/necta.txt', 'r') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error reading company info: {e}")
        return 'Necta helps you source candidates using AI.'

def compose_greeting(client_info):
    current_hour = datetime.now().hour
    if current_hour < 12:
        greeting_time = "Good morning"
    else:
        greeting_time = "Good afternoon"
    return f"{greeting_time} {client_info.get('name', 'there')}, this is Nelly from Necta. How are you today?"

def compose_goal():
    return (
        "Your main goal is to keep the conversation short, focused, and oriented towards booking a demo with Jack, our COO. "
        "Start by introducing yourself confidently and mentioning Necta briefly, establishing a friendly tone. "
        "Then, ask open-ended questions to understand the prospect's needs and challenges, and communicate the value that Necta provides. "
        "If the opportunity arises, propose booking a demo with Jack. "
        "Always ask open-ended questions to understand the prospect's needs and challenges, and communicate the value that Necta provides if it fits. "
        "Answer objection handling calmly and confidently, and steer the conversation towards booking a demo if the opportunity presents itself. "
    )

def compose_qualification_guidance():
    return (
        "After the introduction, ask open-ended questions to understand the prospect's needs and challenges. "
        "Quickly communicate the value that Necta provides, such as using AI to source and shortlist the right candidate for the right role at the right time, reducing time and effort for recruitment teams and avoiding CVs written by AI, focusing more on behaviour, skills and culture. "
        "Examples include: 'What are some of your current challenges in sourcing or evaluating candidates?' or 'Have you considered using AI to make your recruitment process more productive?' or 'What challenges do you currently face?'. "
        "Listen actively to their responses, acknowledge their concerns, and steer the conversation towards booking a demo if the opportunity presents itself."
    )

def compose_objection_handling_guidance():
    return (
        "If the prospect raises objections, address them calmly and confidently. "
        "Use facts, case studies, or success stories briefly to provide reassurance. "
        "For example: 'Many of our clients had similar concerns, but they found that using Necta reduces 17 hours on average per hire. The time to hire reduces by 26%. End-to-end cost is reduced by 30%. The right candidate means they stay longer.' "
        "Only dive into handling objections if they express a clear concern; otherwise, move forward in the conversation to booking a demo to see how our product can work with your current process."
    )

def compose_closing_guidance():
    return (
        "Wrap up the conversation by summarizing how Necta can benefit them, and propose booking a demo with Jack, our COO. "
        "Use a friendly but confident tone: 'I think a demo would be a great next step to show you exactly how we can help. Would you be open to setting one up with Jack?' "
        "If they agree, confirm their contact details and schedule a suitable time for the demo. "
        "If they decline, thank them for their time and ask if you can follow up with them in the future. "
    )

def compose_function_guidance(function_definitions):
    function_list = generate_function_prompt(function_definitions)
    return f"You can answer questions about Necta, but if a query is unrelated to Necta, check if you have a function that can handle it. {function_list}. Otherwise say you do not know and will get someone to call back."

def compose_other_guidance(company_info):
    return (
        f"Always aim to book a demo, and if asked, admit that you are an AI. "
        f"Keep answers concise and friendly, respond in short sentences, similar to how people chat in real conversations. "
        f"Avoid lengthy explanations or going off-topic. If unsure, simply say, 'Let me find out for you.' "
        f"Instead of saying 'Pause,' say 'One moment please'. Never be rude or anti-social, never correct the client. "
        f"Necta Information: {company_info}."
    )

def compose_system_prompt(client_info, function_definitions):
    company_info = load_company_info()
    greeting = compose_greeting(client_info)
    goal = compose_goal()
    qualification_guidance = compose_qualification_guidance()
    objection_handling_guidance = compose_objection_handling_guidance()
    closing_guidance = compose_closing_guidance()
    function_guidance = compose_function_guidance(function_definitions)
    other_guidance = compose_other_guidance(company_info)
    location = client_info.get('location', 'Auckland, New Zealand')

    return (
        f"You are Nelly from Necta, a friendly and confident Senior Sales Development Agent designed for phone conversations, located in {location}. Ensure you respond in no more than two sentences at a time. "
        f"You are speaking with the following prospect: {json.dumps(client_info)}. "
        f"Although not explicit, the phone conversation should follow the sequence of greeting, qualification, objection handling, and close with the goal of: {goal}.  "
        f"Start with: '{greeting}'. Then Qualification: {qualification_guidance}. Then Objection Handling: {objection_handling_guidance}. Finally Close: {closing_guidance} "
        f"{function_guidance} {other_guidance} "
        f"Remember to keep your responses short, conversational, and focused on booking a demo. "
        f"If the prospect asks for specific information that you cannot provide directly, check if you have a function that can help. "
        f"You can call these functions if needed: {generate_function_prompt(function_definitions)}. If there is no function to the question, you can say 'I am not sure, let me get someone to call you back'."
    )

async def fetch_weather_from_api(llm, args):
    location = args.get('location', 'Unknown Location')
    url = f"https://wttr.in/{location}?format=%C+%t"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    weather_info = {
                        "conditions": data.split()[0],
                        "temperature": data.split()[1],
                        "location": location
                    }
                    return weather_info
                else:
                    logger.error(f"Failed to fetch weather data: {response.status}")
                    return {"error": "Unable to fetch weather information at this time"}
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return {"error": "An error occurred while fetching weather information"}

async def main(room_url, token, call_sid, client_info):
    if room_url and token:
        # Use DailyTransport
        transport = DailyTransport(
            room_url,
            token,
            "Realtime AI",
            DailyParams(
                audio_out_enabled=True,
                video_source=False,
                transcription_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer()
            ))
    elif call_sid:
        # Use TwilioTransport
        transport = TwilioTransport(
            call_sid,
            TwilioParams(
                transcription_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer()
            ))
    else:
        logger.error("Neither room URL nor call SID provided.")
        return

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
                    'content': compose_system_prompt(client_info, function_definitions)
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
        llm_api_key=os.getenv("OPENAI_API_KEY"),
        tts_api_key=os.getenv("CARTESIA_API_KEY"))

    # Register a callback to send audio back to Twilio
    @rtai.event_handler("on_audio_output")
    async def on_audio_output(frame):
        if isinstance(transport, TwilioTransport):
            await transport.send_audio_to_twilio(frame.audio_data)

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
    parser.add_argument("-s", type=str, help="Call SID")
    parser.add_argument("-c", type=str, help="Client Info JSON")
    config = parser.parse_args()

    if config.c:
        client_info = json.loads(config.c)
    else:
        client_info = {}

    asyncio.run(main(config.u, config.t, config.s, client_info))