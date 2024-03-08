# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm
#FROM nvidia/cuda:12.0.1-runtime-ubuntu22.04

RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
    gradio \
    requests

WORKDIR /app
#ENV HF_HOME=${WORKDIR}/.cache

# Add the current directory contents into the container at /app
ADD . /app
    

# Make port 80 available to the world outside this container
EXPOSE 8088

# Run app.py when the container launches
CMD ["python3", "app_frontend.py"]