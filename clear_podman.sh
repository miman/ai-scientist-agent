#!/bin/bash

# This script is used if the code changes aren't updated in the container for some reason.
# Run this script to clear the cache and rebuild the container.

# Hämta inställningar från .env om den finns
if [ -f .env ]; then
    CONTAINER_ENGINE=$(grep -E "^CONTAINER_ENGINE=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

# Fallback om CONTAINER_ENGINE saknas
if [ -z "$CONTAINER_ENGINE" ]; then
    if command -v podman &> /dev/null; then
        CONTAINER_ENGINE="podman"
    else
        CONTAINER_ENGINE="docker"
    fi
fi

if [ "$CONTAINER_ENGINE" = "podman" ]; then
    COMPOSE_CMD="podman-compose"
    ENGINE_CMD="podman"
else
    COMPOSE_CMD="docker compose"
    ENGINE_CMD="docker"
fi

# 1. Stoppa och ta bort de gamla containrarna helt
$COMPOSE_CMD down --volumes  # Tar även bort eventuella hängda interna volymer

# 2. Kör en hård ombyggnad av imagen:
$ENGINE_CMD build --no-cache -f Dockerfile -t localhost/ai-scientist_hermes_api:latest .

# 3. Dräpa eventuella dolda Python-cachefiler i din lokala mapp:
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null

# 4. Starta upp allt igen via ditt skript:
./install.sh