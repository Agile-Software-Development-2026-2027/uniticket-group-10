FROM upstream

RUN python3 -m ensurepip --upgrade \
    && python3 -m pip install --no-cache-dir \
       django-unical-bootstrap-italia==2.0.1
       
WORKDIR /app/uniticket

COPY extensions/settingslocal.py /app/uniticket/uni_ticket_project/settingslocal.py
COPY extensions /app/uniticket/extensions

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]