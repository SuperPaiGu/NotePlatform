import os
import requests
from flask import Flask, request

app = Flask(__name__)
DINGTALK_URL = os.environ["DINGTALK_WEBHOOK"]

@app.route("/dingtalk", methods=["POST"])
def dingtalk():
    data = request.get_json()
    lines = []
    for alert in data.get("alerts", []):
        status = alert.get("status")
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        name = labels.get("alertname", "未知")
        severity = labels.get("severity", "none")
        summary = annotations.get("summary", "")
        emoji = "🔴" if status == "firing" else "✅"
        lines.append(f"{emoji} [告警] {name}\n级别: {severity}\n状态: {status}\n{summary}")
    content = "\n\n".join(lines)
    print(f"[收到告警] {content}", flush=True)
    resp = requests.post(DINGTALK_URL, json={"msgtype": "text", "text": {"content": content}})
    print(f"[钉钉响应] {resp.status_code} {resp.text}", flush=True)
    return resp.text, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)