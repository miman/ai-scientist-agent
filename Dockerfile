# Använd en officiell och lättviktig Python-image
FROM docker.io/library/python:3.11-slim

# Sätt arbetskatalogen inuti containern
WORKDIR /app

# Installera systemberoenden inkl. docker CLI för container isolation & testning
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Kopiera först requirements.txt för att utnyttja Podmans/Dockers byggcache optimalt
COPY requirements.txt .

# Installera alla Python-paket från requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Kopiera resten av projektfilerna (app.py m.m.) till containern
COPY . .

# Exponera porten som FastAPI (Uvicorn) körs på
EXPOSE 8500

# Starta FastAPI-appen när containern drar igång
CMD ["python", "app.py"]