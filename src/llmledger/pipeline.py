import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from llmledger import events, history, page, survival

SOURCE = "https://github.com/BerriAI/litellm.git"
UPSTREAM = Path("data/upstream")
EVENTS = "data/events.csv"
SURVIVAL = "data/survival.csv"
SITE = "site"


def check_python(pin_file=".python-version"):
    wanted = Path(pin_file).read_text().strip()
    running = platform.python_version()
    if running == wanted:
        return f"python {running}, as pinned in {pin_file}"
    return (f"WARNING: python {running}, but {pin_file} pins {wanted}; "
            "numbers may differ slightly")


def update(repo=UPSTREAM):
    if repo.exists():
        subprocess.run(("git", "fetch", "--quiet", "origin", "main"),
                       cwd=repo, check=True)
    else:
        subprocess.run(("git", "clone", "--quiet", "--filter=blob:none",
                        "--no-checkout", SOURCE, str(repo)), check=True)


def main():
    print(check_python())
    update()
    print("versions fetched:", history.prefetch(UPSTREAM))
    events.main(UPSTREAM, EVENTS)
    sizes = survival.main(EVENTS, SURVIVAL)
    versions = history.commits(UPSTREAM)
    sha, when = versions[-1]
    info = {
        "models": sizes["main"],
        "since": versions[0][1],
        "sha": sha,
        "when": when,
        "built": datetime.now(timezone.utc),
        "python": platform.python_version(),
    }
    print("page written:", page.main(SURVIVAL, SITE, info))


if __name__ == "__main__":
    main()