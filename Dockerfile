FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system aegis && adduser --system --ingroup aegis aegis

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=aegis:aegis . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER aegis

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
