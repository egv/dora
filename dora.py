#!/usr/bin/env python3
"""Convenience script to run Dora."""

import os
import sys

if __name__ == "__main__":
    # Add the parent directory to the Python path so we can import the package
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dora.__main__ import main
    main()