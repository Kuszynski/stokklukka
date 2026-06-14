# Użyj lekkiego oficjalnego obrazu Pythona
FROM python:3.11-slim

# Ustaw zmienne środowiskowe dla bezpieczeństwa i wydajności Pythona
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Ustaw katalog roboczy
WORKDIR /workspace

# Kopiuj listę zależności i zainstaluj je (korzystanie z cache Dockera)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiuj kod źródłowy aplikacji
COPY app/ ./app/

# Udostępnij port 80
EXPOSE 80

# Uruchom aplikację za pomocą uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
