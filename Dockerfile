FROM python:3.11-slim
WORKDIR /app
RUN python3 -m venv .venv
ENV PATH="/app/.venv/bin:$PATH" 
COPY . .
RUN pip install -e .
CMD ["python3", "-m", "shop_bot"]