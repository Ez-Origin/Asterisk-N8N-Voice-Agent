#!/usr/bin/env python3
"""
Simple test script to verify SIP client connection with Asterisk.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sip_client import SIPClient, SIPConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_sip_connection():
    """Test SIP connection to Asterisk server."""
    
    # Configuration for testing
    config = SIPConfig(
        host="voiprnd.nemtclouddispatch.com",
        port=5060,
        extension="3000",
        password="AIAgent2025",
        codecs=["ulaw", "alaw", "g722"],
        transport="udp",
        local_ip="0.0.0.0",
        local_port=5060,
        rtp_port_range=(10000, 20000),
        registration_interval=3600,
        call_timeout=30
    )
    
    # Create SIP client
    sip_client = SIPClient(config)
    
    try:
        logger.info("Starting SIP client test...")
        
        # Start the SIP client
        if not await sip_client.start():
            logger.error("Failed to start SIP client")
            return False
        
        # Wait a moment for registration
        await asyncio.sleep(3)
        
        # Check registration status
        if sip_client.is_registered():
            logger.info("✅ Successfully registered with Asterisk")
            
            # Show call information
            calls = sip_client.get_all_calls()
            logger.info(f"Active calls: {len(calls)}")
            
            # Wait for a bit to monitor
            logger.info("Monitoring for 10 seconds...")
            await asyncio.sleep(10)
            
            return True
        else:
            logger.error("❌ Failed to register with Asterisk")
            return False
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False
    finally:
        # Stop the SIP client
        await sip_client.stop()
        logger.info("SIP client stopped")


async def main():
    """Main test function."""
    logger.info("=" * 50)
    logger.info("SIP Client Connection Test")
    logger.info("=" * 50)
    
    success = await test_sip_connection()
    
    if success:
        logger.info("✅ Test completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Test failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
