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


def get_taiga_tasks_request(base_url, token, project_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {
        "project": project_id
    }
    url = f"{base_url}/api/v1/userstories"
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def get_tracker_issues():
    access_token = os.environ["YA_TOKEN"]
    org_id = os.environ["XORG_ID"]
    issue_tag = os.environ["ISSUE_TAG"]

    issues = get_tracker_issues_request(access_token, org_id)
    if isinstance(issues, dict):
        issues = issues.get("issues", [])

    allowed_statuses = {"Открыт", "В работе"}

    result = {
        "count": 0,
        "issues": []
    }

    for issue in issues:
        if (
            issue_tag in issue.get("tags", [])
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


def get_taiga_tasks():
    base_url = os.environ.get("TAIGA_BASE_URL", "https://api.taiga.io").rstrip("/")
    token = os.environ["TAIGA_TOKEN"]
    project_id = os.environ["TAIGA_PROJECT_ID"]
    issue_tag = os.environ.get("ISSUE_TAG")

    tasks = get_taiga_tasks_request(base_url, token, project_id)
    allowed_statuses = ['Открыто']

    result = {
        "count": 0,
        "issues": []
    }

    for task in tasks:
        task_tags = task.get("tags", [[]])[0]
        status_name = task['status_extra_info']['name']
        if issue_tag and issue_tag not in task_tags:
            continue
        if status_name and status_name not in allowed_statuses:
            continue
        task_key = task.get("ref") or task.get("id")
        result["issues"].append({
            "key": str(task_key),
            "id": task.get("id"),
            "summary": task.get("subject"),
            "status": status_name,
            "tags": task_tags
        })

    result["count"] = len(result["issues"])
    return result


def get_tasks():
    board = os.environ.get("TASK_BOARD", "yandex_tracker").strip().lower()
    if board == "yandex_tracker":
        return get_tracker_issues()
    if board == "taiga":
        return get_taiga_tasks()
    raise ValueError(f"Unsupported TASK_BOARD: {board}")
