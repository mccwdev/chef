FROM python:3.6-alpine

RUN adduser -D chef

WORKDIR /home/chef

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn pymysql

COPY app app
COPY migrations migrations
COPY chef.py config.py boot.sh ./
RUN chmod a+x boot.sh

ENV FLASK_APP chef.py

RUN chown -R chef:chef ./
USER chef

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]
