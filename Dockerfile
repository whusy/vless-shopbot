FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["python3", "-m", "shop_bot"]