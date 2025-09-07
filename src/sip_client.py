"""
SIP Client for Asterisk Integration

This module provides a SIP client implementation for registering as a PJSIP extension
with Asterisk 16+ and handling RTP audio streams. It supports G.711 µ-law/A-law and
G.722 codecs with NAT traversal capabilities.
"""

import asyncio
import logging
import socket
import struct
import time
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum
import hashlib
import random
import re

# Configure logging
logger = logging.getLogger(__name__)


class SIPMethod(Enum):
    """SIP method types."""
    REGISTER = "REGISTER"
    INVITE = "INVITE"
    ACK = "ACK"
    BYE = "BYE"
    CANCEL = "CANCEL"
    OPTIONS = "OPTIONS"
    INFO = "INFO"


class SIPResponseCode(Enum):
    """SIP response codes."""
    TRYING = 100
    RINGING = 180
    OK = 200
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    REQUEST_TIMEOUT = 408
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503


@dataclass
class SIPConfig:
    """SIP configuration parameters."""
    host: str
    port: int = 5060
    extension: str = "3000"
    password: str = "AIAgent2025"
    transport: str = "udp"  # udp, tcp, tls
    codecs: List[str] = None
    local_ip: str = "0.0.0.0"
    local_port: int = 15060
    rtp_port_range: tuple = (10000, 20000)
    registration_interval: int = 3600  # seconds
    call_timeout: int = 30  # seconds
    
    def __post_init__(self):
        if self.codecs is None:
            self.codecs = ["ulaw", "alaw", "g722"]


@dataclass
class CallInfo:
    """Information about an active call."""
    call_id: str
    from_user: str
    to_user: str
    local_rtp_port: int
    remote_rtp_port: int
    remote_ip: str
    codec: str
    start_time: float
    state: str = "ringing"  # ringing, connected, ended


