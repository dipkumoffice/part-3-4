#!/usr/bin/env python3

import os
import time
import logging
import argparse
import requests
import smtplib
from email.message import EmailMessage
from kubernetes import client, config

# --- Config ---
NAMESPACE = os.getenv("NGINX_NAMESPACE", "ingress-nginx")
DEPLOYMENT_NAME = os.getenv("NGINX_DEPLOYMENT", "ingress-nginx-controller")
SLACK_HOOK_URL = os.getenv("SLACK_HOOK_URL")
PAGERDUTY_ROUTING_KEY = os.getenv("PAGERDUTY_ROUTING_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
CHECK_EVERY = int(os.getenv("CHECK_INTERVAL", 60))
FAILURE_THRESHOLD = int(os.getenv("FAILURE_LIMIT", 3))

# --- Logging ---
logging.basicConfig(
    filename="nginx_health_monitor.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --- Notification Functions ---


def notify_slack(message):
    if not SLACK_HOOK_URL:
        logging.warning("Slack URL not set, skipping Slack notification")
        return
    try:
        requests.post(SLACK_HOOK_URL, json={"text": message})
    except Exception as err:
        logging.error(f"Slack error: {err}")


def notify_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_TO, SMTP_HOST]):
        logging.warning("Email config incomplete, skipping email")
        return
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST) as smtp:
            smtp.send_message(msg)
    except Exception as err:
        logging.error(f"Email error: {err}")


def notify_pagerduty(message):
    if not PAGERDUTY_ROUTING_KEY:
        logging.warning("PagerDuty key not set, skipping notification")
        return
    try:
        payload = {
            "routing_key": PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger",
            "payload": {
                "summary": message,
                "severity": "critical",
                "source": "nginx-ingress-monitor"
            }
        }
        requests.post("https://events.pagerduty.com/v2/enqueue", json=payload)
    except Exception as err:
        logging.error(f"PagerDuty error: {err}")


def notify_all_channels(message):
    logging.info(f"Alert: {message}")
    notify_slack(message)
    notify_email("NGINX Health Alert", message)
    notify_pagerduty(message)

# --- Health Check & Recovery ---


def get_unhealthy_pods():
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(
        namespace=NAMESPACE, label_selector="app.kubernetes.io/component=controller")
    problem_pods = []
    for pod in pods.items:
        if pod.status.container_statuses:
            for c in pod.status.container_statuses:
                if not c.ready:
                    problem_pods.append(pod.metadata.name)
    return problem_pods


def restart_nginx_controller(dry_run):
    msg = f"[Self-Heal] Restarting deployment {DEPLOYMENT_NAME} in namespace {NAMESPACE}"
    logging.info(msg)
    if dry_run:
        logging.info("[Dry Run] Skipping actual restart")
        return
    apps_api = client.AppsV1Api()
    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "restarted-at": str(time.time())
                    }
                }
            }
        }
    }
    try:
        apps_api.patch_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE,
            body=patch
        )
        notify_all_channels(f"Remediation triggered: {msg}")
    except Exception as err:
        logging.error(f"Failed to restart: {err}")

# --- Monitor Loop ---


def run_monitor(dry_run):
    try:
        config.load_kube_config()
    except:
        config.load_incluster_config()

    logging.info("NGINX health monitor started")
    failure_count = 0

    while True:
        print("Next Lopp")
        try:
            broken_pods = get_unhealthy_pods()
            if broken_pods:
                failure_count += 1
                logging.warning(
                    f"Detected unhealthy pods: {broken_pods} (failure #{failure_count})")
                if failure_count >= FAILURE_THRESHOLD:
                    restart_nginx_controller(dry_run)
                    failure_count = 0
            else:
                logging.info("All NGINX pods are healthy")
                failure_count = 0
        except Exception as monitor_err:
            logging.error(f"Monitoring error: {monitor_err}")
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not take real remediation actions")
    args = parser.parse_args()
    run_monitor(dry_run=args.dry_run)
