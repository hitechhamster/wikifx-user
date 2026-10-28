FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY legacy/ legacy/
COPY app.py .
COPY material_policy.py .
COPY news_policy.py .
COPY fact_check.py .
COPY fact_numbers.py .
COPY editorial_checks.py .
COPY ai_audit.py .
COPY writer-prompt.md .
COPY test_writer.py .
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python","app.py"]
