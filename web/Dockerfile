# =============================================================================
#  MetriX web PWA
#  Built once, served as static assets by nginx. The API is a separate service,
#  so the image carries no server runtime.
# =============================================================================
FROM node:20-alpine AS build

WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund

# The shared TypeScript layer lives outside web/, so it must be present for
# the type build to resolve @shared/*.
COPY packages/shared /app/packages/shared
COPY web/ ./

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/web/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
