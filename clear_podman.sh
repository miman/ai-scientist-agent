#!/bin/bash

# This script is used if the code changes isn't updated in podman for some reason.
# Run this script to clear the podman cache and rebuild the container.

# 1. Stoppa och ta bort de gamla containrarna helt
podman compose down --volumes  # Tar även bort eventuella hängda interna volymer

# 2. Kör din installation med flaggan --no-cache om ditt install-skript stöder det, 
# eller kör en hård ombyggnad av Podman-imagen:
podman build --no-cache -t hermes_api_server .

# 3. Dräpa eventuella dolda Python-cachefiler i din lokala mapp:
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null

# 4. Starta upp allt igen via ditt skript:
./install.sh