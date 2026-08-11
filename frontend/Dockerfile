# Stage 1: Build the React application
FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy the build output to replace the default nginx contents.
COPY --from=build /app/dist /usr/share/nginx/html

# Copy the custom Nginx configuration file
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
