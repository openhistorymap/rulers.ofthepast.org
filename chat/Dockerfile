# Avatar chat microservice (stub). FastAPI on python:3.9, OHM convention.
FROM python:3.9

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# The harvested data the persona builder reads. In production, mount the repo's
# data/ at /data instead of copying, so a re-harvest doesn't need a rebuild:
#   docker run -e PAST_DATA_DIR=/data -v "$PWD/../data":/data:ro -p 8000:8000 otp-chat
ENV PAST_DATA_DIR=/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
