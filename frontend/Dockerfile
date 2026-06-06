FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/progetto-calcio-frontend/package.json frontend/progetto-calcio-frontend/package-lock.json ./
RUN npm ci
COPY frontend/progetto-calcio-frontend/ .
RUN npm run build -- --output-path=dist

FROM nginx:alpine

COPY --from=build /app/dist/browser /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/entrypoint.sh /docker-entrypoint.d/40-inject-env.sh

EXPOSE 80
