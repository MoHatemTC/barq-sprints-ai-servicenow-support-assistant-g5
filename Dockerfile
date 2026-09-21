# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install CPU-only PyTorch first (kept separate so it's cached independently)
RUN pip install --no-cache-dir \
    torch \
    --index-url https://download.pytorch.org/whl/cpu

# Copy the whole project (pyproject.toml needs the rest of the source
# to install the project itself, e.g. package folders referenced in it)
COPY . .

# Install the project and its dependencies from pyproject.toml
RUN pip install --no-cache-dir .

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]