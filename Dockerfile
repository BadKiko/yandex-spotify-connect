FROM python:3.11-slim

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    avahi-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy librespot binary from host build context
COPY librespot /app/librespot
RUN chmod +x /app/librespot

# Copy requirements and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ /app/src/
COPY config.yaml /app/

# Expose HTTP streaming port
EXPOSE 8555

# Set Python path and unbuffered output
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "/app/src/app.py"]
