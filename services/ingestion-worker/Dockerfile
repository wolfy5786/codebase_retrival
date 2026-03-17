FROM python:3.11-slim-bookworm

# Install OpenJDK 17 for jdtls (Eclipse JDT Language Server)
# Note: openjdk-17 was removed from Debian Trixie (testing); Bookworm still has it
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Run as module so package imports work
CMD ["python", "-m", "src.main"]
