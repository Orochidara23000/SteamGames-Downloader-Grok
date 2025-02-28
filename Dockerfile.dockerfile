FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY app.py requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PORT=7860

# Create necessary directories
RUN mkdir -p ./downloads ./steamcmd

# Expose the port
EXPOSE 7860

# Command to run the application
CMD ["python", "app.py"]