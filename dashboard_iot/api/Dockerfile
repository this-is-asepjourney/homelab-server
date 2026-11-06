FROM python:3.11-slim

# Set working directory to /app
# The 'api' package will live at /app/api/
WORKDIR /app

# Copy requirements and install dependencies first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into /app/api/ so Python can find 'api' as a package
# uvicorn will run as: uvicorn api.main:app (from /app working dir)
COPY . ./api/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
