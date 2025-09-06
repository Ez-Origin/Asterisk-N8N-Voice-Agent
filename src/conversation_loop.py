"""
Conversation Loop Implementation

This module provides the main conversation loop that orchestrates the
STT → LLM → TTS cycle for voice agent interactions.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum

from src.call_session import CallSession, CallState
from src.audio_processing.pipeline import AudioProcessingPipeline, AudioProcessingConfig
from src.audio_processing.codec_handler import CodecHandler
from src.providers.openai import (
    RealtimeClient, STTHandler, LLMHandler, TTSHandler,
    RealtimeConfig, STTConfig, LLMConfig, TTSConfig
)

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """Conversation loop state enumeration."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class ConversationConfig:
    """Configuration for conversation loop."""
    
    # Audio processing
    enable_vad: bool = True
    enable_noise_suppression: bool = True
    enable_echo_cancellation: bool = True
    vad_threshold: float = 0.5
    silence_timeout: float = 3.0
    max_silence_duration: float = 10.0
    
    # OpenAI Realtime API
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-realtime-preview-2024-10-01"
    voice_type: str = "alloy"
    language: str = "en-US"
    
    # Conversation settings
    system_prompt: str = "You are a helpful AI voice assistant. Keep responses concise and natural for voice conversation."
    max_conversation_turns: int = 50
    response_timeout: float = 30.0
    
    # Callbacks
    on_user_speech: Optional[Callable[[str], None]] = None
    on_ai_response: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[str, Exception], None]] = None
    on_state_change: Optional[Callable[[ConversationState], None]] = None


