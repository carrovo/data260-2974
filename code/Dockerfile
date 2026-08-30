# Use a lightweight Nginx web server.
FROM nginx:alpine

# Remove the default Nginx website.
RUN rm -rf /usr/share/nginx/html/*

# Copy the rental listing website into the Nginx web directory.
COPY web_application/ /usr/share/nginx/html/

# Document that the container serves HTTP on port 80.
EXPOSE 80

# Keep Nginx running in the foreground.
CMD ["nginx", "-g", "daemon off;"]