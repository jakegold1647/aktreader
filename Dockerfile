FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

RUN mkdir /data
EXPOSE 8780

ENTRYPOINT ["aktreader"]
CMD ["service-serve", "/data", "--container-listen", "--port", "8780"]
