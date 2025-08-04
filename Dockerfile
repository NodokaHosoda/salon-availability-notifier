FROM mcr.microsoft.com/playwright/python:v1.43.1-jammy

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8080

CMD ["python", "main.py"]