class SIPClient:
    """
    SIP client for Asterisk integration.
    
    Handles SIP registration, call management, and RTP audio streaming
    with support for multiple codecs and NAT traversal.
    """
    
    def __init__(self, config: SIPConfig):
        self.config = config
        self.socket: Optional[socket.socket] = None
        self.registered = False
        self.calls: Dict[str, CallInfo] = {}
        self.call_handlers: Dict[str, Callable] = {}
        self.registration_handlers: List[Callable] = []
        self.running = False
        self._sequence_number = 1
        self._tag = self._generate_tag()
        self._branch = self._generate_branch()
        
        # RTP configuration
        self.rtp_socket: Optional[socket.socket] = None
        self.rtp_port = self._find_available_rtp_port()
        
        logger.info(f"SIP Client initialized for {config.extension}@{config.host}:{config.port}")
    
    def _generate_tag(self) -> str:
        """Generate a unique SIP tag."""
        return f"tag-{random.randint(100000, 999999)}"
    
    def _generate_branch(self) -> str:
        """Generate a unique SIP branch."""
        return f"z9hG4bK{random.randint(100000, 999999)}"
    
    def _find_available_rtp_port(self) -> int:
        """Find an available RTP port in the configured range."""
        for port in range(self.config.rtp_port_range[0], self.config.rtp_port_range[1]):
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_socket.bind((self.config.local_ip, port))
                test_socket.close()
                return port
            except OSError:
                continue
        raise RuntimeError("No available RTP ports in the configured range")
    
    async def start(self) -> bool:
        """Start the SIP client and register with Asterisk."""
        try:
            # Create UDP socket for SIP signaling
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.info(f"Attempting to bind to {self.config.local_ip}:{self.config.local_port}")
            self.socket.bind((self.config.local_ip, self.config.local_port))
            self.socket.settimeout(1.0)  # 1 second timeout for non-blocking operation
            logger.info(f"Successfully bound to {self.config.local_ip}:{self.config.local_port}")
            
            # Create UDP socket for RTP audio
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtp_socket.bind((self.config.local_ip, self.rtp_port))
            
            self.running = True
            logger.info(f"SIP client started on {self.config.local_ip}:{self.config.local_port}")
            logger.info(f"RTP socket bound to port {self.rtp_port}")
            
            # Start background tasks
            asyncio.create_task(self._message_loop())
            asyncio.create_task(self._registration_loop())
            
            # Initial registration
            await self.register()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start SIP client: {e}")
            return False
    
    async def stop(self):
        """Stop the SIP client and cleanup resources."""
        self.running = False
        
        # Unregister from Asterisk
        if self.registered:
            await self.unregister()
        
        # Close sockets
        if self.socket:
            self.socket.close()
        if self.rtp_socket:
            self.rtp_socket.close()
        
        logger.info("SIP client stopped")
    
    async def register(self) -> bool:
        """Register with Asterisk server."""
        try:
            # Send REGISTER request
            register_msg = self._build_register_message()
            await self._send_message(register_msg)
            
            # Wait for response
            response = await self._wait_for_response()
            
            if response and "401" in response:
                # Handle authentication challenge
                return await self._handle_authentication(response)
            elif response and "200" in response:
                self.registered = True
                logger.info(f"Successfully registered as {self.config.extension}")
                self._notify_registration_handlers(True)
                return True
            else:
                logger.error(f"Registration failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    async def unregister(self) -> bool:
        """Unregister from Asterisk server."""
        try:
            unregister_msg = self._build_unregister_message()
            await self._send_message(unregister_msg)
            
            response = await self._wait_for_response()
            if response and "200" in response:
                self.registered = False
                logger.info(f"Successfully unregistered {self.config.extension}")
                self._notify_registration_handlers(False)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Unregistration error: {e}")
            return False
    
    async def make_call(self, destination: str, audio_handler: Optional[Callable] = None) -> Optional[str]:
        """Make an outbound call to the specified destination."""
        try:
            call_id = f"call-{random.randint(100000, 999999)}"
            
            # Build INVITE message
            invite_msg = self._build_invite_message(destination, call_id)
            await self._send_message(invite_msg)
            
            # Wait for response
            response = await self._wait_for_response()
            
            if response and "200" in response:
                # Parse SDP to get RTP information
                rtp_info = self._parse_sdp(response)
                
                # Create call info
                call_info = CallInfo(
                    call_id=call_id,
                    from_user=self.config.extension,
                    to_user=destination,
                    local_rtp_port=self.rtp_port,
                    remote_rtp_port=rtp_info.get('port', 0),
                    remote_ip=rtp_info.get('ip', ''),
                    codec=rtp_info.get('codec', 'ulaw'),
                    start_time=time.time()
                )
                
                self.calls[call_id] = call_info
                if audio_handler:
                    self.call_handlers[call_id] = audio_handler
                
                # Send ACK
                ack_msg = self._build_ack_message(call_id, response)
                await self._send_message(ack_msg)
                
                # Start RTP audio handling
                asyncio.create_task(self._handle_rtp_audio(call_id))
                
                logger.info(f"Call {call_id} established to {destination}")
                return call_id
            else:
                logger.error(f"Call failed: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Make call error: {e}")
            return None
    
    async def end_call(self, call_id: str) -> bool:
        """End the specified call."""
        try:
            if call_id not in self.calls:
                return False
            
            # Send BYE message
            bye_msg = self._build_bye_message(call_id)
            await self._send_message(bye_msg)
            
            # Wait for response
            response = await self._wait_for_response()
            
            # Cleanup call
            if call_id in self.calls:
                del self.calls[call_id]
            if call_id in self.call_handlers:
                del self.call_handlers[call_id]
            
            logger.info(f"Call {call_id} ended")
            return True
            
        except Exception as e:
            logger.error(f"End call error: {e}")
            return False
    
    def add_registration_handler(self, handler: Callable):
        """Add a handler for registration status changes."""
        self.registration_handlers.append(handler)
    
    def _build_register_message(self) -> str:
        """Build a SIP REGISTER message."""
        via = f"SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
        from_header = f"<sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
        to_header = f"<sip:{self.config.extension}@{self.config.host}>"
        contact = f"<sip:{self.config.extension}@{self.config.local_ip}:{self.config.local_port}>"
        
        message = f"""REGISTER sip:{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {self._generate_call_id()}\r
CSeq: {self._sequence_number} REGISTER\r
Contact: {contact}\r
Expires: {self.config.registration_interval}\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
Content-Length: 0\r
\r
"""
        return message
    
    def _build_unregister_message(self) -> str:
        """Build a SIP UNREGISTER message (REGISTER with Expires: 0)."""
        via = f"SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
        from_header = f"<sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
        to_header = f"<sip:{self.config.extension}@{self.config.host}>"
        contact = f"<sip:{self.config.extension}@{self.config.local_ip}:{self.config.local_port}>"
        
        message = f"""REGISTER sip:{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {self._generate_call_id()}\r
CSeq: {self._sequence_number} REGISTER\r
Contact: {contact}\r
Expires: 0\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
Content-Length: 0\r
\r
"""
        return message
    
    def _build_invite_message(self, destination: str, call_id: str) -> str:
        """Build a SIP INVITE message."""
        via = f"Via: SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
        from_header = f"From: <sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
        to_header = f"To: <sip:{destination}@{self.config.host}>"
        
        # Build SDP for audio
        sdp = self._build_sdp()
        
        message = f"""INVITE sip:{destination}@{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: {self._sequence_number} INVITE\r
Contact: <sip:{self.config.extension}@{self.config.local_ip}:{self.config.local_port}>\r
Content-Type: application/sdp\r
Content-Length: {len(sdp)}\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
\r
{sdp}"""
        return message
    
    def _build_ack_message(self, call_id: str, response: str) -> str:
        """Build a SIP ACK message."""
        via = f"Via: SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
        from_header = f"From: <sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
        to_header = f"To: <sip:{self.config.extension}@{self.config.host}>"
        
        message = f"""ACK sip:{self.config.extension}@{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: {self._sequence_number} ACK\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
\r
"""
        return message
    
    def _build_bye_message(self, call_id: str) -> str:
        """Build a SIP BYE message."""
        via = f"Via: SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
        from_header = f"From: <sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
        to_header = f"To: <sip:{self.config.extension}@{self.config.host}>"
        
        message = f"""BYE sip:{self.config.extension}@{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: {self._sequence_number} BYE\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
\r
"""
        return message
    
    def _build_sdp(self) -> str:
        """Build SDP (Session Description Protocol) for audio."""
        # Get local IP address
        local_ip = self.config.local_ip
        if local_ip == "0.0.0.0":
            # Get actual local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((self.config.host, 80))
                local_ip = s.getsockname()[0]
            except:
                local_ip = "127.0.0.1"
            finally:
                s.close()
        
        # Build codec list
        codec_list = []
        for codec in self.config.codecs:
            if codec == "ulaw":
                codec_list.append("0 PCMU/8000")
            elif codec == "alaw":
                codec_list.append("8 PCMA/8000")
            elif codec == "g722":
                codec_list.append("9 G722/8000")
        
        sdp = f"""v=0\r
o=asterisk-ai-voice-agent 1234567890 1234567890 IN IP4 {local_ip}\r
s=Asterisk AI Voice Agent\r
c=IN IP4 {local_ip}\r
t=0 0\r
m=audio {self.rtp_port} RTP/AVP {' '.join([c.split()[0] for c in codec_list])}\r
a=rtpmap:0 PCMU/8000\r
a=rtpmap:8 PCMA/8000\r
a=rtpmap:9 G722/8000\r
a=sendrecv\r
"""
        return sdp
    
    def _parse_sdp(self, response: str) -> Dict[str, Any]:
        """Parse SDP from SIP response to extract RTP information."""
        rtp_info = {}
        
        # Extract IP address
        ip_match = re.search(r'c=IN IP4 (\d+\.\d+\.\d+\.\d+)', response)
        if ip_match:
            rtp_info['ip'] = ip_match.group(1)
        
        # Extract RTP port
        port_match = re.search(r'm=audio (\d+) RTP/AVP', response)
        if port_match:
            rtp_info['port'] = int(port_match.group(1))
        
        # Extract codec
        codec_match = re.search(r'a=rtpmap:(\d+) (\w+)/', response)
        if codec_match:
            codec_num = codec_match.group(1)
            codec_name = codec_match.group(2)
            if codec_num == "0":
                rtp_info['codec'] = "ulaw"
            elif codec_num == "8":
                rtp_info['codec'] = "alaw"
            elif codec_num == "9":
                rtp_info['codec'] = "g722"
        
        return rtp_info
    
    def _generate_call_id(self) -> str:
        """Generate a unique Call-ID."""
        return f"call-{random.randint(100000, 999999)}@{self.config.local_ip}"
    
    async def _send_message(self, message: str):
        """Send a SIP message to the server."""
        try:
            data = message.encode('utf-8')
            self.socket.sendto(data, (self.config.host, self.config.port))
            logger.debug(f"Sent SIP message to {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.error(f"Failed to send SIP message: {e}")
    
    async def _wait_for_response(self, timeout: float = 5.0) -> Optional[str]:
        """Wait for a SIP response from the server."""
        try:
            self.socket.settimeout(timeout)
            data, addr = self.socket.recvfrom(4096)
            response = data.decode('utf-8')
            logger.debug(f"Received SIP response from {addr}")
            return response
        except socket.timeout:
            logger.warning("SIP response timeout")
            return None
        except Exception as e:
            logger.error(f"Error receiving SIP response: {e}")
            return None
    
    async def _handle_authentication(self, response: str) -> bool:
        """Handle SIP authentication challenge."""
        try:
            # Extract nonce and realm from 401 response
            nonce_match = re.search(r'nonce="([^"]+)"', response)
            realm_match = re.search(r'realm="([^"]+)"', response)
            
            if not nonce_match or not realm_match:
                logger.error("Missing nonce or realm in 401 response")
                return False
            
            nonce = nonce_match.group(1)
            realm = realm_match.group(1)
            
            # Generate authentication response
            ha1 = hashlib.md5(f"{self.config.extension}:{realm}:{self.config.password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"REGISTER:sip:{self.config.host}".encode()).hexdigest()
            response_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
            
            # Build authenticated REGISTER message
            auth_header = f'Authorization: Digest username="{self.config.extension}", realm="{realm}", nonce="{nonce}", uri="sip:{self.config.host}", response="{response_hash}"'
            
            via = f"SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch={self._branch}"
            from_header = f"<sip:{self.config.extension}@{self.config.host}>;tag={self._tag}"
            to_header = f"<sip:{self.config.extension}@{self.config.host}>"
            contact = f"<sip:{self.config.extension}@{self.config.local_ip}:{self.config.local_port}>"
            
            message = f"""REGISTER sip:{self.config.host} SIP/2.0\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {self._generate_call_id()}\r
CSeq: {self._sequence_number + 1} REGISTER\r
Contact: {contact}\r
Expires: {self.config.registration_interval}\r
Max-Forwards: 70\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
{auth_header}\r
Content-Length: 0\r
\r
"""
            
            await self._send_message(message)
            auth_response = await self._wait_for_response()
            
            if auth_response and "200" in auth_response:
                self.registered = True
                logger.info(f"Successfully authenticated and registered as {self.config.extension}")
                self._notify_registration_handlers(True)
                return True
            else:
                logger.error(f"Authentication failed: {auth_response}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def _message_loop(self):
        """Main message processing loop."""
        logger.info("SIP message loop started")
        while self.running:
            try:
                self.socket.settimeout(0.1)  # Short timeout for non-blocking operation
                data, addr = self.socket.recvfrom(4096)
                logger.info(f"Received SIP message from {addr}: {data[:100]}...")
                message = data.decode('utf-8')
                
                # Process incoming SIP message
                await self._process_incoming_message(message, addr)
                
            except socket.timeout:
                # No message received, continue
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_incoming_message(self, message: str, addr: tuple):
        """Process an incoming SIP message."""
        try:
            if "INVITE" in message and "SIP/2.0" in message:
                # Handle incoming call
                await self._handle_incoming_call(message, addr)
            elif "BYE" in message and "SIP/2.0" in message:
                # Handle call termination
                await self._handle_call_termination(message, addr)
            elif "OPTIONS" in message and "SIP/2.0" in message:
                # Handle OPTIONS request (health check)
                await self._handle_options_request(message, addr)
            else:
                logger.debug(f"Unhandled SIP message: {message[:100]}...")
                
        except Exception as e:
            logger.error(f"Error processing incoming message: {e}")
    
    async def _handle_incoming_call(self, message: str, addr: tuple):
        """Handle an incoming call."""
        try:
            # Extract call information
            call_id_match = re.search(r'Call-ID: ([^\r\n]+)', message)
            from_match = re.search(r'From: <sip:([^@]+)@', message)
            
            if not call_id_match or not from_match:
                logger.error("Could not extract call information from INVITE")
                return
            
            call_id = call_id_match.group(1).strip()
            from_user = from_match.group(1)
            
            # Create call info
            call_info = CallInfo(
                call_id=call_id,
                from_user=from_user,
                to_user=self.config.extension,
                local_rtp_port=self.rtp_port,
                remote_rtp_port=0,  # Will be updated from SDP
                remote_ip=addr[0],
                codec="ulaw",  # Default
                start_time=time.time()
            )
            
            # Set initial state to ringing
            call_info.state = "ringing"
            self.calls[call_id] = call_info
            
            # Send 180 Ringing
            ringing_msg = self._build_ringing_response(call_id, message)
            await self._send_message(ringing_msg)
            
            # Send 200 OK with SDP
            ok_msg = self._build_ok_response(call_id, message)
            await self._send_message(ok_msg)
            
            # Update call state to connected after sending 200 OK
            call_info.state = "connected"
            
            # Start RTP audio handling
            asyncio.create_task(self._handle_rtp_audio(call_id))
            
            logger.info(f"Incoming call {call_id} from {from_user} - state: {call_info.state}")
            
        except Exception as e:
            logger.error(f"Error handling incoming call: {e}")
    
    async def _handle_call_termination(self, message: str, addr: tuple):
        """Handle call termination."""
        try:
            call_id_match = re.search(r'Call-ID: ([^\r\n]+)', message)
            if call_id_match:
                call_id = call_id_match.group(1).strip()
                if call_id in self.calls:
                    del self.calls[call_id]
                if call_id in self.call_handlers:
                    del self.call_handlers[call_id]
                logger.info(f"Call {call_id} terminated")
                
        except Exception as e:
            logger.error(f"Error handling call termination: {e}")
    
    async def hangup_call(self, call_id: str):
        """Hang up a specific call."""
        try:
            if call_id in self.calls:
                call_info = self.calls[call_id]
                # Send BYE message to terminate the call
                bye_msg = self._build_bye_message(call_id, call_info)
                await self._send_message(bye_msg)
                logger.info(f"Sent BYE for call {call_id}")
            else:
                logger.warning(f"Call {call_id} not found for hangup")
        except Exception as e:
            logger.error(f"Error hanging up call {call_id}: {e}")
    
    def _build_bye_message(self, call_id: str, call_info: CallInfo) -> str:
        """Build a BYE message to terminate a call."""
        return f"""BYE sip:{call_info.from_user}@voiprnd.nemtclouddispatch.com SIP/2.0\r
Via: SIP/2.0/UDP {self.config.local_ip}:{self.config.local_port};branch=z9hG4bKPjbye\r
From: <sip:{call_info.to_user}@voiprnd.nemtclouddispatch.com>;tag=as{call_id[:8]}\r
To: <sip:{call_info.from_user}@voiprnd.nemtclouddispatch.com>;tag=as{call_id[8:16]}\r
Call-ID: {call_id}\r
CSeq: 2 BYE\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
Content-Length: 0\r
\r
"""
    
    async def _handle_options_request(self, message: str, addr: tuple):
        """Handle OPTIONS request (health check)."""
        try:
            # Extract Call-ID and CSeq from the OPTIONS request
            call_id_match = re.search(r'Call-ID: ([^\r\n]+)', message)
            cseq_match = re.search(r'CSeq: (\d+) OPTIONS', message)
            
            if not call_id_match or not cseq_match:
                logger.error("Could not extract Call-ID or CSeq from OPTIONS request")
                return
            
            call_id = call_id_match.group(1).strip()
            cseq = cseq_match.group(1).strip()
            
            # Extract Via header from the original request to echo it back
            via_match = re.search(r'Via: ([^\r\n]+)', message)
            via_header = via_match.group(1) if via_match else "SIP/2.0/UDP 172.17.0.1:5060;rport;branch=z9hG4bKPje2"
            
            # Extract From and To headers from the original request
            from_match = re.search(r'From: ([^\r\n]+)', message)
            to_match = re.search(r'To: ([^\r\n]+)', message)
            
            from_header = from_match.group(1) if from_match else "<sip:3000@voiprnd.nemtclouddispatch.com>;tag=as12345678"
            to_header = to_match.group(1) if to_match else "<sip:3000@172.17.0.3:15060>;tag=as87654321"
            
            # Send 200 OK response with proper headers
            response = f"""SIP/2.0 200 OK\r
Via: {via_header}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: {cseq} OPTIONS\r
Contact: <sip:3000@172.17.0.3:15060>\r
Allow: INVITE, ACK, CANCEL, OPTIONS, BYE, REFER, NOTIFY\r
Accept: application/sdp\r
Accept-Encoding: identity\r
Accept-Language: en\r
Supported: replaces\r
User-Agent: Asterisk-AI-Voice-Agent/1.0\r
Content-Length: 0\r
\r
"""
            
            # Send the response
            self.socket.sendto(response.encode('utf-8'), addr)
            logger.info(f"Sent OPTIONS 200 OK response to {addr}")
            
        except Exception as e:
            logger.error(f"Error handling OPTIONS request: {e}")
    
    def _build_ringing_response(self, call_id: str, original_message: str) -> str:
        """Build a 180 Ringing response."""
        # Extract Via header from original message
        via_match = re.search(r'Via: ([^\r\n]+)', original_message)
        via = via_match.group(1) if via_match else ""
        
        # Extract From and To headers
        from_match = re.search(r'From: ([^\r\n]+)', original_message)
        to_match = re.search(r'To: ([^\r\n]+)', original_message)
        
        from_header = from_match.group(1) if from_match else ""
        to_header = to_match.group(1) if to_match else ""
        
        message = f"""SIP/2.0 180 Ringing\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: 1 INVITE\r
Content-Length: 0\r
\r
"""
        return message
    
    def _build_ok_response(self, call_id: str, original_message: str) -> str:
        """Build a 200 OK response with SDP."""
        # Extract Via header from original message
        via_match = re.search(r'Via: ([^\r\n]+)', original_message)
        via = via_match.group(1) if via_match else ""
        
        # Extract From and To headers
        from_match = re.search(r'From: ([^\r\n]+)', original_message)
        to_match = re.search(r'To: ([^\r\n]+)', original_message)
        
        from_header = from_match.group(1) if from_match else ""
        to_header = to_match.group(1) if to_match else ""
        
        # Build SDP
        sdp = self._build_sdp()
        
        message = f"""SIP/2.0 200 OK\r
Via: {via}\r
From: {from_header}\r
To: {to_header}\r
Call-ID: {call_id}\r
CSeq: 1 INVITE\r
Contact: <sip:{self.config.extension}@{self.config.local_ip}:{self.config.local_port}>\r
Content-Type: application/sdp\r
Content-Length: {len(sdp)}\r
\r
{sdp}"""
        return message
    
    async def _handle_rtp_audio(self, call_id: str):
        """Handle RTP audio for a call."""
        try:
            if call_id not in self.calls:
                return
            
            call_info = self.calls[call_id]
            logger.info(f"Starting RTP audio handling for call {call_id}")
            
            # This is a placeholder for RTP audio handling
            # In a real implementation, this would:
            # 1. Receive RTP packets from the remote party
            # 2. Decode audio using the negotiated codec
            # 3. Process audio (VAD, noise suppression, etc.)
            # 4. Send audio to AI provider
            # 5. Receive audio from AI provider
            # 6. Encode audio using the negotiated codec
            # 7. Send RTP packets to the remote party
            
            # For now, just log that RTP handling started
            while call_id in self.calls and self.running:
                await asyncio.sleep(1)
            
            logger.info(f"RTP audio handling ended for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error in RTP audio handling for call {call_id}: {e}")
    
    async def _registration_loop(self):
        """Periodic registration refresh loop."""
        while self.running:
            try:
                await asyncio.sleep(self.config.registration_interval - 60)  # Refresh 1 minute before expiry
                
                if self.registered:
                    await self.register()
                    
            except Exception as e:
                logger.error(f"Error in registration loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    def _notify_registration_handlers(self, registered: bool):
        """Notify registration status change handlers."""
        for handler in self.registration_handlers:
            try:
                handler(registered)
            except Exception as e:
                logger.error(f"Error in registration handler: {e}")
    
    def get_call_info(self, call_id: str) -> Optional[CallInfo]:
        """Get information about a specific call."""
        return self.calls.get(call_id)
    
    def get_all_calls(self) -> Dict[str, CallInfo]:
        """Get information about all active calls."""
        return self.calls.copy()
    
    def is_registered(self) -> bool:
        """Check if the client is registered with Asterisk."""
        return self.registered
