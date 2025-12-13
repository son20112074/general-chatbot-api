FROM python:3.12.10

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# # Copy the project files
# COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD uvicorn server_dev:app --host 0.0.0.0 --port 8000 --workers 2