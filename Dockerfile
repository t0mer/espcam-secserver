FROM ubuntu:latest

LABEL maintainer=""

ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8

ENV GREEN_API_INSTANCE_ID ""
ENV GREEN_API_TOKEN ""
ENV TARGET ""
ENV MESSAGE ""


RUN apt update -yqq 

RUN apt install -yqq python3-pip && \
    apt install -yqq libffi-dev && \
    apt install -yqq libssl-dev

RUN  pip3 install --upgrade setuptools --no-cache-dir --break-system-packages

RUN mkdir -p /app/

COPY requirements.txt /tmp

RUN pip3 install --break-system-packages -r /tmp/requirements.txt

COPY app /app

WORKDIR /app

ENTRYPOINT ["/usr/bin/python3", "/app/app.py"]