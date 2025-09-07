"""
Main AI Voice Agent Engine

This module provides the main engine that coordinates between the SIP client,
audio processing, and AI providers to create a complete voice agent system.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional, Dict, Any
from pathlib import Path

from src.config import ConfigManager
from src.sip_client import SIPClient, SIPConfig, CallInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VoiceAgentEngine:
    """
    Main voice agent engine that coordinates all components.
    
    This engine manages the SIP client, audio processing, and AI provider
    integration to provide a complete voice agent solution.
    """
    
    def __init__(self, config_file: str = "config/engine.json"):
        """Initialize the voice agent engine."""
        self.config_manager = ConfigManager(config_file)
        self.config = self.config_manager.get_config()
        self.sip_client: Optional[SIPClient] = None
        self.running = False
        self.active_calls: Dict[str, CallInfo] = {}
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Voice Agent Engine initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())
    
    async def start(self) -> bool:
        """Start the voice agent engine."""
        try:
            logger.info("Starting Voice Agent Engine...")
            
            # Create SIP configuration from loaded config
            sip_config = SIPConfig(
                host=self.config.sip.host,
                port=self.config.sip.port,
                extension=self.config.sip.extension,
                password=self.config.sip.password,
                codecs=self.config.sip.codecs,
                transport=self.config.sip.transport,
                local_ip='0.0.0.0',
                local_port=15060,
                rtp_port_range=self.config.sip.rtp_port_range,
                registration_interval=3600,
                call_timeout=30
            )
            
            # Create and start SIP client
            self.sip_client = SIPClient(sip_config, self.config)
            
            # Add call handlers
            self.sip_client.add_registration_handler(self._on_registration_change)
            
            # Start SIP client
            if not await self.sip_client.start():
                logger.error("Failed to start SIP client")
                return False
            
            self.running = True
            logger.info("Voice Agent Engine started successfully")
            
            # Start main event loop
            await self._main_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Voice Agent Engine: {e}")
            return False
    
    async def stop(self):
        """Stop the voice agent engine."""
        logger.info("Stopping Voice Agent Engine...")
        self.running = False
        
        if self.sip_client:
            await self.sip_client.stop()
            self.sip_client = None
        
        logger.info("Voice Agent Engine stopped")
    
    async def _main_loop(self):
        """Main event loop for the voice agent."""
        logger.info("Voice Agent Engine main loop started")
        
        try:
            while self.running:
                # Update active calls
                if self.sip_client:
                    self.active_calls = self.sip_client.get_all_calls()
                
                # Process active calls
                await self._process_active_calls()
                
                # Sleep briefly to prevent excessive CPU usage
                await asyncio.sleep(0.01)  # Process more frequently
                
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            logger.info("Voice Agent Engine main loop ended")
    
    async def _process_active_calls(self):
        """Process all active calls."""
        if self.active_calls:
            logger.info(f"Processing {len(self.active_calls)} active calls: {list(self.active_calls.keys())}")
        
        for call_id, call_info in self.active_calls.items():
            try:
                # Only process calls that need attention
                if call_info.state == "ringing":
                    logger.info(f"Processing call {call_id} with state: {call_info.state}")
                    await self._handle_call(call_id, call_info)
                elif call_info.state == "connected" and not hasattr(call_info, 'conversation_started'):
                    logger.info(f"Processing call {call_id} with state: {call_info.state}")
                    await self._handle_call(call_id, call_info)
                elif call_info.state == "ended":
                    logger.info(f"Processing call {call_id} with state: {call_info.state}")
                    await self._handle_call(call_id, call_info)
            except Exception as e:
                logger.error(f"Error processing call {call_id}: {e}")
    
    async def _handle_call(self, call_id: str, call_info: CallInfo):
        """Handle a specific call."""
        if call_info.state == "ringing":
            logger.info(f"Call {call_id} is ringing from {call_info.from_user}")
            # Answer the call and start conversation loop
            await self._answer_call(call_id, call_info)
        elif call_info.state == "connected":
            # Only process if conversation loop hasn't been started yet
            if not hasattr(call_info, 'conversation_started') or not call_info.conversation_started:
                logger.info(f"Call {call_id} is connected with {call_info.from_user} - starting conversation")
                call_info.conversation_started = True
                # Process audio through conversation loop
                await self._process_call_audio(call_id, call_info)
            else:
                # Call is already being processed, skip
                pass
        elif call_info.state == "ended":
            logger.info(f"Call {call_id} has ended - removing from active calls")
            # Clean up conversation loop and remove from active calls
            await self._cleanup_call(call_id)
            # Remove from active calls to prevent infinite processing
            if call_id in self.active_calls:
                del self.active_calls[call_id]
    
    async def _answer_call(self, call_id: str, call_info: CallInfo):
        """Answer an incoming call and start conversation loop."""
        try:
            logger.info(f"Answering call {call_id} from {call_info.from_user}")
            
            # Import here to avoid circular imports
            from src.conversation_loop import ConversationLoop, ConversationConfig
            
            # Create conversation configuration
            conv_config = ConversationConfig(
                enable_vad=True,
                enable_noise_suppression=True,
                enable_echo_cancellation=True,
                openai_api_key=self.config.ai_provider.api_key,
                openai_model=self.config.ai_provider.model,
                voice_type=self.config.ai_provider.voice,
                system_instructions="You are a helpful AI assistant for Jugaar LLC. Answer calls professionally and helpfully.",
                max_context_length=10,
                silence_timeout=3.0,
                max_silence_duration=10.0
            )
            
            # Create conversation loop
            conversation_loop = ConversationLoop(conv_config)
            
            # Start the conversation loop
            if await conversation_loop.start():
                logger.info(f"Conversation loop started for call {call_id}")
                # Store the conversation loop for this call
                if not hasattr(self, 'conversation_loops'):
                    self.conversation_loops = {}
                self.conversation_loops[call_id] = conversation_loop
                
                # Update call state to connected
                call_info.state = "connected"
            else:
                logger.error(f"Failed to start conversation loop for call {call_id}")
                # Hang up the call
                await self.sip_client.hangup_call(call_id)
                
        except Exception as e:
            logger.error(f"Error answering call {call_id}: {e}")
            # Hang up the call
            await self.sip_client.hangup_call(call_id)
    
    async def _process_call_audio(self, call_id: str, call_info: CallInfo):
        """Process audio for an active call."""
        try:
            if hasattr(self, 'conversation_loops') and call_id in self.conversation_loops:
                conversation_loop = self.conversation_loops[call_id]
                # Process audio through the conversation loop
                # This would be called with audio data from RTP
                pass
        except Exception as e:
            logger.error(f"Error processing audio for call {call_id}: {e}")
    
    async def _cleanup_call(self, call_id: str):
        """Clean up resources for a ended call."""
        try:
            if hasattr(self, 'conversation_loops') and call_id in self.conversation_loops:
                conversation_loop = self.conversation_loops[call_id]
                await conversation_loop.stop()
                del self.conversation_loops[call_id]
                logger.info(f"Cleaned up conversation loop for call {call_id}")
        except Exception as e:
            logger.error(f"Error cleaning up call {call_id}: {e}")
    
    def _on_registration_change(self, registered: bool):
        """Handle SIP registration status changes."""
        if registered:
            logger.info("✅ Successfully registered with Asterisk")
        else:
            logger.warning("❌ Unregistered from Asterisk")
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the voice agent engine."""
        status = {
            "running": self.running,
            "registered": self.sip_client.is_registered() if self.sip_client else False,
            "active_calls": len(self.active_calls),
            "calls": {}
        }
        
        # Add call details
        for call_id, call_info in self.active_calls.items():
            status["calls"][call_id] = {
                "from_user": call_info.from_user,
                "to_user": call_info.to_user,
                "state": call_info.state,
                "codec": call_info.codec,
                "duration": int(asyncio.get_event_loop().time() - call_info.start_time)
            }
        
        return status


async def main():
    """Main entry point for the voice agent engine."""
    # Create engine instance
    engine = VoiceAgentEngine()
    
    try:
        # Start the engine
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Stop the engine
        await engine.stop()


if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())


