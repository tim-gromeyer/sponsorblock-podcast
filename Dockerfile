FROM python:alpine

# Install FFmpeg and build dependencies
RUN apk add --no-cache ffmpeg

# Set working directory
WORKDIR /app

# Create required directories
RUN mkdir -p episodes cache

# Copy requirements file
COPY requirements.txt .

# Install requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py models.py ./

# Expose port
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]