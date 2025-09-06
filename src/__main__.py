#!/usr/bin/env python3
"""
Asterisk AI Voice Agent - Main Entry Point

This module provides the main entry point for the Asterisk AI Voice Agent
when run as a Python module.
"""

import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

from cli import app

if __name__ == "__main__":
    app()
