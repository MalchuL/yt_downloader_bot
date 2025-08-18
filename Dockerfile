# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy only the files needed for dependency installation
COPY pyproject.toml poetry.lock* ./

# Install project dependencies
# --no-root is important to not install the project itself, just the dependencies
# The project will be mounted as a volume in docker-compose
RUN poetry install --no-root --no-dev

# Copy the rest of the application's code
COPY ./src /app/src

# Command to run the application
CMD ["poetry", "run", "python", "src/main.py"]
