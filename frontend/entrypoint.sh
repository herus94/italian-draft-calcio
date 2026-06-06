#!/bin/sh
if [ -n "$API_URL" ]; then
  sed -i "s|<app-root>|<script>window.__API_URL__='${API_URL}'</script><app-root>|" /usr/share/nginx/html/index.html
fi
