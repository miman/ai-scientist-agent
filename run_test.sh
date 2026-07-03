#!/bin/bash

# Centrala inställningar
API_URL="http://localhost:8500/api/ask"
TMP_JSON="/tmp/hermes_payload.json"

# 1. Hantera input (Kolla om användaren skickade med en prompt som argument)
if [ -n "$1" ]; then
    # Använd argumentet som skickades med skriptet
    PROMPT_TEXT="$1"
else
    # Interaktiv fallback om inget argument skickades
    echo "💡 Tips: Du kan också köra: $0 \"Din fråga här\""
    echo -n "🤖 Vad vill du att Code Scientist ska lösa? "
    read -r PROMPT_TEXT
fi

# Avbryt om användaren tryckte enter utan att skriva något
if [ -z "$PROMPT_TEXT" ]; then
    echo "❌ Fel: Prompten kan inte vara tom."
    exit 1
fi

# 2. Kontrollera att API-servern är vaken
echo "🔍 Kontrollerar om API-server är igång på port 8500..."
if ! curl -s --connect-timeout 2 http://localhost:8500/api/solutions/1 > /dev/null 2>&1; then
    # Vi kollar mot endpoints som vi vet finns, eller bara bas-URL
    if ! curl -s --connect-timeout 2 http://localhost:8500/ > /dev/null; then
        echo "❌ Fel: API-servern svarar inte. Kör './install.sh' först."
        exit 1
    fi
fi

# 3. Skapa en säker JSON-payload (Hanterar alla typer av citattecken helt automatiskt)
# Vi använder Pythons inbyggda json-modul för att koda strängen helt perfekt
echo "📦 Paketerar prompten till en skottsäker JSON..."
JSON_BODY=$(python3 -c '
import json, sys
print(json.dumps({"prompt": sys.argv[1]}))
' "$PROMPT_TEXT")

echo "$JSON_BODY" > "$TMP_JSON"

echo "🚀 Skickar förfrågan till Agent Pipeline..."
echo "------------------------------------------------"

# 4. Skicka till FastAPI
RESPONSE=$(curl -s -X POST "$API_URL" \
     -H "Content-Type: application/json" \
     -d @"$TMP_JSON")

# Skriv ut svaret från API:et
echo "$RESPONSE"
echo "------------------------------------------------"

# Städa upp den temporära filen
rm -f "$TMP_JSON"

# Load container engine setting
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