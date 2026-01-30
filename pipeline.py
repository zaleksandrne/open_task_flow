import os, time, json, requests, subprocess, re
from get_tasks import get_tracker_issues
from dotenv import load_dotenv
from unidecode import unidecode


load_dotenv()

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
cwd = os.environ["TARGET_REPO"]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

# get tasks list
tasks = get_tracker_issues()["issues"]
tasks_txt = json.dumps(tasks, ensure_ascii=False, indent=2)
requests.post(url, data={"chat_id": CHAT_ID, "text": "Открытые задачи:\n\n" + tasks_txt})
if len(tasks) == 0:
    exit(0)

# get first task to work
time.sleep(1)
requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": "Беру в работу задачу:\n\n" + tasks[0]["key"] + ":" + tasks[0]["summary"]
})

# making task
time.sleep(1)
task = tasks[0]
summary = task["summary"]

prompt = f"""
Ты фронтенд-разработчик.

Репозиторий: frontend

Задача из трекера:
{summary}

Действуй как автономный агент.
Твоя цель — закрыть задачу полностью.
Не задавай вопросов, принимай разумные решения сам.
Не оставляй комментарии в коде.
Не пытайся устанавливать пакеты через npm или yarn.
Если нужен новый пакет — просто добавь его в package.json.
В конце выполнения не запускай сервер и не выполняй другие команды.
"""

subprocess.run(
    [
        "qwen",
        prompt,
        "--approval-mode", "yolo",
        "--all-files",
        "--channel", "CI"
    ],
    cwd=cwd,
    check=True
)

# commit and push
name = re.sub(r'[^a-z0-9\-]', '-', unidecode(summary.lower()))
branch_name = f"features/ticket-{task['key']}-{name}"

subprocess.run(["git", "checkout", "-b", branch_name], cwd=cwd, check=True)
subprocess.run(["git", "add", "."], cwd=cwd, check=True)
commit_msg = f"{task['key']}: {summary}"
subprocess.run(["git", "commit", "-m", commit_msg], cwd=cwd, check=True)
subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=cwd, check=True)
requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": f"Задача {task['key']} закоммичена и запушена в ветку {branch_name}"
})

# create merge request by glab in staging branch
subprocess.run([
    "glab", "mr", "create",
    "--source-branch", branch_name,
    "--target-branch", "staging",
    "--title", commit_msg,
    "--description", summary,
    "--yes"
], cwd=cwd, check=True)

subprocess.run(["git", "checkout", "staging"], cwd=cwd, check=True)

requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": f"Merge request для задачи {task['key']} создан в ветку staging"
})

