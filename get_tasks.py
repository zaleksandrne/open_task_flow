import requests
import os

from dotenv import load_dotenv

load_dotenv()


def get_tracker_issues_request(access_token, org_id):
    headers = {
        'Authorization': f'OAuth {access_token}',
        'X-Org-ID': org_id,
        'Content-Type': 'application/json'
    }

    payload = {
        "order": "-created"
    }

    url = "https://api.tracker.yandex.net/v2/issues/_search"
    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def get_tracker_issues():
    access_token = os.environ["YA_TOKEN"]
    org_id = os.environ["XORG_ID"]

    issues = get_tracker_issues_request(access_token, org_id)

    allowed_statuses = {"Открыт", "В работе"}

    result = {
        "count": 0,
        "issues": []
    }

    for issue in issues:
        if (
            "frontend" in issue.get("tags", [])
            and issue.get("status", {}).get("display") in allowed_statuses
        ):
            result["issues"].append({
                "key": issue.get("key"),
                "summary": issue.get("summary"),
                "status": issue.get("status", {}).get("display"),
                "tags": issue.get("tags", [])
            })

    result["count"] = len(result["issues"])
    return result
