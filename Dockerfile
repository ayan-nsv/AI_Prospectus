FROM python:3.11-slim

# Set platform arguments for multi-architecture support
ARG TARGETARCH

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        curl \
        gnupg \
        unzip \
        libnss3 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libpangocairo-1.0-0 \
        libasound2 \
        libx11-xcb1 \
        fonts-liberation \
        libappindicator3-1 \
        xdg-utils && \
    \
    # --- Install Google Chrome / Chromium depending on arch ---
    if [ "$TARGETARCH" = "amd64" ]; then \
        wget -q https://dl.google.com/linux/linux_signing_key.pub \
            -O /usr/share/keyrings/google-linux-signing-key.pub && \
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.pub] https://dl.google.com/linux/chrome/deb/ stable main" \
            > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && \
        apt-get install -y google-chrome-stable; \
    else \
        apt-get install -y chromium chromium-driver; \
    fi && \
    \
    # Cleanup
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 appuser


# Switch to non-root user
USER appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

# Set Chrome/Chromium binary path based on architecture
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMIUM_BIN=/usr/bin/chromium

CMD ["python", "run.py"]