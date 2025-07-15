# Base image with Python and pip
FROM python:3.10-slim

# Set working directory
WORKDIR /opt/ml/code

# Copy app code into container
COPY ecs_handler.py .

# Install required libraries
RUN pip install --no-cache-dir boto3 psycopg2-binary

# Set entry point for ECS
CMD ["python", "ecs_handler.py"]
