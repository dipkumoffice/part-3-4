

export NGINX_NAMESPACE=ingress-nginx
export NGINX_DEPLOYMENT=ingress-nginx-controller
export SLACK_HOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
export PAGERDUTY_ROUTING_KEY=your-routing-key
export EMAIL_FROM=ops@example.com
export EMAIL_TO=admin@example.com
export SMTP_HOST=smtp.example.com
export CHECK_INTERVAL=60
export FAILURE_LIMIT=3

# Dry-run mode (simulate without real restart)
python3 nginx_monitor.py --dry-run

# Live mode (real remediation)
python3 nginx_monitor.py



set -a
source .env
set +a
python3 nginx_monitor.py