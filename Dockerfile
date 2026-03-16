FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Node.js (for Gemini CLI + Codex CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Copy project
COPY . /app/

# Python dependencies
RUN pip install --no-cache-dir flask flask-cors PyJWT 2>/dev/null || true

# Initialize database
RUN cd /app && python3 scripts/init_db.py

# Make mem executable
RUN chmod +x /app/scripts/mem && \
    ln -sf /app/scripts/mem /usr/local/bin/mem

# Expose dashboard port
EXPOSE 19876

CMD ["bash"]
