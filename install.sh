#!/bin/bash

# Färger för snyggare terminalutskrift
GREEN='\033[032m'
BLUE='\033[034m'
NC='\033[0m' # No Color

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   Konfiguration av Hermes AI Code Scientist   ${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

# Standard-URL för din externa Ollama
DEFAULT_OLLAMA_URL="http://192.168.68.100:11434"
read -p "Ange URL till din Ollama-instans [$DEFAULT_OLLAMA_URL]: " OLLAMA_URL

# Om användaren bara trycker på Enter, använd ditt nätverks-IP
if [ -z "$OLLAMA_URL" ]; then
    OLLAMA_URL=$DEFAULT_OLLAMA_URL
fi

# Skriv URL:en till en .env-fil för compose-miljön
echo "OLLAMA_URL=$OLLAMA_URL" > .env
echo -e "${GREEN}✓ Konfiguration sparad i .env-filen.${NC}"

# Tvinga användning av podman-compose
COMPOSE_CMD="podman-compose"

echo ""
echo -e "${BLUE}🧹 Rensar gamla containrar och cache för att förhindra fel...${NC}"
$COMPOSE_CMD down
podman builder prune -f

echo ""
echo -e "${BLUE}🛠️  Bygger API-image manuellt med podman...${NC}"
# Detta kommando bygger containern direkt och helt säkert utan compose-buggar
podman build -f Dockerfile -t localhost/ai-scientist_hermes_api:latest "$PWD"

echo ""
echo -e "${BLUE}🚀 Startar containrar via Podman...${NC}"
$COMPOSE_CMD up -d

echo ""
echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN} 🎉 Systemet är igång via Podman!${NC}"
echo -e "${GREEN} API:et lyssnar på: http://localhost:8500${NC}"
echo -e "${GREEN} Ollama är kopplad till: $OLLAMA_URL${NC}"
echo -e "${GREEN}===============================================${NC}"