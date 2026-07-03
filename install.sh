#!/bin/bash

# Färger för snyggare terminalutskrift
GREEN='\033[032m'
BLUE='\033[034m'
NC='\033[0m' # No Color

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   Konfiguration av AI Code Scientist   ${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

# Hämta befintliga inställningar från .env om den finns
if [ -f .env ]; then
    ENV_OLLAMA=$(grep -E "^OLLAMA_URL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    ENV_SEARXNG=$(grep -E "^SEARXNG_URL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    CONTAINER_ENGINE=$(grep -E "^CONTAINER_ENGINE=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    BASE_MODEL=$(grep -E "^BASE_MODEL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

# Standard-URL för din externa Ollama och SearXNG
DEFAULT_OLLAMA_URL="${ENV_OLLAMA:-http://192.168.68.100:11434}"
DEFAULT_SEARXNG_URL="${ENV_SEARXNG:-http://192.168.68.100:4522}"
DEFAULT_BASE_MODEL="${ENV_BASE_MODEL:-hf.co/unsloth/gemma-4-12b-it-GGUF:UD-Q5_K_XL}"

read -p "Ange URL till din Ollama-instans [$DEFAULT_OLLAMA_URL]: " OLLAMA_URL
if [ -z "$OLLAMA_URL" ]; then
    OLLAMA_URL=$DEFAULT_OLLAMA_URL
fi

read -p "Ange URL till din SearXNG-instans [$DEFAULT_SEARXNG_URL]: " SEARXNG_URL
if [ -z "$SEARXNG_URL" ]; then
    SEARXNG_URL=$DEFAULT_SEARXNG_URL
fi

# Fråga efter container-motor om flaggan saknas i .env
if [ -z "$CONTAINER_ENGINE" ]; then
    if command -v podman &> /dev/null; then
        DETECTED_ENGINE="podman"
    else
        DETECTED_ENGINE="docker"
    fi
    
    echo -e "\nVälj container-motor (docker eller podman):"
    read -p "Använder du docker eller podman? [$DETECTED_ENGINE]: " INPUT_ENGINE
    INPUT_ENGINE=$(echo "$INPUT_ENGINE" | tr '[:upper:]' '[:lower:]')
    if [ -z "$INPUT_ENGINE" ]; then
        CONTAINER_ENGINE=$DETECTED_ENGINE
    else
        CONTAINER_ENGINE=$INPUT_ENGINE
    fi
    
    # Validera att valet är giltigt
    while [[ "$CONTAINER_ENGINE" != "docker" && "$CONTAINER_ENGINE" != "podman" ]]; do
        read -p "Ogiltigt val. Ange 'docker' eller 'podman': " CONTAINER_ENGINE
        CONTAINER_ENGINE=$(echo "$CONTAINER_ENGINE" | tr '[:upper:]' '[:lower:]')
    done
fi

# Skriv URL:erna och container-motorn till en .env-fil för compose-miljön
echo "OLLAMA_URL=$OLLAMA_URL" > .env
echo "SEARXNG_URL=$SEARXNG_URL" >> .env
echo "CONTAINER_ENGINE=$CONTAINER_ENGINE" >> .env
echo "BASE_MODEL=$BASE_MODEL" >> .env
echo -e "${GREEN}✓ Konfiguration sparad i .env-filen.${NC}"

# Ställ in kommandon baserat på vald motor
if [ "$CONTAINER_ENGINE" = "podman" ]; then
    COMPOSE_CMD="podman-compose"
    ENGINE_CMD="podman"
else
    COMPOSE_CMD="docker compose"
    ENGINE_CMD="docker"
fi

echo ""
echo -e "${BLUE}🧹 Rensar gamla containrar och cache för att förhindra fel...${NC}"
$COMPOSE_CMD down
$ENGINE_CMD builder prune -f

echo ""
echo -e "${BLUE}🛠️  Bygger API-image manuellt med $CONTAINER_ENGINE...${NC}"
# Detta kommando bygger containern direkt och helt säkert utan compose-buggar
$ENGINE_CMD build -f Dockerfile -t localhost/ai-scientist_hermes_api:latest "$PWD"

echo ""
echo -e "${BLUE}🚀 Startar containrar via $CONTAINER_ENGINE...${NC}"
$COMPOSE_CMD up -d

echo ""
echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN} 🎉 Systemet är igång via ${CONTAINER_ENGINE}!${NC}"
echo -e "${GREEN} Web UI lyssnar på: http://localhost:8501${NC}"
echo -e "${GREEN} API:et lyssnar på: http://localhost:8500${NC}"
echo -e "${GREEN} Ollama är kopplad till: $OLLAMA_URL${NC}"
echo -e "${GREEN} SearXNG är kopplad till: $SEARXNG_URL${NC}"
echo -e "${GREEN} BASE_MODEL är kopplad till: $BASE_MODEL${NC}"
echo -e "${GREEN}===============================================${NC}"