#!/bin/sh
set -eu

release=/opt/mneme-api-releases/0.3.0-6cd9420
unit=/etc/systemd/system/mneme-api.service

install -m 0644 "$release/mneme-api.service.previous" "$unit"
systemctl daemon-reload
systemctl restart mneme-api

for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS --max-time 3 http://127.0.0.1:8001/health; then
        printf '\n'
        systemctl --no-pager --full status mneme-api
        exit 0
    fi
    sleep 2
done

systemctl --no-pager --full status mneme-api
exit 1
