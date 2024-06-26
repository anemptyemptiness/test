FROM python:3.11-slim-bullseye

# интерпретатор не будет записывать .pyc файлы, чтобы сохранить немного места
ENV PYTHONDONTWRITEBYTECODE 1
# не буферизировать консольный вывод, чтобы любые принты сразу выводились в терминал, а не с запозданием
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements_unix.txt .

RUN pip install -r requirements_unix.txt

RUN apt-get update && apt-get install -y postgresql-client

COPY . .

ENV PYTHONPATH = .

# CMD ["python", "-m", "src"]