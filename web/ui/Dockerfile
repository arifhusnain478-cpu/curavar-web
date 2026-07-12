# CuraVar UI image: build the Vite bundle with Node, serve it with nginx (which
# also reverse-proxies /api to the API service — see nginx.conf).
#
#   docker build -t curavar-ui web/ui
#
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
