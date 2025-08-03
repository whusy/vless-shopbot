FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN python3 -m venv .venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pip install -e .
COPY src/ /app/src/
ENV PYTHONPATH="${PYTHONPATH}:/app/src"
CMD ["python3", "-m", "shop_bot"]