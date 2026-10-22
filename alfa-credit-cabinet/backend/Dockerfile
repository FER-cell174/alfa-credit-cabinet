FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests

EXPOSE 8000
# api: uvicorn app.main:app   |   mocks: uvicorn app.mock_service:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
