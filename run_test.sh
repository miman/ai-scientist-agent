#!/bin/bash

# Centrala inställningar
API_URL="http://localhost:8500/api/ask"
TMP_JSON="/tmp/hermes_payload.json"

# 1. Hantera input
PIPELINE_TYPE="dev_team"

if [ -n "$1" ]; then
    PROMPT_TEXT="$1"
    if [ -n "$2" ]; then
        PIPELINE_TYPE="$2"
    fi
else
    echo "💡 Tips: Du kan köra: $0 \"Din fråga här\" [dev_team|research]"
    echo -n "🤖 Vad vill du att Code Scientist ska lösa? "
    read -r PROMPT_TEXT
    echo -n "⚙️ Vilken pipeline vill du använda? (1: dev_team, 2: research) [1]: "
    read -r PIPE_CHOICE
    if [ "$PIPE_CHOICE" = "2" ] || [ "$PIPE_CHOICE" = "research" ]; then
        PIPELINE_TYPE="research"
    else
        PIPELINE_TYPE="dev_team"
    fi
fi

if [ -z "$PROMPT_TEXT" ]; then
    echo "❌ Fel: Prompten kan inte vara tom."
    exit 1
fi

# 2. Kontrollera att API-servern är vaken
echo "🔍 Kontrollerar om API-server är igång på port 8500..."
if ! curl -s --connect-timeout 2 http://localhost:8500/api/solutions/1 > /dev/null 2>&1; then
    if ! curl -s --connect-timeout 2 http://localhost:8500/ > /dev/null; then
        echo "❌ Fel: API-servern svarar inte. Kör './install.sh' först."
        exit 1
    fi
fi

# 3. Skapa JSON payload
echo "📦 Paketerar prompten och pipeline-typ ($PIPELINE_TYPE)..."
JSON_BODY=$(python3 -c '
import json, sys
print(json.dumps({"prompt": sys.argv[1], "pipeline_type": sys.argv[2]}))
' "$PROMPT_TEXT" "$PIPELINE_TYPE")

echo "$JSON_BODY" > "$TMP_JSON"

echo "🚀 Skickar förfrågan till Agent Pipeline ($PIPELINE_TYPE)..."
echo "------------------------------------------------"

# 4. Skicka till FastAPI
RESPONSE=$(curl -s -X POST "$API_URL" \
     -H "Content-Type: application/json" \
     -d @"$TMP_JSON")

echo "$RESPONSE"
echo "------------------------------------------------"

rm -f "$TMP_JSON"

if [ -f .env ]; then
    CONTAINER_ENGINE=$(grep -E "^CONTAINER_ENGINE=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi
if [ -z "$CONTAINER_ENGINE" ]; then
    if command -v podman &> /dev/null; then
        CONTAINER_ENGINE="podman"
    else
        CONTAINER_ENGINE="docker"
    fi
fi

echo "🎯 Pipeline har startats i bakgrunden!"
echo "👉 Följ agenternas arbete i realtid med:"
echo "   $CONTAINER_ENGINE logs -f ai_scientist_agents"