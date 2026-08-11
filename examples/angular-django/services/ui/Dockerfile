FROM node:22-alpine AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 4200

CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4200", "--allowed-hosts"]


# ---
FROM development AS test

# Angular's default unit-test runner (Karma) needs an actual browser; the
# Chromium package is Alpine's musl-native build, so it works out of the box
# (unlike downloading Puppeteer/Playwright's glibc-based Chromium).
RUN apk add --no-cache chromium
ENV CHROME_BIN=/usr/bin/chromium-browser

# Nothing here runs the suite: `seal ci` runs it inside the container once
# this service is up (services/ui/Tiltfile declares the command). This stage
# exists to carry the browser that runs it -- karma.conf.js and the specs
# are already in the image, from the development stage this builds on.


# ---
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npx ng build --configuration=production


# ---
# There is no long-running "ui" container outside of dev: the built static
# files are copied out by an initContainer (see
# k8s/non-dev/web/nginx/patch-init-containers.yaml) and served by nginx.
FROM alpine:3 AS runtime

COPY --from=build /app/dist/ui/browser /app/static/ui

CMD ["sleep", "infinity"]
