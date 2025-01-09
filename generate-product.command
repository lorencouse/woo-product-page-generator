#!/bin/bash
cd "$(dirname "$0")"
python3 generate-product.py
read -p "Press Enter to exit..."
