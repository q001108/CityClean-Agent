FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY knowledge_base/demo/fixtures/vehicle_breakdown_replan.json knowledge_base/demo/fixtures/complaint_urgent_v2.json /knowledge_base/demo/fixtures/
ARG VITE_TIANDITU_KEY=
ENV VITE_TIANDITU_KEY=${VITE_TIANDITU_KEY}
RUN npm run build

FROM nginx:1.30.5-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
