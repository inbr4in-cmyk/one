# One English — its own server block; nothing else on this server is changed.
server {
    listen 80;
    server_name __DOMAIN__;
    client_max_body_size 25m;

    root /opt/one-english/web;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:__PORT__;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade_oe;
        proxy_read_timeout 120s;
    }
    location /assets/ { expires 30d; add_header Cache-Control "public, immutable"; try_files $uri =404; }
    location / { try_files $uri $uri/ /index.html; }

    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header X-Frame-Options DENY always;
}

map $http_upgrade $connection_upgrade_oe { default upgrade; '' close; }
