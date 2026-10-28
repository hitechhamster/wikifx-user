FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
ENV TZ=Asia/Shanghai PYTHONUNBUFFERED=1
COPY legacy/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY legacy/ legacy/
COPY app.py convert.py ./
EXPOSE 8080
CMD ["python","app.py"]
