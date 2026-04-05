FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.toml* ./
COPY packages/ ./packages/
COPY services/agent_api/ ./services/agent_api/

RUN uv sync --package agent_api

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "agent_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
