FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY digital_twin_bridge/ digital_twin_bridge/

# Note: CARLA Python egg (carla package) must be installed separately.
# It is not on PyPI and must be built from the CARLA SDK or installed
# from the .egg/.whl provided with your CARLA distribution.
#
# To use this Dockerfile with CARLA:
#   docker build --build-arg CARLA_EGG=/path/to/carla.egg -t v2x-bridge .
# Or mount the egg at runtime.

EXPOSE 8765

ENTRYPOINT ["python", "-m", "digital_twin_bridge.drive_main"]
