FROM python:3.11-slim
WORKDIR /app/project
ENV PYTHONUNBUFFERED=1
COPY . .
RUN pip install --no-cache-dir -e .
CMD ["python3", "-m", "shop_bot"]