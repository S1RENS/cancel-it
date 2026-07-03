FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY .streamlit ./.streamlit

ENV CANCELIT_DB_PATH=/data/cancelit.db
VOLUME /data
EXPOSE 8501

HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]

CMD ["uv", "run", "--frozen", "--no-dev", "streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
