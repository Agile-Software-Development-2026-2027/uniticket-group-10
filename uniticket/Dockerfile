FROM node:22-bookworm-slim AS widget-build

WORKDIR /build/widget
COPY widget/package.json widget/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY widget/ ./
RUN npm run build:widget

FROM upstream

RUN python3 -m ensurepip --upgrade \
    && python3 -m pip install --no-cache-dir \
       django-unical-bootstrap-italia==2.0.1 \
       qdrant-client==1.14.3 \
       httpx==0.28.1

WORKDIR /app/uniticket

COPY uniticket/extensions /extensions
COPY --from=widget-build /build/widget/dist-widget/ /extensions/assistant/static/chat/vendor/

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
