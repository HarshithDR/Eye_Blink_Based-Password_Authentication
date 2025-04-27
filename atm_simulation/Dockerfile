# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Set DEBIAN_FRONTEND to noninteractive to avoid prompts during apt-get install
    DEBIAN_FRONTEND=noninteractive \
    # Set the working directory in the container
    WORKDIR=/app

# Install system dependencies required by OpenCV, dlib, face_recognition
# - build-essential: Provides C/C++ compilers (like g++)
# - cmake: Required by dlib
# - pkg-config: Helper for finding libraries
# - libjpeg-dev, libpng-dev, libtiff-dev: Image format support for OpenCV
# - libavcodec-dev, libavformat-dev, libswscale-dev: Video format support (FFmpeg)
# - libv4l-dev: Video for Linux (webcam access)
# - libgtk-3-dev: GUI library (often needed by OpenCV builds, even if not used directly)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libgtk-3-dev \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# Use --no-cache-dir to reduce image size
# dlib and face_recognition installation might take a while here!
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# Ensure shape predictor is copied!
COPY . .

# Make sure the dlib shape predictor model is executable/readable if needed (usually fine)
# RUN chmod +r shape_predictor_68_face_landmarks.dat

# Expose the port the app runs on
EXPOSE 5000

# Define the command to run the application
# Using eventlet's server directly as in your app.py
CMD ["python", "app.py"]
# Alternatively, using gunicorn (might need adjustments in app.py if __main__ guard isn't present)
# CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]