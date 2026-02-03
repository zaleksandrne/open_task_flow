import os, time, requests, subprocess, re
from get_tasks import get_tasks
from dotenv import load_dotenv
from unidecode import unidecode


load_dotenv()

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
cwd = 'target_repo/' + os.environ["TARGET_REPO"]

SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
EDIT_URL = f"https://api.telegram.org/bot{TOKEN}/editMessageText"

MAX_TG_TEXT = 3500
LOG_UPDATE_INTERVAL = float(os.environ.get("TG_LOG_UPDATE_INTERVAL", "2.0"))


def _trim_tg_text(text: str) -> str:
    if len(text) <= MAX_TG_TEXT:
        return text
    return "…\n" + text[-MAX_TG_TEXT:]


def send_message(text: str) -> int:
    resp = requests.post(SEND_URL, data={
        "chat_id": CHAT_ID,
        "text": text
    })
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["message_id"]


def edit_message(message_id: int, text: str) -> None:
    requests.post(EDIT_URL, data={
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": _trim_tg_text(text)
    })


def update_task_status(task: dict, status_env_var: str) -> None:
    board = os.environ.get("TASK_BOARD", "tracker").strip().lower()
    if board in {"tracker", "yandex", "yandex_tracker", "yandex-tracker", "ya"}:
        return
    if board != "taiga":
        raise ValueError(f"Unsupported TASK_BOARD: {board}")

    base_url = os.environ.get("TAIGA_BASE_URL", "https://api.taiga.io").rstrip("/")
    token = os.environ["TAIGA_TOKEN"]
    status_id = os.environ.get(status_env_var)
    if not status_id:
        raise ValueError(f"Missing {status_env_var} for Taiga status update")
    task_id = task.get("id")
    if not task_id:
        raise ValueError("Missing Taiga task id for status update")

    url = f"{base_url}/api/v1/userstories/{task_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    current = requests.get(url, headers=headers)
    current.raise_for_status()
    version = current.json().get("version")
    if version is None:
        raise ValueError("Missing version in Taiga task response")
    response = requests.patch(
        url,
        headers=headers,
        json={"status": int(status_id), "version": version}
    )
    response.raise_for_status()

# get tasks list
tasks = get_tasks()["issues"]

if not tasks:
    exit(0)

lines = ["Открытые задачи:\n"]
for i, task in enumerate(tasks, 1):
    lines.append(f"{i}. {task['key']}: {task['summary']}")

tasks_txt = "\n".join(lines)

send_message(tasks_txt)

# get first task to work
time.sleep(1)
update_task_status(tasks[0], "TAIGA_IN_PROGRESS_STATUS_ID")
send_message("Беру в работу задачу:\n\n" + tasks[0]["key"] + ":" + tasks[0]["summary"])

# making task
time.sleep(1)
task = tasks[0]
summary = task["summary"]

prompt = f"""
Ты фронтенд-разработчик.

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

log_message_id = send_message("Стартую выполнение. Лог появится здесь…")
log_lines = []
last_update = 0.0

process = subprocess.Popen(
    [
        "qwen",
        prompt,
        "--approval-mode", "yolo",
        "--all-files",
        "--channel", "CI"
    ],
    cwd=cwd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

for line in process.stdout:
    log_lines.append(line.rstrip())
    now = time.time()
    if now - last_update >= LOG_UPDATE_INTERVAL:
        last_update = now
        log_text = "Лог выполнения:\n" + "\n".join(log_lines)
        edit_message(log_message_id, log_text)

process.wait()
if process.returncode != 0:
    log_text = "Лог выполнения:\n" + "\n".join(log_lines)
    edit_message(log_message_id, log_text + "\n\nВыполнение завершилось с ошибкой.")
    raise subprocess.CalledProcessError(process.returncode, process.args)

log_text = "Лог выполнения:\n" + "\n".join(log_lines)
edit_message(log_message_id, log_text + "\n\nВыполнение завершено.")

# commit and push
name = re.sub(r'[^a-z0-9\-]', '-', unidecode(summary.lower()))
branch_name = f"features/{task['key']}/{name}"

existing = subprocess.run(
    ["git", "branch", "--list", branch_name],
    cwd=cwd,
    check=True,
    stdout=subprocess.PIPE,
    text=True
)
if existing.stdout.strip():
    subprocess.run(["git", "branch", "-D", branch_name], cwd=cwd, check=True)

subprocess.run(["git", "checkout", "-b", branch_name], cwd=cwd, check=True)
subprocess.run(["git", "add", "."], cwd=cwd, check=True)
commit_msg = f"{task['key']}: {summary}"
subprocess.run(["git", "commit", "-m", commit_msg], cwd=cwd, check=True)
subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=cwd, check=True)
send_message(f"Задача {task['key']} закоммичена и запушена в ветку {branch_name}")

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

send_message(f"Мерж реквест для задачи {task['key']} создан в ветку staging")

update_task_status(task, "TAIGA_IN_REVIEW_STATUS_ID")
send_message(f"Задача {task['key']} перенесена на ревью")

