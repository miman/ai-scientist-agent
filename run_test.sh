#!/bin/bash

# Sätt variabler
API_URL="http://localhost:8500/api/ask"
TMP_JSON="./test-prompt.json"

# Texten/prompten vi vill skicka (Helt säker mot citattecken-strul i Bash)
PROMPT_TEXT="Write a complete and robust Node.js function using ES modules (import statements) that leverages the official '@google/genai' SDK to stream responses from the 'gemini-2.5-flash' model. The function must accept a text prompt as an argument, securely handle the API key via environment variables, and implement a resilient retry mechanism with exponential backoff to handle 429 (Rate Limit) or 503 (Service Unavailable) errors gracefully. The streamed chunks must be written directly to the console (process.stdout) in real-time as they arrive."

echo "🔍 Kontrollerar om Hermes API-server är igång på port 8500..."
if ! curl -s --connect-timeout 2 http://localhost:8500/ > /dev/null; then
    echo "❌ Fel: API-servern verkar inte svara. Kör './install.sh' först eller kolla 'podman ps'."
    exit 1
fi

echo "📦 Skapar skottsäker JSON-payload i $TMP_JSON..."
# Vi använder en Here-Doc för att skriva JSON exakt som den ska vara
cat << EOF > "$TMP_JSON"
{
  "prompt": "$PROMPT_TEXT"
}
EOF

echo "🚀 Skickar förfrågan till Hermes Agent Pipeline..."
echo "------------------------------------------------"

# Skicka med curl och spara svaret
RESPONSE=$(curl -s -X POST "$API_URL" \
     -H "Content-Type: application/json" \
     -d @"$TMP_JSON")

# Skriv ut svaret från API:et
echo "$RESPONSE"
echo "------------------------------------------------"

# Ta bort den temporära filen
rm -f "$TMP_JSON"

echo "🎯 Pipeline har startats i bakgrunden!"
echo "👉 Kör nu detta kommando för att följa agenternas arbete i realtid:"
echo "   podman logs -f hermes_api_server"