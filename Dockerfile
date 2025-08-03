FROM python:3.11-slim
WORKDIR /app
RUN python3 -m venv .venv
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
RUN pip install --no-cache-dir -e .
ENV PYTHONUNBUFFERED=1
CMD ["python3", "-m", "shop_bot"]