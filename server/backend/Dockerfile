FROM python:3.11-slim

WORKDIR /app
COPY db/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY db ./db
COPY shared ./shared
COPY catalog ./catalog

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "db.main:app", "--host", "0.0.0.0", "--port", "8000"]
