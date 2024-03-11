# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    build-essential \
    python3-numpy

RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
    llama-index-llms-azure-openai \
    llama-index-embeddings-huggingface \
    llama-index-llms-ollama \
    pydantic-settings \
    llama-index-readers-web \
    llama-index \
    llama-index-vector-stores-qdrant \
    llama-index-embeddings-huggingface \
    trafilatura \
    qdrant-client \
    ollama

WORKDIR /app

ADD . /app

# Make port 80 available to the world outside this container
EXPOSE 8080

# Run app.py when the container launches
CMD ["uvicorn", "app_backend:app", "--host", "0.0.0.0", "--port", "8080"]