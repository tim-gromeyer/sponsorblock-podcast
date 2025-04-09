FROM python:3.11-slim

# Install FFmpeg and build tools
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-flask \
    python3-requests \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Upgrade pip, install wheel, and install requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Expose port
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
