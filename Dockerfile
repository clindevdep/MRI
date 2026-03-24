FROM node:22-bookworm-slim

# System deps for Playwright Chromium + Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    curl ca-certificates \
    # Playwright Chromium dependencies
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Node.js dependencies
COPY package.json ./
RUN npm install --production

# Install Playwright Chromium only
RUN npx playwright install chromium && npx playwright install-deps chromium

# Python dependencies
COPY pyproject.toml ./
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python \
    streamlit pandas openpyxl pypdf lxml pdfplumber

# Copy application code
COPY scripts/ ./scripts/
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV NODE_ENV=production

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

EXPOSE 8502

# Initial CMD — will be updated to Streamlit in Stage 2
CMD ["python3", "-c", "import http.server; s=http.server.HTTPServer(('0.0.0.0',8502),http.server.SimpleHTTPRequestHandler); print('MRI backend ready on :8502'); s.serve_forever()"]
