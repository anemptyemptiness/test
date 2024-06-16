FROM python:3.11-slim-bullseye

# интерпретатор не будет записывать .pyc файлы, чтобы сохранить немного места
ENV PYTHONDONTWRITEBYTECODE 1
# не буферизировать консольный вывод, чтобы любые принты сразу выводились в терминал, а не с запозданием
ENV PYTHONUNBUFFERED 1

WORKDIR py-aiogram-carousel-tabel-bot/

COPY requirements_unix.txt .

RUN pip install -r /py-aiogram-carousel-tabel-bot/requirements_unix.txt

COPY src /py-aiogram-carousel-tabel-bot/src/

CMD ["python", "-m", "src/main.py"]