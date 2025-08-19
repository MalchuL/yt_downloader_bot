# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install uv
RUN pip install uv

# Copy pyproject.toml
COPY pyproject.toml ./

# Install project dependencies
RUN uv pip install .

# Copy the rest of the application's code
COPY ./src /app/src

# Command to run the application
CMD ["python", "src/main.py"]