# -*- coding: utf-8 -*-
import os
import time
from typing import Optional

from dotenv import load_dotenv

from .asterisk_connection import AsteriskConnection
from .llm import LLM
from .sound import Sound
from .stt import STT
from .tts import TTS

# Load environment variables from .env file
load_dotenv()


class Engine:
    def __init__(self, config: dict):
        self.config = config
        self.asterisk_conn = None
        self.sound = None
        self.tts = None
        self.llm = None
        self.stt = None
        self.active_channel = None
        self.active_call_id = None
        self.last_transcript = ""
        self.session_data = {}

        self.connect_to_asterisk()
        self.init_tts()
        self.init_llm()
        self.init_stt()
        self.init_sound()

    def init_sound(self):
        self.sound = Sound(self.asterisk_conn)

    def init_tts(self):
        self.tts = TTS(self.config)

    def init_stt(self):
        self.stt = STT(self.config)

    def init_llm(self):
        self.llm = LLM(self.config)

    def connect_to_asterisk(self):
        self.asterisk_conn = AsteriskConnection(self.config)

    def get_initial_greeting(self):
        return self.config.get("llm", {}).get("initial_greeting", "Hello, how can I help you today?")

    def handle_new_channel(self, event, call_id):
        channel = event.get("channel")
        self.active_channel = channel
        self.active_call_id = call_id
        print(f"New channel: {channel['name']}")
        initial_greeting = self.get_initial_greeting()
        self.say(initial_greeting)

    def handle_dtmf(self, event):
        digit = event.get("digit")
        channel_name = event.get("channel", {}).get("name")
        print(f"DTMF received: {digit} on channel {channel_name}")
        # Add your DTMF handling logic here
        self.session_data[channel_name] = self.session_data.get(channel_name, "") + digit
        self.process_session(channel_name)

    def handle_speech_result(self, event):
        transcript = event.get("result", "")
        channel_name = event.get("channel", {}).get("name")
        self.last_transcript = transcript
        print(f"Speech result: {transcript} on channel {channel_name}")
        # Add your speech result handling logic here
        self.session_data[channel_name] = transcript
        self.process_session(channel_name)

    def say(self, text: str):
        if not self.active_channel:
            print("No active channel to say the text.")
            return

        try:
            self.tts.say(text, self.active_channel)
        except Exception as e:
            print(f"Error saying text: {e}")

    def process_session(self, channel_name):
        transcript = self.session_data.get(channel_name, "")
        print(f"Processing session for {channel_name} with transcript: {transcript}")
        # Add your session processing logic here
        if not transcript:
            self.say("Please say something.")
            return
        response = self.llm.query(transcript)
        self.say(response)
