FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY run.py .

# Create directory for data with proper permissions
RUN mkdir -p /app/data && chmod 777 /app/data

# Set environment variable for data directory
ENV DATA_DIR=/app/data

CMD ["python", "-u", "run.py"]