class ConversationLoop:
    """
    Main conversation loop that orchestrates STT → LLM → TTS cycles.
    
    This class manages the real-time conversation flow, handling audio input,
    processing it through AI providers, and generating audio responses.
    """
    
    def __init__(self, session: CallSession, config: ConversationConfig):
        """Initialize conversation loop."""
        self.session = session
        self.config = config
        self.state = ConversationState.IDLE
        
        # Audio processing components
        self.audio_pipeline: Optional[AudioProcessingPipeline] = None
        self.codec_handler: Optional[CodecHandler] = None
        
        # AI provider components
        self.realtime_client: Optional[RealtimeClient] = None
        self.stt_handler: Optional[STTHandler] = None
        self.llm_handler: Optional[LLMHandler] = None
        self.tts_handler: Optional[TTSHandler] = None
        
        # Conversation state
        self.is_running = False
        self.current_audio_buffer = b""
        self.silence_start_time: Optional[float] = None
        self.last_activity_time = time.time()
        
        # Statistics
        self.stats = {
            'conversation_turns': 0,
            'total_processing_time': 0.0,
            'average_response_time': 0.0,
            'errors': 0,
            'vad_detections': 0,
            'stt_requests': 0,
            'llm_requests': 0,
            'tts_requests': 0
        }
        
        logger.info(f"Conversation loop initialized for call {session.call_id}")
    
    async def initialize(self) -> bool:
        """Initialize all components for the conversation loop."""
        try:
            logger.info(f"Initializing conversation loop for call {self.session.call_id}")
            
            # Initialize audio processing pipeline
            await self._initialize_audio_processing()
            
            # Initialize AI providers
            await self._initialize_ai_providers()
            
            # Setup callbacks
            self._setup_callbacks()
            
            logger.info(f"Conversation loop initialized successfully for call {self.session.call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize conversation loop: {e}")
            await self._handle_error("Initialization failed", e)
            return False
    
    async def _initialize_audio_processing(self):
        """Initialize audio processing components."""
        try:
            # Initialize codec handler
            self.codec_handler = CodecHandler()
            
            # Initialize audio processing pipeline
            pipeline_config = AudioProcessingConfig(
                enable_vad=self.config.enable_vad,
                enable_noise_suppression=self.config.enable_noise_suppression,
                enable_echo_cancellation=self.config.enable_echo_cancellation,
                sample_rate=self.session.sample_rate
            )
            
            self.audio_pipeline = AudioProcessingPipeline(pipeline_config)
            
            logger.info("Audio processing pipeline initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize audio processing: {e}")
            raise
    
    async def _initialize_ai_providers(self):
        """Initialize AI provider components."""
        try:
            if not self.config.openai_api_key:
                raise ValueError("OpenAI API key not provided")
            
            # Initialize Realtime client
            realtime_config = RealtimeConfig(
                api_key=self.config.openai_api_key,
                model=self.config.openai_model,
                voice=self.config.voice_type,
                language=self.config.language
            )
            
            self.realtime_client = RealtimeClient(realtime_config)
            
            # Initialize handlers
            stt_config = STTConfig(
                sample_rate=self.session.sample_rate,
                channels=self.session.channels,
                enable_logging=True
            )
            
            llm_config = LLMConfig(
                system_prompt=self.config.system_prompt,
                max_context_length=self.config.max_conversation_turns,
                enable_logging=True
            )
            
            tts_config = TTSConfig(
                voice=self.config.voice_type,
                sample_rate=self.session.sample_rate,
                channels=self.session.channels,
                enable_logging=True
            )
            
            self.stt_handler = STTHandler(stt_config, self.realtime_client)
            self.llm_handler = LLMHandler(llm_config, self.realtime_client)
            self.tts_handler = TTSHandler(tts_config, self.realtime_client)
            
            # Connect to OpenAI Realtime API
            if not await self.realtime_client.connect():
                raise ConnectionError("Failed to connect to OpenAI Realtime API")
            
            logger.info("AI providers initialized and connected")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI providers: {e}")
            raise
    
    def _setup_callbacks(self):
        """Setup callbacks for AI handlers."""
        # STT callbacks
        if self.stt_handler:
            self.stt_handler.config.on_transcript = self._on_transcript
            self.stt_handler.config.on_speech_start = self._on_speech_start
            self.stt_handler.config.on_speech_end = self._on_speech_end
        
        # LLM callbacks
        if self.llm_handler:
            self.llm_handler.config.on_response_start = self._on_response_start
            self.llm_handler.config.on_response_chunk = self._on_response_chunk
            self.llm_handler.config.on_response_complete = self._on_response_complete
        
        # TTS callbacks
        if self.tts_handler:
            self.tts_handler.config.on_speech_start = self._on_tts_speech_start
            self.tts_handler.config.on_audio_chunk = self._on_audio_chunk
            self.tts_handler.config.on_speech_end = self._on_tts_speech_end
    
    async def start(self) -> bool:
        """Start the conversation loop."""
        try:
            if self.is_running:
                logger.warning("Conversation loop is already running")
                return False
            
            logger.info(f"Starting conversation loop for call {self.session.call_id}")
            
            # Update session state
            self.session.update_state(CallState.CONNECTED)
            self._update_state(ConversationState.LISTENING)
            
            self.is_running = True
            self.last_activity_time = time.time()
            
            # Start the main conversation loop
            await self._conversation_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start conversation loop: {e}")
            await self._handle_error("Failed to start conversation", e)
            return False
    
    async def stop(self):
        """Stop the conversation loop."""
        logger.info(f"Stopping conversation loop for call {self.session.call_id}")
        
        self.is_running = False
        self._update_state(ConversationState.IDLE)
        
        # Stop all handlers
        if self.stt_handler:
            await self.stt_handler.stop_listening()
        
        if self.llm_handler:
            await self.llm_handler.cancel_response()
        
        if self.tts_handler:
            await self.tts_handler.stop_synthesis()
        
        # Disconnect from OpenAI
        if self.realtime_client:
            await self.realtime_client.disconnect()
        
        # Update session state
        self.session.update_state(CallState.ENDED)
        
        logger.info(f"Conversation loop stopped for call {self.session.call_id}")
    
    async def _conversation_loop(self):
        """Main conversation loop."""
        logger.info(f"Conversation loop started for call {self.session.call_id}")
        
        try:
            while self.is_running and self.session.is_active():
                # Check for timeout
                if time.time() - self.last_activity_time > self.config.max_silence_duration:
                    logger.info("Conversation timeout reached")
                    break
                
                # Process audio input
                await self._process_audio_input()
                
                # Small delay to prevent excessive CPU usage
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Error in conversation loop: {e}")
            await self._handle_error("Conversation loop error", e)
        finally:
            logger.info(f"Conversation loop ended for call {self.session.call_id}")
    
    async def _process_audio_input(self):
        """Process incoming audio input."""
        try:
            # This would typically receive audio from the SIP client
            # For now, we'll simulate the process
            
            # In a real implementation, this would:
            # 1. Receive audio chunks from SIP client
            # 2. Process through audio pipeline (VAD, noise suppression, etc.)
            # 3. Send to STT handler when speech is detected
            # 4. Handle the STT → LLM → TTS cycle
            
            pass
            
        except Exception as e:
            logger.error(f"Error processing audio input: {e}")
            await self._handle_error("Audio processing error", e)
    
    async def process_audio_chunk(self, audio_data: bytes) -> bool:
        """Process a chunk of audio data."""
        try:
            if not self.is_running or not self.session.is_active():
                return False
            
            # Update activity time
            self.last_activity_time = time.time()
            
            # Process through audio pipeline
            if self.audio_pipeline:
                processed_audio = await self.audio_pipeline.process_audio(audio_data)
                
                # Check for voice activity
                if self.audio_pipeline.is_voice_detected():
                    self.stats['vad_detections'] += 1
                    
                    # Buffer audio for STT
                    self.current_audio_buffer += processed_audio
                    
                    # Start STT if not already listening
                    if self.state == ConversationState.LISTENING:
                        await self._start_listening()
                
                # Check for silence timeout
                if self.audio_pipeline.is_silence_detected():
                    if self.silence_start_time is None:
                        self.silence_start_time = time.time()
                    elif time.time() - self.silence_start_time > self.config.silence_timeout:
                        await self._process_speech()
                else:
                    self.silence_start_time = None
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            await self._handle_error("Audio chunk processing error", e)
            return False
    
    async def _start_listening(self):
        """Start listening for speech."""
        try:
            if not self.stt_handler:
                return
            
            self._update_state(ConversationState.LISTENING)
            
            # Start STT listening
            success = await self.stt_handler.start_listening()
            if not success:
                logger.error("Failed to start STT listening")
                return
            
            logger.info("Started listening for speech")
            
        except Exception as e:
            logger.error(f"Error starting listening: {e}")
            await self._handle_error("Failed to start listening", e)
    
    async def _process_speech(self):
        """Process detected speech."""
        try:
            if not self.stt_handler or not self.llm_handler:
                return
            
            self._update_state(ConversationState.PROCESSING)
            
            # Send buffered audio to STT
            if self.current_audio_buffer:
                await self.stt_handler.process_audio(self.current_audio_buffer)
                self.current_audio_buffer = b""
            
            # Wait for STT to complete
            await asyncio.sleep(0.5)  # Give STT time to process
            
            # Get transcript
            transcript = self.stt_handler.get_current_transcript()
            if transcript and transcript.text.strip():
                logger.info(f"User said: {transcript.text}")
                
                # Add to conversation history
                self.session.add_to_conversation("user", transcript.text)
                
                # Call user speech callback
                if self.config.on_user_speech:
                    self.config.on_user_speech(transcript.text)
                
                # Generate AI response
                await self._generate_response(transcript.text)
            
            # Reset for next speech
            self.silence_start_time = None
            self._update_state(ConversationState.LISTENING)
            
        except Exception as e:
            logger.error(f"Error processing speech: {e}")
            await self._handle_error("Speech processing error", e)
    
    async def _generate_response(self, user_input: str):
        """Generate AI response to user input."""
        try:
            if not self.llm_handler or not self.tts_handler:
                return
            
            start_time = time.time()
            
            # Send message to LLM
            await self.llm_handler.send_message(user_input)
            
            # Create response
            success = await self.llm_handler.create_response(["text", "audio"])
            if not success:
                logger.error("Failed to create LLM response")
                return
            
            # Wait for response to complete
            while self.llm_handler.is_responding():
                await asyncio.sleep(0.1)
            
            # Get response text
            response = self.llm_handler.get_current_response()
            if response and response.text.strip():
                logger.info(f"AI response: {response.text}")
                
                # Add to conversation history
                self.session.add_to_conversation("assistant", response.text)
                
                # Call AI response callback
                if self.config.on_ai_response:
                    self.config.on_ai_response(response.text)
                
                # Synthesize speech
                await self._synthesize_response(response.text)
            
            # Update statistics
            processing_time = time.time() - start_time
            self.stats['conversation_turns'] += 1
            self.stats['total_processing_time'] += processing_time
            self.stats['average_response_time'] = (
                self.stats['total_processing_time'] / self.stats['conversation_turns']
            )
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            await self._handle_error("Response generation error", e)
    
    async def _synthesize_response(self, text: str):
        """Synthesize AI response to speech."""
        try:
            if not self.tts_handler:
                return
            
            self._update_state(ConversationState.SPEAKING)
            
            # Synthesize text to speech
            success = await self.tts_handler.synthesize_text(text)
            if not success:
                logger.error("Failed to synthesize speech")
                return
            
            # Wait for synthesis to complete
            while self.tts_handler.is_synthesizing():
                await asyncio.sleep(0.1)
            
            logger.info("Speech synthesis completed")
            
        except Exception as e:
            logger.error(f"Error synthesizing response: {e}")
            await self._handle_error("Speech synthesis error", e)
    
    # Callback methods
    def _on_transcript(self, transcript: str):
        """Handle STT transcript."""
        logger.debug(f"STT transcript: {transcript}")
        self.stats['stt_requests'] += 1
    
    def _on_speech_start(self):
        """Handle speech start detection."""
        logger.debug("Speech started")
        self._update_state(ConversationState.LISTENING)
    
    def _on_speech_end(self):
        """Handle speech end detection."""
        logger.debug("Speech ended")
    
    def _on_response_start(self):
        """Handle LLM response start."""
        logger.debug("LLM response started")
        self.stats['llm_requests'] += 1
    
    def _on_response_chunk(self, chunk: str):
        """Handle LLM response chunk."""
        logger.debug(f"LLM chunk: {chunk}")
    
    def _on_response_complete(self, response: str):
        """Handle LLM response completion."""
        logger.debug(f"LLM response complete: {response}")
    
    def _on_tts_speech_start(self):
        """Handle TTS speech start."""
        logger.debug("TTS speech started")
        self.stats['tts_requests'] += 1
    
    def _on_audio_chunk(self, audio_data: bytes):
        """Handle TTS audio chunk."""
        logger.debug(f"TTS audio chunk: {len(audio_data)} bytes")
        # In a real implementation, this would send audio to the SIP client
    
    def _on_tts_speech_end(self):
        """Handle TTS speech end."""
        logger.debug("TTS speech ended")
        self._update_state(ConversationState.LISTENING)
    
    def _update_state(self, new_state: ConversationState):
        """Update conversation state."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            
            if self.config.on_state_change:
                try:
                    self.config.on_state_change(new_state)
                except Exception as e:
                    logger.error(f"Error in state change callback: {e}")
            
            logger.debug(f"Conversation state: {old_state.value} -> {new_state.value}")
    
    async def _handle_error(self, message: str, error: Exception):
        """Handle errors in the conversation loop."""
        logger.error(f"{message}: {error}")
        
        self.stats['errors'] += 1
        self._update_state(ConversationState.ERROR)
        
        if self.config.on_error:
            try:
                self.config.on_error(message, error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get conversation loop statistics."""
        stats = self.stats.copy()
        stats['state'] = self.state.value
        stats['is_running'] = self.is_running
        stats['session_stats'] = self.session.get_stats()
        return stats
