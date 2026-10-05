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

# R + PowerTOST for CVw screening / bioequivalence sample size.
#
# The compiled dependencies come from Debian (r-cran-*): they are prebuilt
# against this image's R 4.2.2, so the image still needs NO gfortran / C++
# toolchain and the build stays fast. r-base-core (not full r-base) avoids
# pulling the build toolchain via recommends.
#
# Do NOT go back to installing these from Posit Package Manager: PPM no longer
# publishes bookworm/R-4.2 *binaries* (every snapshot now resolves to
# src/contrib), so mvtnorm (Fortran) and cubature/Rcpp (C++) fall back to a
# source build and fail in this compiler-less image. That is exactly how the
# 2026-08-04 build silently lost mvtnorm + cubature and left PowerTOST
# unloadable — Sample Size / CVw screening was dead until 2026-10-05 — because
# install.packages() only *warns* on a failed package. PowerTOST itself is
# NeedsCompilation=no, so it still installs cleanly from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    r-base-core r-cran-mvtnorm r-cran-cubature r-cran-rcpp r-cran-jsonlite \
    && rm -rf /var/lib/apt/lists/*
# The assertion makes a partial/failed install fail the build instead of
# shipping an image whose Sample Size tab is broken.
RUN Rscript -e 'options(HTTPUserAgent=sprintf("R/%s R (%s)", getRversion(), paste(getRversion(), R.version["platform"], R.version["arch"], R.version["os"])), repos=c(PPM="https://packagemanager.posit.co/cran/__linux__/bookworm/latest")); install.packages("PowerTOST")' \
    && Rscript -e 'pkgs <- c("jsonlite","mvtnorm","cubature","PowerTOST"); missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly=TRUE)]; if (length(missing)) stop("R packages failed to install: ", paste(missing, collapse=", ")); library(PowerTOST); cat("R deps OK — PowerTOST", as.character(packageVersion("PowerTOST")), "CVfromCI:", CVfromCI(lower=0.9, upper=1.11, n=20, design="2x2"), "\n")'

# Copy application code
COPY scripts/ ./scripts/
COPY src/ ./src/
COPY .streamlit/ ./.streamlit/

ENV PATH="/app/.venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV NODE_ENV=production
ENV PYTHONPATH=/app/src

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

EXPOSE 8502

CMD ["streamlit", "run", "/app/src/mri_app/Home.py", "--server.port=8502", "--server.address=0.0.0.0"]
