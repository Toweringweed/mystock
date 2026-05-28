FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crawler.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "crawler.py"]
