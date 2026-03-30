FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8080

CMD ["gunicorn", "--bind", ":8080", "--timeout", "180", "main:app"]
