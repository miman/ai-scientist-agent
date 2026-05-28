För att verkligen sätta din Hermes AI Code Scientist på prov och se vad din 5-agent-pipeline går för, vill du ge den en uppgift som tvingar alla agenter att arbeta hårt, men som ändå inte är så gigantisk att din GPU storknar.

En perfekt testfråga ska uppfylla följande kriterier:

    Trigga Agent 1 (Sök): Uppgiften måste kräva extern, specifik eller relativt ny API-kunskap så att sökagenten väljer "JA" istället for "NEJ".

    Utmana Agent 3 (Expert): Det ska krävas en kombination av logik, asynkron hantering och felhantering (inte bara en standardkopierad funktion).

    Sätta press på Agent 4 (Critic): Koden ska ha dolda fallgropar där Critic-agenten faktiskt tvingas upptäcka fel, underkänna koden och skicka tillbaka den i korrigeringsloopen (så att du får se loop-arkitekturen i praktiken!).

🔥 Det ultimata test-promptet

Kopiera och skicka in följande prompt till din /api/ask-ändpunkt:

```JSON
{
  "prompt": "Skriv en komplett och robust Node.js-funktion (med ES-moduler/import) som använder det officiella biblioteket '@google/genai' för att strömma (stream) ett svar från modellen 'gemini-2.5-flash'. Funktionen måste ta emot en text-prompt, hantera API-nyckeln säkert via miljövariabler, och ha en inbyggd retry-mekanism med exponential backoff om Google kastar ett 429 (Rate Limit) eller 503-fel. Funktionen ska skriva ut strömmen direkt till konsolen (process.stdout) allteftersom tecknen kommer."
}
```

🕵️‍♂️ Vad som kommer hända under huven (och vad du ska hålla utkik efter i loggarna!)

När du kör detta och bevakar din terminal med podman logs -f hermes_api_server, kommer du att få se hela din arkitektur briljera steg för steg:
1. Agent 1 (Sökagenten) gör Triage

    Förväntat beteende: Google släppte nyligen sitt helt nya och uppdaterade SDK (@google/genai) som ersätter det gamla @google/generative-ai. Eftersom qwen3.5 vet att detta är ett specifikt externt bibliotek, bör den fatta ett kognitivt beslut att söka.

    I loggen: Du kommer se 🌐 [Agent 1: Sök] Agenten beslutade att söka! Söksträng: '@google/genai nodejs stream gemini-2.5-flash'.

2. Agent 2 & ChromaDB sparar kontexten

    Förväntat beteende: Sökresultaten från DuckDuckGo (som innehåller den absolut senaste syntaxen för Googles nya SDK) rensas av Processor-agenten och sparas i ChromaDB (blixtsnabbt tack vare vår FakeEmbeddingFunction på klientsidan!).

3. Agent 3 (Expert) skriver koden

    Förväntat beteende: Expert-agenten läser dokumentationen från ChromaDB och försöker pussla ihop Node.js-koden, konfigurera GoogleGenAI-klienten, sätta upp streaming-loopen och koda logiken för exponential backoff.

4. Det magiska ögonblicket: Agent 4 (Critic) slår bakut! ⚖️

Det här är den absolut roligaste delen att titta på i ett agent-system. Att skriva asynkron strömning (t.ex. for await (const chunk of response.stream)) tillsammans med en komplex retry-loop för 429-fel är ökänt svårt för en LLM att få 100 % rätt på första försöket.

    Förväntat beteende: Expert-agenten kommer troligtvis att missa att stänga strömmen korrekt vid ett fel, eller råka blanda ihop syntaxen mellan det gamla och nya Google-biblioteket.

    I loggen: Critic-agenten kommer att läsa igenom koden med lupp och upptäcka detta. Du kommer se:
    STATUS: UNDERKÄND - Utvecklaren har missat att fånga fel inuti själva asynkrona iteratorn...

    Loopen triggas: Systemet skickar tillbaka feedbacken. Expert-agenten tar emot kritiken, rättar till buggen och genererar version 2. Det är här din failsafe-spärr på max 10 loopar skyddar din GPU om de skulle börja argumentera!

5. Agent 5 (Arkiv) stänger säcken

    Förväntat beteende: När Critic-agenten äntligen ser en perfekt kodrad som hanterar imports, strömmar rätt, använder rätt SDK och har en felfri backoff-logik skriver den STATUS: GODKÄND. Arkiveringsagenten sparar ner koden i din SQLite-databas i den säkra Docker-volymen.

📊 Hur du hämtar resultatet när det är klart

När loggarna har tystnat och du ser 🎉 Klart! Sparat med ID: X, kan du enkelt hämta ut den färdiga, hårdtestade och granskade koden genom att göra en GET-request till ditt API:
Bash

curl http://localhost:8500/api/solutions/X

(Ersätt X med det ID som din arkiv-agent skrev ut).

Detta test visar verkligen skillnaden mellan att bara ställa en fråga till en vanlig chatt-bot (som garanterat hade hallucinerat ihop en blandning av Googles gamla och nya API-syntax) och din autonoma pipeline som faktiskt gör research, upptäcker sina egna misstag och korrigerar dem innan du ens hinner se koden!