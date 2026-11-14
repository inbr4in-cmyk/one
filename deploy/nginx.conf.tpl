# One English — its own server block; nothing else on this server is changed.
server {
    listen 80;
    server_name __DOMAIN__;
    # 25 MB upload limit in the API (OE_MAX_UPLOAD_MB) + multipart overhead.
    client_max_body_size 27m;

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
        # The API sends its own security headers; don't send them twice.
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Strict-Transport-Security;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header Referrer-Policy no-referrer always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    }
    # An add_header inside a location replaces the server-level ones, so the security headers are repeated here.
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable" always;
        add_header Content-Security-Policy $oe_csp always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy strict-origin-when-cross-origin always;
        add_header X-Frame-Options DENY always;
        try_files $uri =404;
    }
    # PWA manifest: the right type so phones offer «Install app».
    location = /manifest.webmanifest { default_type application/manifest+json; try_files $uri =404; }
    location / { try_files $uri $uri/ /index.html; }

    # QA H-6. Scripts only from this site (no inline scripts); fonts from Google Fonts; images may be https
    # (Instagram media in the inbox); the API, WebSocket and files are same-origin.
    add_header Content-Security-Policy $oe_csp always;
    # Browsers ignore HSTS on plain http; it takes effect once certbot has switched the site to https.
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header X-Frame-Options DENY always;
    add_header Permissions-Policy "camera=(), microphone=(self), geolocation=()" always;
}

map $http_upgrade $connection_upgrade_oe { default upgrade; '' close; }
map $host $oe_csp {
    default "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self' wss://__DOMAIN__; worker-src 'self' blob:; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
}
