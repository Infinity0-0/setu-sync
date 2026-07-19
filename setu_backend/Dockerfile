# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install Node.js (required for whiteboard sync server)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed Python packages specified in requirements.txt and gunicorn
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy the rest of the application code
COPY . .

# Install Node.js dependencies for the whiteboard sync server and build React app
# Suppress errors if whiteboard/package.json doesn't exist
RUN if [ -f "whiteboard/package.json" ]; then cd whiteboard && npm install && npm run build; fi

# Expose the port the app runs on
EXPOSE 8000
# Also expose the internal Node.js sync server port just in case
EXPOSE 5858

# Command to run the application using Gunicorn with Uvicorn workers for production
# PORT is provided dynamically by Render
CMD ["sh", "-c", "gunicorn main:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}"]
