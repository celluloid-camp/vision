#!/usr/bin/env python3
"""
Command-line interface for video detection
This is a wrapper script that calls the detection module from the app package.
"""
import sys
from app.detection.detect_objects import main

if __name__ == "__main__":
    sys.exit(main())
