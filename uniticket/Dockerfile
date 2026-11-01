# Node è necessario solo durante la build; non viene incluso nel runtime Django.
FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY package.json package-lock.json vite.config.js ./
RUN npm ci
COPY extensions/assistant/static ./extensions/assistant/static
RUN npm run build

# We will work on the latest version available
# docker buildx imagetools inspect ghcr.io/universitadellacalabria/uniticket:latest (sha256:b010d9000f16942ae207f19a01bed00746c76a0c6074db17588118a1d34e4771)
FROM ghcr.io/universitadellacalabria/uniticket@sha256:b010d9000f16942ae207f19a01bed00746c76a0c6074db17588118a1d34e4771

RUN python3 -m ensurepip --upgrade \
    && python3 -m pip install --no-cache-dir \
       django-unical-bootstrap-italia==2.0.1
       

WORKDIR /app/uniticket

COPY config/settings.py /app/uniticket/uni_ticket_project/settings.py
COPY extensions /extensions
# Gli asset restano accessibili anche con /extensions montato in sola lettura da Compose.
COPY --from=frontend /frontend/frontend-dist /frontend-dist

ENV PYTHONPATH=/extensions:/app/uniticket \
    DJANGO_SETTINGS_MODULE=uni_ticket_project.settings

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]