FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_BASE_DIR=/opt/phone-agent

WORKDIR /opt/phone-agent

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg sox ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/opt/phone-agent/src

EXPOSE 8088

CMD ["python", "-m", "uvicorn", "phone_agent.dashboard.app:app", "--host", "0.0.0.0", "--port", "8088"]
