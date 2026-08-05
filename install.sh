#!/bin/bash

# Colors for terminal output
GREEN='\033[032m'
BLUE='\033[034m'
NC='\033[0m' # No Color

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   AI Code Scientist — Configuration   ${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

# Load existing settings from .env if it exists
if [ -f .env ]; then
    ENV_OLLAMA=$(grep -E "^OLLAMA_URL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    ENV_SEARXNG=$(grep -E "^SEARXNG_URL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    CONTAINER_ENGINE=$(grep -E "^CONTAINER_ENGINE=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    BASE_MODEL=$(grep -E "^BASE_MODEL=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

# Default URLs for Ollama and SearXNG
DEFAULT_OLLAMA_URL="${ENV_OLLAMA:-http://192.168.68.100:11434}"
DEFAULT_SEARXNG_URL="${ENV_SEARXNG:-http://192.168.68.100:4522}"
DEFAULT_BASE_MODEL="${ENV_BASE_MODEL:-hf.co/unsloth/gemma-4-12b-it-GGUF:UD-Q5_K_XL}"

# Prompt for Ollama URL if not already set in .env
if [ -z "$ENV_OLLAMA" ]; then
    read -p "Enter the URL of your Ollama instance [$DEFAULT_OLLAMA_URL]: " OLLAMA_URL
    if [ -z "$OLLAMA_URL" ]; then
        OLLAMA_URL=$DEFAULT_OLLAMA_URL
    fi
else
    OLLAMA_URL=$ENV_OLLAMA
fi

# Ask which search engine to use if SEARXNG_URL is not already set
if [ -z "$ENV_SEARXNG" ]; then
    echo ""
    echo -e "Select search engine for web research:"
    echo -e "  1) SearXNG (self-hosted)"
    echo -e "  2) DuckDuckGo (no configuration needed)"
    read -p "Your choice [1/2, default=2]: " SEARCH_CHOICE

    if [ "$SEARCH_CHOICE" = "1" ]; then
        read -p "Enter the URL of your SearXNG instance [$DEFAULT_SEARXNG_URL]: " SEARXNG_URL
        if [ -z "$SEARXNG_URL" ]; then
            SEARXNG_URL=$DEFAULT_SEARXNG_URL
        fi
    else
        SEARXNG_URL=""
        echo -e "${GREEN}✓ DuckDuckGo selected — no SEARXNG_URL needed.${NC}"
    fi
else
    read -p "Enter the URL of your SearXNG instance [$DEFAULT_SEARXNG_URL]: " SEARXNG_URL
    if [ -z "$SEARXNG_URL" ]; then
        SEARXNG_URL=$DEFAULT_SEARXNG_URL
    fi
fi

# Ask for container engine if not set in .env
if [ -z "$CONTAINER_ENGINE" ]; then
    if command -v podman &> /dev/null; then
        DETECTED_ENGINE="podman"
    else
        DETECTED_ENGINE="docker"
    fi
    
    echo -e "\nSelect container engine (docker or podman):"
    read -p "Are you using docker or podman? [$DETECTED_ENGINE]: " INPUT_ENGINE
    INPUT_ENGINE=$(echo "$INPUT_ENGINE" | tr '[:upper:]' '[:lower:]')
    if [ -z "$INPUT_ENGINE" ]; then
        CONTAINER_ENGINE=$DETECTED_ENGINE
    else
        CONTAINER_ENGINE=$INPUT_ENGINE
    fi
    
    # Validate the choice
    while [[ "$CONTAINER_ENGINE" != "docker" && "$CONTAINER_ENGINE" != "podman" ]]; do
        read -p "Invalid choice. Enter 'docker' or 'podman': " CONTAINER_ENGINE
        CONTAINER_ENGINE=$(echo "$CONTAINER_ENGINE" | tr '[:upper:]' '[:lower:]')
    done
fi

# Write configuration to .env file
echo "OLLAMA_URL=$OLLAMA_URL" > .env
if [ -n "$SEARXNG_URL" ]; then
    echo "SEARXNG_URL=$SEARXNG_URL" >> .env
fi
echo "CONTAINER_ENGINE=$CONTAINER_ENGINE" >> .env
echo "BASE_MODEL=$BASE_MODEL" >> .env
echo -e "${GREEN}✓ Configuration saved to .env file.${NC}"

# Set compose command based on selected engine
if [ "$CONTAINER_ENGINE" = "podman" ]; then
    # podman compose (subcommand) is built-in since Podman 4.1+
    # podman-compose (hyphenated) is an older separate Python package
    if podman compose version &> /dev/null; then
        COMPOSE_CMD="podman compose"
    elif command -v podman-compose &> /dev/null; then
        COMPOSE_CMD="podman-compose"
    else
        echo -e "⚠️  Neither 'podman compose' nor 'podman-compose' was found."
        echo -e "   Install with: pip install podman-compose"
        echo -e "   Or upgrade Podman to 4.1+ for the built-in 'podman compose' subcommand."
        exit 1
    fi
    ENGINE_CMD="podman"
else
    COMPOSE_CMD="docker compose"
    ENGINE_CMD="docker"
fi

echo ""
echo -e "${BLUE}🧹 Cleaning up old containers and cache to prevent errors...${NC}"
$COMPOSE_CMD down
$ENGINE_CMD builder prune -f

echo ""
echo -e "${BLUE}🛠️  Building API image with $CONTAINER_ENGINE...${NC}"
$ENGINE_CMD build -f Dockerfile -t localhost/ai-scientist_hermes_api:latest "$PWD"

echo ""
echo -e "${BLUE}🚀 Starting containers via $CONTAINER_ENGINE...${NC}"
$COMPOSE_CMD up -d

echo ""
echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN} 🎉 System is up and running via ${CONTAINER_ENGINE}!${NC}"
echo -e "${GREEN} Web UI listening on: http://localhost:8501${NC}"
echo -e "${GREEN} API listening on:    http://localhost:8500${NC}"
echo -e "${GREEN} Ollama connected to: $OLLAMA_URL${NC}"
if [ -n "$SEARXNG_URL" ]; then
    echo -e "${GREEN} Search engine: SearXNG ($SEARXNG_URL)${NC}"
else
    echo -e "${GREEN} Search engine: DuckDuckGo (no external service)${NC}"
fi
echo -e "${GREEN} BASE_MODEL: $BASE_MODEL${NC}"
echo -e "${GREEN}===============================================${NC}"
