"""
A new, simplified Asterisk ARI WebSocket Client.
Focuses on robust connection and logging to debug startup issues.
"""

import asyncio
import json
import os
import time
import uuid
import audioop
import wave
from typing import Dict, Any, Optional, Callable, List
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import websockets
import structlog
from urllib.parse import quote

from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import WebSocketClientProtocol

from .config import AsteriskConfig
from .logging_config import get_logger

logger = get_logger(__name__)

class ARIClient:
    """A client for interacting with the Asterisk REST Interface (ARI)."""

    def __init__(self, username: str, password: str, base_url: str, app_name: str):
        self.username = username
        self.password = password
        self.http_url = base_url
        ws_host = base_url.replace("http://", "").split('/')[0]
        safe_username = quote(username)
        safe_password = quote(password)
        self.ws_url = f"ws://{ws_host}/ari/events?api_key={safe_username}:{safe_password}&app={app_name}&subscribeAll=true&subscribe=ChannelAudioFrame"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.active_playbacks: Dict[str, str] = {}
        self.audio_frame_handler: Optional[Callable] = None

    def on_event(self, event_type: str, handler: Callable):
        """Alias for add_event_handler for backward compatibility."""
        self.add_event_handler(event_type, handler)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def connect(self):
        """Connect to the ARI WebSocket and establish an HTTP session."""
        logger.info("Connecting to ARI...")
        try:
            # First, test HTTP connection to ensure ARI is available
            self.http_session = aiohttp.ClientSession(auth=aiohttp.BasicAuth(self.username, self.password))
            async with self.http_session.get(f"{self.http_url}/asterisk/info") as response:
                if response.status != 200:
                    raise ConnectionError(f"Failed to connect to ARI HTTP endpoint. Status: {response.status}")
                logger.info("Successfully connected to ARI HTTP endpoint.")

            # Then, connect to the WebSocket
            self.websocket = await websockets.connect(self.ws_url)
            self.running = True
            logger.info("Successfully connected to ARI WebSocket.")
        except Exception as e:
            logger.error("Failed to connect to ARI, will retry...", error=str(e), exc_info=True)
            if self.http_session and not self.http_session.closed:
                await self.http_session.close()
            raise

    async def start_listening(self):
        """Start listening for events from the ARI WebSocket."""
        if not self.running or not self.websocket:
            logger.error("Cannot start listening, client is not connected.")
            return

        logger.info("Starting ARI event listener.")
        try:
            # Subscribe to playback finished events
            self.add_event_handler("PlaybackFinished", self._on_playback_finished)

            async for message in self.websocket:
                try:
                    event_data = json.loads(message)
                    event_type = event_data.get("type")
                    
                    # Handle audio frames from AudioSocket connections
                    if event_type == "ChannelAudioFrame":
                        channel = event_data.get('channel', {})
                        channel_id = channel.get('id')
                        logger.debug("ChannelAudioFrame received", channel_id=channel_id)
                        asyncio.create_task(self._on_audio_frame(channel, event_data))
                    
                    # Handle other events
                    if event_type and event_type in self.event_handlers:
                        for handler in self.event_handlers[event_type]:
                            # Call the handler with just the event data
                            asyncio.create_task(handler(event_data))
                except json.JSONDecodeError:
                    logger.warning("Failed to decode ARI event JSON", message=message)
        except ConnectionClosed:
            logger.warning("ARI WebSocket connection closed.")
            self.running = False
        except Exception as e:
            logger.error("An error occurred in the ARI listener", exc_info=True)
            self.running = False

    async def disconnect(self):
        """Disconnect from the ARI WebSocket and close the HTTP session."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            self.http_session = None
        logger.info("Disconnected from ARI.")

    def add_event_handler(self, event_type: str, handler: Callable):
        """Register a handler for a specific ARI event type."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.debug("Added event handler", event_type=event_type, handler=handler.__name__)

    async def handle_audio_frame(self, event_data: dict, audio_handler: Callable):
        """Handle audio frames from snoop channels."""
        channel = event_data.get('channel', {})
        channel_id = channel.get('id')
        audio_data = event_data.get('audio', {})
        
        if channel_id and audio_data:
            # Extract the raw audio data
            audio_payload = audio_data.get('data')
            if audio_payload:
                # Convert from base64 if needed, or handle as raw bytes
                import base64
                try:
                    raw_audio = base64.b64decode(audio_payload)
                    await audio_handler(channel_id, raw_audio)
                except Exception as e:
                    logger.error("Error processing audio frame", error=str(e))

    async def handle_dtmf_received(self, event_data: dict, dtmf_handler: Callable):
        """Handle DTMF events from snoop channels."""
        channel = event_data.get('channel', {})
        channel_id = channel.get('id')
        digit = event_data.get('digit')
        
        if channel_id and digit:
            await dtmf_handler(channel_id, digit)

    async def send_command(self, method: str, resource: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command to the ARI HTTP endpoint."""
        url = f"{self.http_url}/{resource}"
        
        # Handle channelVars specially - they need to be in the JSON body, not query params
        if params and "channelVars" in params:
            channel_vars = params.pop("channelVars")
            if data is None:
                data = {}
            data["channelVars"] = channel_vars
        
        try:
            async with self.http_session.request(method, url, json=data, params=params) as response:
                if response.status >= 400:
                    reason = await response.text()
                    logger.error("ARI command failed", method=method, url=url, status=response.status, reason=reason)
                    # To prevent crashing on expected 404s for hangup, we return a dict
                    return {"status": response.status, "reason": reason}
                if response.status == 204: # No Content
                    return {"status": response.status}
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error("ARI HTTP request failed", exc_info=True)
            return {"status": 500, "reason": str(e)}

    async def answer_channel(self, channel_id: str):
        """Answer a channel."""
        logger.info("Answering channel", channel_id=channel_id)
        await self.send_command("POST", f"channels/{channel_id}/answer")

    async def hangup_channel(self, channel_id: str):
        """Hang up a channel."""
        logger.info("Hanging up channel", channel_id=channel_id)
        # We add a check here. If the command fails with a 404, we log it
        # as a debug message instead of an error, as this can happen in race
        # conditions during cleanup and is not necessarily a critical failure.
        response = await self.send_command("DELETE", f"channels/{channel_id}")
        if response and response.get("status") == 404:
            logger.debug("Channel hangup failed (404), likely already hung up.", channel_id=channel_id)

    async def play_media(self, channel_id: str, media_uri: str) -> Optional[Dict[str, Any]]:
        """Play media on a channel."""
        logger.info("Playing media on channel", channel_id=channel_id, media_uri=media_uri)
        return await self.send_command("POST", f"channels/{channel_id}/play", data={"media": media_uri})


    async def create_bridge(self, bridge_type: str = "mixing") -> Optional[str]:
        """Create a new bridge for channel mixing."""
        try:
            response = await self.send_command(
                "POST",
                "bridges",
                data={
                    "type": bridge_type,
                    "name": f"bridge_{uuid.uuid4().hex[:8]}"
                }
            )
            
            if response.get("id"):
                logger.info("Bridge created", bridge_id=response["id"], bridge_type=bridge_type)
                return response["id"]
            else:
                logger.error("Failed to create bridge", response=response)
                return None
                
        except Exception as e:
            logger.error("Error creating bridge", error=str(e))
            return None

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> bool:
        """Add a channel to a bridge."""
        try:
            response = await self.send_command(
                "POST",
                f"bridges/{bridge_id}/addChannel",
                data={"channel": channel_id}
            )

            # send_command returns {"status": 204} for No Content on success
            status = response.get("status") if isinstance(response, dict) else None
            if status is not None:
                if 200 <= int(status) < 300:
                    logger.info("Channel added to bridge", bridge_id=bridge_id, channel_id=channel_id, status=status)
                    return True
                else:
                    logger.error("Failed to add channel to bridge", bridge_id=bridge_id, channel_id=channel_id, status=status, response=response)
                    return False

            # If no explicit status was returned, assume success and log response for traceability
            logger.info("Channel add-to-bridge response without status; assuming success", bridge_id=bridge_id, channel_id=channel_id, response=response)
            return True

        except Exception as e:
            logger.error("Error adding channel to bridge", 
                        bridge_id=bridge_id, 
                        channel_id=channel_id, 
                        error=str(e))
            return False


    async def play_audio_response(self, channel_id: str, audio_data: bytes):
        """Saves TTS audio to shared media directory and commands Asterisk to play it."""
        logger.info("Starting audio playback process", channel_id=channel_id, audio_size=len(audio_data))
        
        # CRITICAL: Validate channel before attempting playback
        logger.debug("Validating channel before playback", channel_id=channel_id)
        if not await self.validate_channel_for_playback(channel_id):
            logger.warning("Channel validation failed - skipping audio playback", channel_id=channel_id)
            return
        
        unique_filename = f"response-{uuid.uuid4()}.ulaw"
        # Use the shared RAM space for high-performance audio file storage
        # Put files in the ai-generated subdirectory to match the symlink
        container_path = f"/mnt/asterisk_media/ai-generated/{unique_filename}"
        # Use the symlinked path that Asterisk can access
        # Remove .ulaw extension since Asterisk adds it automatically
        asterisk_media_uri = f"sound:ai-generated/{unique_filename[:-5]}"

        try:
            # TTS now generates ulaw data directly, no conversion needed
            logger.debug("Writing ulaw audio file to ai-generated subdirectory", path=container_path)
            
            logger.debug("Writing ulaw audio file", path=container_path, size=len(audio_data))
            with open(container_path, "wb") as f:
                f.write(audio_data)
            
            # Audio generated as ulaw format at 8000 Hz for Asterisk compatibility
            logger.debug("Ulaw audio file written (generated as ulaw at 8000 Hz)", path=container_path)
            
            # Change ownership to asterisk user so Asterisk can read the file
            # Use hardcoded UID/GID since pwd.getpwnam doesn't work in container
            try:
                asterisk_uid = 995  # asterisk user UID
                asterisk_gid = 995  # asterisk group GID
                os.chown(container_path, asterisk_uid, asterisk_gid)
                logger.debug("Changed file ownership to asterisk user", path=container_path, uid=asterisk_uid, gid=asterisk_gid)
            except Exception as e:
                logger.warning("Failed to change file ownership", path=container_path, error=str(e))
            
            logger.debug("Verifying file creation", path=container_path, exists=os.path.exists(container_path))
            if os.path.exists(container_path):
                file_size = os.path.getsize(container_path)
                logger.debug("File created successfully", path=container_path, size=file_size)
                
                # File is ready for playback
                logger.debug("Attempting to play media", channel_id=channel_id, media_uri=asterisk_media_uri)

            playback = await self.play_media(channel_id, asterisk_media_uri)
            if playback and 'id' in playback:
                self.active_playbacks[playback['id']] = container_path
                logger.info("Audio playback initiated successfully", 
                          channel_id=channel_id, 
                          filename=unique_filename, 
                          playback_id=playback['id'])
            else:
                logger.error("Failed to initiate audio playback", 
                           channel_id=channel_id, 
                           playback_response=playback)
        except Exception as e:
            logger.error("Failed to play audio file", channel_id=channel_id, error=str(e), exc_info=True)

    async def _on_playback_finished(self, event):
        """Event handler for cleaning up audio files after a short delay."""
        playback_id = event.get("playback", {}).get("id")
        file_path = self.active_playbacks.pop(playback_id, None)
        if file_path:
            # Add a delay to ensure Asterisk has finished with the file
            import asyncio
            await asyncio.sleep(2.0)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug("Successfully deleted audio file", file_path=file_path)
                except OSError:
                    logger.error("Error deleting audio file", file_path=file_path, exc_info=True)
        
        # Call the engine's PlaybackFinished handler if it exists
        if hasattr(self, 'engine') and hasattr(self.engine, '_on_playback_finished'):
            await self.engine._on_playback_finished(event)

    async def cleanup_call_files(self, channel_id: str):
        """Clean up any remaining audio files for a specific call."""
        import os
        import glob
        
        # Clean up any files that might be associated with this call
        # Look for files in the ai-generated directory that might be orphaned
        ai_generated_dir = "/mnt/asterisk_media/ai-generated"
        if os.path.exists(ai_generated_dir):
            # Find any files that might be associated with this call
            # This is a safety net for files that weren't cleaned up by playback_finished
            pattern = os.path.join(ai_generated_dir, "response-*.ulaw")
            files = glob.glob(pattern)
            
            for file_path in files:
                try:
                    # Check if file is older than 30 seconds (safety check)
                    if os.path.getmtime(file_path) < (time.time() - 30):
                        os.remove(file_path)
                        logger.debug("Cleaned up orphaned audio file", file_path=file_path)
                except OSError as e:
                    logger.debug("Could not clean up file", file_path=file_path, error=str(e))

    async def _on_audio_frame(self, channel, event):
        """Handles incoming raw audio frames from the snoop channel."""
        try:
            logger.debug("Processing audio frame", channel_id=channel.get('id'), event_keys=list(event.keys()))
            # Get the audio frame data
            frame_data = event.get("frame", {})
            audio_payload = frame_data.get("data", "")
            
            # Log frame format information
            frame_format = frame_data.get("format", "unknown")
            frame_samples = frame_data.get("samples", 0)
            logger.debug("Audio frame details", format=frame_format, samples=frame_samples, payload_length=len(audio_payload))
            
            if audio_payload:
                # Decode base64 audio data
                import base64
                audio_data = base64.b64decode(audio_payload)
                logger.debug("Decoded audio data", bytes=len(audio_data), format=frame_format)
                
                # Forward to the audio frame handler
                if self.audio_frame_handler:
                    await self.audio_frame_handler(audio_data)
                    logger.debug("Forwarded audio frame to handler")
                else:
                    logger.debug(f"Received audio frame but no handler set: {len(audio_data)} bytes")
            else:
                logger.debug("Received audio frame with no data")
        except Exception as e:
            logger.error("Error processing audio frame", error=str(e), exc_info=True)

    def set_audio_frame_handler(self, handler: Callable):
        """Set the handler for incoming audio frames."""
        self.audio_frame_handler = handler


    async def play_audio_file(self, channel_id: str, file_path: str) -> bool:
        """Play an audio file to the specified channel with enhanced error handling."""
        try:
            import time
            start_time = time.time()
            
            # Enhanced file verification with detailed logging
            for attempt in range(15):  # Try up to 15 times (1.5 seconds total)
                if os.path.exists(file_path):
                    if os.access(file_path, os.R_OK):
                        file_size = os.path.getsize(file_path)
                        if file_size > 0:
                            logger.debug(f"File verified: {file_path} ({file_size} bytes) - attempt {attempt + 1}")
                            break
                        else:
                            logger.warning(f"File exists but is empty: {file_path} - attempt {attempt + 1}")
                    else:
                        logger.warning(f"File exists but not readable: {file_path} (permissions: {oct(os.stat(file_path).st_mode)[-3:]}) - attempt {attempt + 1}")
                else:
                    logger.warning(f"File not found: {file_path} - attempt {attempt + 1}")
                
                time.sleep(0.1)  # 100ms delay
            
            # Final verification
            if not os.path.exists(file_path):
                logger.error(f"Audio file not found after 15 attempts: {file_path}")
                return False
            
            if not os.access(file_path, os.R_OK):
                logger.error(f"Audio file not readable: {file_path} (permissions: {oct(os.stat(file_path).st_mode)[-3:]})")
                return False

            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.error(f"Audio file is empty: {file_path}")
                return False

            # Set channel variable for debugging
            await self.send_command(
                "POST",
                f"channels/{channel_id}/variable",
                data={"variable": "AUDIO_FILE_PATH", "value": file_path}
            )
            
            # Use ARI to play the file
            result = await self.send_command(
                "POST",
                f"channels/{channel_id}/play",
                data={"media": f"sound:{file_path}"}
            )
            
            elapsed_time = (time.time() - start_time) * 1000  # milliseconds
            if result:
                logger.info(f"Playing audio file {file_path} ({file_size} bytes) on channel {channel_id} - took {elapsed_time:.1f}ms")
                return True
            else:
                logger.error(f"Failed to play audio file {file_path} after {elapsed_time:.1f}ms")
                return False
                
        except Exception as e:
            logger.error(f"Error playing audio file {file_path}: {e}")
            return False

    async def create_audio_file_from_ulaw(self, ulaw_data: bytes, sample_rate: int = 8000) -> str:
        """Convert ulaw audio data to a WAV file and return the file path."""
        try:
            # Convert ulaw to linear PCM
            pcm_data = audioop.ulaw2lin(ulaw_data, 2)  # 2 bytes per sample (16-bit)
            
            # Create timestamped filename for better debugging
            import time
            timestamp = int(time.time() * 1000)  # milliseconds
            filename = f"audio_{timestamp}_{len(pcm_data)}.wav"
            temp_file_path = f"/tmp/asterisk-audio/{filename}"
            
            # Write WAV file
            with wave.open(temp_file_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data)
            
            # Set proper permissions for Asterisk to read the file
            os.chmod(temp_file_path, 0o644)  # rw-r--r--
            
            # Force filesystem sync and verify file exists
            os.sync()  # Force filesystem sync
            
            # Wait and verify file is accessible
            for attempt in range(10):  # Try up to 10 times (1 second total)
                if os.path.exists(temp_file_path) and os.access(temp_file_path, os.R_OK):
                    file_size = os.path.getsize(temp_file_path)
                    if file_size > 0:
                        logger.debug(f"Created WAV file: {temp_file_path} ({file_size} bytes) - attempt {attempt + 1}")
                        return temp_file_path
                time.sleep(0.1)  # 100ms delay
            
            logger.error(f"Failed to create accessible WAV file after 10 attempts: {temp_file_path}")
            return ""
            
        except Exception as e:
            logger.error(f"Error creating audio file from ulaw: {e}")
            return ""


    async def cleanup_audio_file(self, file_path: str, delay: float = 5.0):
        """Clean up an audio file after a delay."""
        try:
            await asyncio.sleep(delay)
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up audio file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up audio file {file_path}: {e}")

    async def stop_audio_streaming(self, channel_id: str) -> bool:
        """Stop audio streaming and clean up media channel and bridge."""
        media_info = self.active_media_channels.pop(channel_id, None)
        if not media_info:
            logger.warning("No active media channel found to stop for channel.", channel_id=channel_id)
            return True # Not a failure if it's already gone

        media_channel_id = media_info['media_channel_id']
        bridge_id = media_info['bridge_id']
        logger.info("Stopping audio streaming and cleaning up resources...",
                    channel_id=channel_id, media_channel_id=media_channel_id, bridge_id=bridge_id)
        
        try:
            # We don't need to remove channels from the bridge, just destroy it
            await self.destroy_bridge(bridge_id)
            # Hanging up the original channel is handled by StasisEnd
            await self.hangup_channel(media_channel_id)
            logger.info("Successfully cleaned up bridge and media channel.", bridge_id=bridge_id, media_channel_id=media_channel_id)
            return True
        except Exception as e:
            logger.error("Error during audio streaming cleanup", exc_info=True)
            return False

    async def create_external_media_channel(self, app_name: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """Create an external media channel."""
        # Note: external_host will be the address of our UDP server
        # This needs to be coordinated with the UDP server's configuration
        params = {
            "app": app_name,
            "channelId": channel_id,
            "external_host": "127.0.0.1:5060", # Placeholder, should be configured
            "format": "ulaw"
        }
        return await self.send_command("POST", "channels/externalMedia", params=params)

    async def is_channel_active(self, channel_id: str) -> bool:
        """Check if a channel is still active and in Stasis application."""
        try:
            # Try to get channel information from ARI
            result = await self.send_command("GET", f"channels/{channel_id}")
            if result and result.get("id") == channel_id:
                # Channel exists, now check if it's in our Stasis app
                state = result.get("state", "")
                logger.debug("Channel status check", 
                           channel_id=channel_id, 
                           state=state,
                           exists=True)
                return state in ["Up", "Ring", "Ringing", "Dialing"]
            else:
                logger.debug("Channel not found in ARI", 
                           channel_id=channel_id,
                           result=result)
                return False
        except Exception as e:
            logger.debug("Error checking channel status", 
                        channel_id=channel_id, 
                        error=str(e))
            return False

    async def validate_channel_for_playback(self, channel_id: str) -> bool:
        """Validate that a channel is ready for audio playback."""
        try:
            # First check if channel is active
            if not await self.is_channel_active(channel_id):
                logger.warning("Channel validation failed: channel not active", 
                             channel_id=channel_id)
                return False
            
            # Additional check: try to get channel info to ensure it's accessible
            result = await self.send_command("GET", f"channels/{channel_id}")
            if not result:
                logger.warning("Channel validation failed: cannot retrieve channel info", 
                             channel_id=channel_id)
                return False
            
            # Check if channel is in the correct state for playback
            state = result.get("state", "")
            if state not in ["Up"]:
                logger.warning("Channel validation failed: not in correct state for playback", 
                             channel_id=channel_id, 
                             state=state)
                return False
            
            logger.debug("Channel validation successful", 
                        channel_id=channel_id, 
                        state=state)
            return True
            
        except Exception as e:
            logger.warning("Channel validation failed: exception occurred", 
                         channel_id=channel_id, 
                         error=str(e))
            return False

    async def create_external_media_channel(self, app: str, external_host: str, format: str = "ulaw", encapsulation: str = "rtp") -> Optional[Dict[str, Any]]:
        """
        Create an External Media channel for RTP communication.
        
        Args:
            app: ARI application name
            external_host: External host:port for RTP (e.g., "127.0.0.1:10000")
            format: Audio format (default: "ulaw")
            encapsulation: Transport protocol (default: "rtp")
            
        Returns:
            Channel information dict or None if failed
        """
        try:
            response = await self.send_command(
                "POST",
                "channels/externalMedia",
                data={
                    "app": app,
                    "external_host": external_host,
                    "format": format,
                    "encapsulation": encapsulation
                }
            )
            
            if response and response.get("id"):
                logger.info("External Media channel created", 
                           channel_id=response["id"], 
                           external_host=external_host,
                           format=format)
                return response
            else:
                logger.error("Failed to create External Media channel", response=response)
                return None
                
        except Exception as e:
            logger.error("Error creating External Media channel", 
                        external_host=external_host, 
                        error=str(e))
            return None

    async def remove_channel_from_bridge(self, bridge_id: str, channel_id: str) -> bool:
        """Remove a channel from a bridge."""
        try:
            response = await self.send_command(
                "POST",
                f"bridges/{bridge_id}/removeChannel",
                data={"channel": channel_id}
            )

            status = response.get("status") if isinstance(response, dict) else None
            if status is not None:
                if 200 <= int(status) < 300:
                    logger.info("Channel removed from bridge", bridge_id=bridge_id, channel_id=channel_id, status=status)
                    return True
                else:
                    logger.error("Failed to remove channel from bridge", bridge_id=bridge_id, channel_id=channel_id, status=status, response=response)
                    return False

            logger.info("Channel remove-from-bridge response without status; assuming success", bridge_id=bridge_id, channel_id=channel_id, response=response)
            return True
            
        except Exception as e:
            logger.error("Error removing channel from bridge", 
                        bridge_id=bridge_id, 
                        channel_id=channel_id, 
                        error=str(e))
            return False

    async def destroy_bridge(self, bridge_id: str) -> bool:
        """Destroy a bridge."""
        try:
            response = await self.send_command("DELETE", f"bridges/{bridge_id}")
            
            status = response.get("status") if isinstance(response, dict) else None
            if status is not None:
                if 200 <= int(status) < 300:
                    logger.info("Bridge destroyed", bridge_id=bridge_id, status=status)
                    return True
                else:
                    logger.error("Failed to destroy bridge", bridge_id=bridge_id, status=status, response=response)
                    return False

            logger.info("Bridge destroy response without status; assuming success", bridge_id=bridge_id, response=response)
            return True
            
        except Exception as e:
            logger.error("Error destroying bridge", bridge_id=bridge_id, error=str(e))
            return False
