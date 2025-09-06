"""
Unit tests for SIP Client implementation.
"""

import pytest
import asyncio
import socket
from unittest.mock import Mock, patch, MagicMock
from src.sip_client import SIPClient, SIPConfig, CallInfo


class TestSIPConfig:
    """Test SIP configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = SIPConfig(host="test.example.com")
        assert config.host == "test.example.com"
        assert config.port == 5060
        assert config.extension == "3000"
        assert config.password == "AIAgent2025"
        assert config.transport == "udp"
        assert config.codecs == ["ulaw", "alaw", "g722"]
        assert config.local_ip == "0.0.0.0"
        assert config.local_port == 5060
        assert config.rtp_port_range == (10000, 20000)
        assert config.registration_interval == 3600
        assert config.call_timeout == 30
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = SIPConfig(
            host="custom.example.com",
            port=5061,
            extension="4000",
            password="CustomPass123",
            transport="tcp",
            codecs=["ulaw", "g722"],
            local_ip="192.168.1.100",
            local_port=5061,
            rtp_port_range=(20000, 30000),
            registration_interval=1800,
            call_timeout=60
        )
        assert config.host == "custom.example.com"
        assert config.port == 5061
        assert config.extension == "4000"
        assert config.password == "CustomPass123"
        assert config.transport == "tcp"
        assert config.codecs == ["ulaw", "g722"]
        assert config.local_ip == "192.168.1.100"
        assert config.local_port == 5061
        assert config.rtp_port_range == (20000, 30000)
        assert config.registration_interval == 1800
        assert config.call_timeout == 60


class TestSIPClient:
    """Test SIP client functionality."""
    
    @pytest.fixture
    def sip_config(self):
        """Create a test SIP configuration."""
        return SIPConfig(
            host="test.example.com",
            extension="3000",
            password="testpass"
        )
    
    @pytest.fixture
    def sip_client(self, sip_config):
        """Create a test SIP client."""
        return SIPClient(sip_config)
    
    def test_client_initialization(self, sip_client, sip_config):
        """Test SIP client initialization."""
        assert sip_client.config == sip_config
        assert sip_client.registered == False
        assert sip_client.calls == {}
        assert sip_client.call_handlers == {}
        assert sip_client.registration_handlers == []
        assert sip_client.running == False
        assert sip_client.socket is None
        assert sip_client.rtp_socket is None
    
    def test_generate_tag(self, sip_client):
        """Test tag generation."""
        tag = sip_client._generate_tag()
        assert tag.startswith("tag-")
        assert len(tag) > 10
        
        # Generate another tag to ensure uniqueness
        tag2 = sip_client._generate_tag()
        assert tag != tag2
    
    def test_generate_branch(self, sip_client):
        """Test branch generation."""
        branch = sip_client._generate_branch()
        assert branch.startswith("z9hG4bK")
        assert len(branch) > 15
        
        # Generate another branch to ensure uniqueness
        branch2 = sip_client._generate_branch()
        assert branch != branch2
    
    def test_generate_call_id(self, sip_client):
        """Test Call-ID generation."""
        call_id = sip_client._generate_call_id()
        assert call_id.startswith("call-")
        assert sip_client.config.local_ip in call_id
        
        # Generate another Call-ID to ensure uniqueness
        call_id2 = sip_client._generate_call_id()
        assert call_id != call_id2
    
    def test_find_available_rtp_port(self, sip_client):
        """Test RTP port finding."""
        port = sip_client._find_available_rtp_port()
        assert sip_client.config.rtp_port_range[0] <= port < sip_client.config.rtp_port_range[1]
        
        # Test that the port is actually available
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            test_socket.bind((sip_client.config.local_ip, port))
            # If we get here, the port is available
            assert True
        except OSError:
            assert False, "Port should be available"
        finally:
            test_socket.close()
    
    def test_build_register_message(self, sip_client):
        """Test REGISTER message building."""
        message = sip_client._build_register_message()
        
        assert "REGISTER sip:test.example.com SIP/2.0" in message
        assert f"From: <sip:3000@test.example.com>;tag={sip_client._tag}" in message
        assert f"To: <sip:3000@test.example.com>" in message
        assert "Call-ID:" in message
        assert "CSeq: 1 REGISTER" in message
        assert "Contact:" in message
        assert "Expires: 3600" in message
        assert "User-Agent: Asterisk-AI-Voice-Agent/1.0" in message
        assert "Content-Length: 0" in message
    
    def test_build_unregister_message(self, sip_client):
        """Test UNREGISTER message building."""
        message = sip_client._build_unregister_message()
        
        assert "REGISTER sip:test.example.com SIP/2.0" in message
        assert "Expires: 0" in message  # Key difference from REGISTER
        assert "User-Agent: Asterisk-AI-Voice-Agent/1.0" in message
    
    def test_build_invite_message(self, sip_client):
        """Test INVITE message building."""
        destination = "4000"
        call_id = "test-call-123"
        message = sip_client._build_invite_message(destination, call_id)
        
        assert f"INVITE sip:{destination}@test.example.com SIP/2.0" in message
        assert f"Call-ID: {call_id}" in message
        assert "Content-Type: application/sdp" in message
        assert "Content-Length:" in message
        assert "v=0" in message  # SDP version
        assert "m=audio" in message  # SDP media line
    
    def test_build_sdp(self, sip_client):
        """Test SDP building."""
        sdp = sip_client._build_sdp()
        
        assert "v=0" in sdp
        assert "o=asterisk-ai-voice-agent" in sdp
        assert "s=Asterisk AI Voice Agent" in sdp
        assert "c=IN IP4" in sdp
        assert "t=0 0" in sdp
        assert f"m=audio {sip_client.rtp_port} RTP/AVP" in sdp
        assert "a=rtpmap:0 PCMU/8000" in sdp  # ulaw
        assert "a=rtpmap:8 PCMA/8000" in sdp  # alaw
        assert "a=rtpmap:9 G722/8000" in sdp  # g722
        assert "a=sendrecv" in sdp
    
    def test_parse_sdp(self, sip_client):
        """Test SDP parsing."""
        response = """SIP/2.0 200 OK
