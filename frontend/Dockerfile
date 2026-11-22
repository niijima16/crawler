FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 検査（Biome・型・テスト）。`docker build --target check ./frontend` で単独実行できる。
FROM deps AS check
COPY . .
RUN npx biome ci . && npx tsc --noEmit && npx vitest run

FROM check AS build
RUN npx vite build

FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
