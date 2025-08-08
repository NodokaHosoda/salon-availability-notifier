FROM mcr.microsoft.com/playwright/python:latest

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8080

CMD ["gunicorn", "--bind", ":8080", "main:app"]