Content-Type: application/sdp
Content-Length: 200

v=0
o=test 1234567890 1234567890 IN IP4 192.168.1.100
s=Test Session
c=IN IP4 192.168.1.100
t=0 0
m=audio 10000 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""
        
        rtp_info = sip_client._parse_sdp(response)
        
        assert rtp_info['ip'] == "192.168.1.100"
        assert rtp_info['port'] == 10000
        assert rtp_info['codec'] == "ulaw"  # First codec in the list
    
    def test_parse_sdp_g722(self, sip_client):
        """Test SDP parsing with G.722 codec."""
        response = """SIP/2.0 200 OK
Content-Type: application/sdp
Content-Length: 200

v=0
o=test 1234567890 1234567890 IN IP4 192.168.1.100
s=Test Session
c=IN IP4 192.168.1.100
t=0 0
m=audio 10000 RTP/AVP 9
a=rtpmap:9 G722/8000
a=sendrecv
"""
        
        rtp_info = sip_client._parse_sdp(response)
        
        assert rtp_info['ip'] == "192.168.1.100"
        assert rtp_info['port'] == 10000
        assert rtp_info['codec'] == "g722"
    
    @pytest.mark.asyncio
    async def test_send_message(self, sip_client):
        """Test message sending."""
        with patch.object(sip_client.socket, 'sendto') as mock_sendto:
            sip_client.socket = Mock()
            message = "TEST MESSAGE"
            await sip_client._send_message(message)
            
            mock_sendto.assert_called_once()
            args, kwargs = mock_sendto.call_args
            assert args[0] == message.encode('utf-8')
            assert args[1] == (sip_client.config.host, sip_client.config.port)
    
    @pytest.mark.asyncio
    async def test_wait_for_response_timeout(self, sip_client):
        """Test response waiting with timeout."""
        with patch.object(sip_client.socket, 'recvfrom') as mock_recvfrom:
            sip_client.socket = Mock()
            mock_recvfrom.side_effect = socket.timeout()
            
            response = await sip_client._wait_for_response(timeout=0.1)
            assert response is None
    
    @pytest.mark.asyncio
    async def test_wait_for_response_success(self, sip_client):
        """Test successful response waiting."""
        with patch.object(sip_client.socket, 'recvfrom') as mock_recvfrom:
            sip_client.socket = Mock()
            mock_recvfrom.return_value = (b"SIP/2.0 200 OK\r\n\r\n", ("192.168.1.1", 5060))
            
            response = await sip_client._wait_for_response()
            assert response == "SIP/2.0 200 OK\r\n\r\n"
    
    def test_add_registration_handler(self, sip_client):
        """Test adding registration handlers."""
        handler1 = Mock()
        handler2 = Mock()
        
        sip_client.add_registration_handler(handler1)
        sip_client.add_registration_handler(handler2)
        
        assert len(sip_client.registration_handlers) == 2
        assert handler1 in sip_client.registration_handlers
        assert handler2 in sip_client.registration_handlers
    
    def test_notify_registration_handlers(self, sip_client):
        """Test registration handler notification."""
        handler1 = Mock()
        handler2 = Mock()
        
        sip_client.registration_handlers = [handler1, handler2]
        sip_client._notify_registration_handlers(True)
        
        handler1.assert_called_once_with(True)
        handler2.assert_called_once_with(True)
    
    def test_notify_registration_handlers_error(self, sip_client):
        """Test registration handler notification with error."""
        handler1 = Mock()
        handler2 = Mock()
        handler2.side_effect = Exception("Test error")
        
        sip_client.registration_handlers = [handler1, handler2]
        
        # Should not raise exception, just log error
        sip_client._notify_registration_handlers(True)
        
        handler1.assert_called_once_with(True)
        handler2.assert_called_once_with(True)
    
    def test_get_call_info(self, sip_client):
        """Test getting call information."""
        call_id = "test-call-123"
        call_info = CallInfo(
            call_id=call_id,
            from_user="3000",
            to_user="4000",
            local_rtp_port=10000,
            remote_rtp_port=20000,
            remote_ip="192.168.1.100",
            codec="ulaw",
            start_time=1234567890.0
        )
        
        sip_client.calls[call_id] = call_info
        
        retrieved_info = sip_client.get_call_info(call_id)
        assert retrieved_info == call_info
        
        # Test non-existent call
        non_existent = sip_client.get_call_info("non-existent")
        assert non_existent is None
    
    def test_get_all_calls(self, sip_client):
        """Test getting all call information."""
        call1 = CallInfo("call1", "3000", "4000", 10000, 20000, "192.168.1.100", "ulaw", 1234567890.0)
        call2 = CallInfo("call2", "3000", "5000", 10001, 20001, "192.168.1.101", "alaw", 1234567891.0)
        
        sip_client.calls = {"call1": call1, "call2": call2}
        
        all_calls = sip_client.get_all_calls()
        assert len(all_calls) == 2
        assert "call1" in all_calls
        assert "call2" in all_calls
        assert all_calls["call1"] == call1
        assert all_calls["call2"] == call2
    
    def test_is_registered(self, sip_client):
        """Test registration status checking."""
        assert sip_client.is_registered() == False
        
        sip_client.registered = True
        assert sip_client.is_registered() == True
        
        sip_client.registered = False
        assert sip_client.is_registered() == False


