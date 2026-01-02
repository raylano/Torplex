FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script
COPY watcher.py .

# Run the watcher
CMD ["python", "-u", "watcher.py"]
