# Build from the PROJECT ROOT (the folder with site/, books/, content/, tools/):
#   docker build -f tools/tutor/deploy/Dockerfile -t learning-platform .
# --build-arg WITH_RUNNER=0 skips the Python runner env (smaller image); then run the container with TUTOR_RUNNER=off.
FROM python:3.12-slim
ARG WITH_RUNNER=1
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn httpx cryptography uv
COPY site /app/site
COPY content /app/content
COPY books /app/books
COPY tools/tutor /app/tools/tutor
RUN if [ "$WITH_RUNNER" = "1" ]; then uv venv /app/tools/tutor/.runner-venv && uv pip install --python /app/tools/tutor/.runner-venv/bin/python numpy matplotlib sympy; fi
ENV TUTOR_AUTH=on TUTOR_HOST=0.0.0.0 TUTOR_TRUSTED_PROXY=* TUTOR_COOKIE_SECURE=1 TUTOR_DATA_DIR=/data TUTOR_RUNNER=on
VOLUME /data
EXPOSE 8780
CMD ["python", "tools/tutor/server.py"]
