FROM python:3.12-slim

# Install LibreOffice and required system packages
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency file first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Render uses the PORT environment variable
CMD gunicorn --bind 0.0.0.0:$PORT app:app