class TestCallInfo:
    """Test CallInfo dataclass."""
    
    def test_call_info_creation(self):
        """Test CallInfo creation with all parameters."""
        call_info = CallInfo(
            call_id="test-call-123",
            from_user="3000",
            to_user="4000",
            local_rtp_port=10000,
            remote_rtp_port=20000,
            remote_ip="192.168.1.100",
            codec="ulaw",
            start_time=1234567890.0,
            state="connected"
        )
        
        assert call_info.call_id == "test-call-123"
        assert call_info.from_user == "3000"
        assert call_info.to_user == "4000"
        assert call_info.local_rtp_port == 10000
        assert call_info.remote_rtp_port == 20000
        assert call_info.remote_ip == "192.168.1.100"
        assert call_info.codec == "ulaw"
        assert call_info.start_time == 1234567890.0
        assert call_info.state == "connected"
    
    def test_call_info_default_state(self):
        """Test CallInfo creation with default state."""
        call_info = CallInfo(
            call_id="test-call-123",
            from_user="3000",
            to_user="4000",
            local_rtp_port=10000,
            remote_rtp_port=20000,
            remote_ip="192.168.1.100",
            codec="ulaw",
            start_time=1234567890.0
        )
        
        assert call_info.state == "ringing"  # Default value


if __name__ == "__main__":
    pytest.main([__file__])


