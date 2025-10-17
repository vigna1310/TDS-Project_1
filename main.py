import os, base64, subprocess, requests, time
from fastapi import FastAPI, HTTPException, Request
from dotenv import load_dotenv
import re

load_dotenv()

# ==== CONFIG ====
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
AIPIPE_KEY     = os.getenv("AIPIPE_KEY")
SECRET_KEY     = os.getenv("secret") or "yoobro"
GITHUB_USERNAME = "vigna1310"     # <--- change if needed

app = FastAPI()

# ==== UTILS ====
def validate_secret(secret: str) -> bool:
    return secret == SECRET_KEY


# ----------------------------------------------------
#  Create GitHub repo
# ----------------------------------------------------
def create_github_repo(repo_name: str):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {"name": repo_name, "private": False, "auto_init": True, "license_template": "mit"}
    r = requests.post("https://api.github.com/user/repos", headers=headers, json=payload)
    if r.status_code == 201:
        print(f"✅ Repo {repo_name} created.")
    elif r.status_code == 422 and "name already exists" in r.text:
        print(f"⚠️ Repo {repo_name} already exists, skipping creation.")
    else:
        raise Exception(f"❌ Repo creation failed: {r.status_code}, {r.text}")


# ----------------------------------------------------
#  Push files to repo
# ----------------------------------------------------
def push_files_to_repo(repo_name: str, files: list[dict]):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    for f in files:
        file_name = f["name"]
        content = f["content"]
        if isinstance(content, bytes):
            content = base64.b64encode(content).decode()
        else:
            content = base64.b64encode(content.encode()).decode()

        # get SHA if file exists
        get_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_name}"
        sha = requests.get(get_url, headers=headers)
        sha_val = sha.json().get("sha") if sha.status_code == 200 else None

        payload = {"message": f"Add/update {file_name}", "content": content}
        if sha_val:
            payload["sha"] = sha_val

        r = requests.put(get_url, headers=headers, json=payload)
        if r.status_code not in (200, 201):
            raise Exception(f"Push failed for {file_name}: {r.status_code}, {r.text}")
        print(f"✅ Pushed {file_name}.")


# ----------------------------------------------------
#  Enable GitHub Pages
# ----------------------------------------------------
def enable_github_pages(repo_name: str):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {"build_type": "legacy", "source": {"branch": "main", "path": "/"}}
    r = requests.post(f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
                      headers=headers, json=payload)
    if r.status_code == 201:
        print("✅ GitHub Pages enabled.")
    elif r.status_code == 409:
        print("⚠️ GitHub Pages already enabled.")
    else:
        raise Exception(f"❌ Pages enable failed: {r.status_code}, {r.text}")


# ----------------------------------------------------
#  Generate code with LLM
# ----------------------------------------------------
def write_code_with_llm(brief: str):
    endpoint = "https://aipipe.org/openrouter/v1/chat/completions"
    payload = {
        "model": "openai/gpt-4.1-nano",
        "messages": [
            {"role": "system", "content": "Generate runnable HTML/JS web apps (single-page)."},
            {"role": "user", "content": f"Create a GitHub Pages app for: {brief}"}
        ]
    }
    headers = {"Authorization": f"Bearer {AIPIPE_KEY}", "Content-Type": "application/json"}
    r = requests.post(endpoint, headers=headers, json=payload)
    if r.status_code != 200:
        raise Exception(f"LLM call failed: {r.status_code}, {r.text}")

    html_code = r.json()["choices"][0]["message"]["content"]
    cleaned_html = re.sub(r"^.*?<html", "<html", html_code, flags=re.S)  # start from <html>
    cleaned_html = re.sub(r"</html>.*$", "</html>", cleaned_html, flags=re.S)  # end at </html>
    cleaned_html = cleaned_html.strip()
    print("✅ Generated HTML code with LLM.")
    return [{"name": "index.html", "content": cleaned_html},
            {"name": "README.md", "content": f"# Generated App\n\nTask: {brief}\n\nGenerated ."},
            {"name": "LICENSE", "content": "MIT License"},
            {"name": ".nojekyll", "content": ""}
        ]
    


# ----------------------------------------------------
#  ROUND 1
# ----------------------------------------------------
def round1(data):
    repo_name = f"{data['task']}_{data['nonce']}".replace(" ", "-")
    print(f"🚀 ROUND 1 → {repo_name}")
    create_github_repo(repo_name)

    files = write_code_with_llm(data["brief"])
    push_files_to_repo(repo_name, files)
    enable_github_pages(repo_name)

    # wait for build
    time.sleep(10)
    commit_sha = requests.get(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/commits/main"
    ).json().get("sha", "unknown")

    pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    print(f"✅ Deployed: {pages_url}")
    return repo_name, commit_sha, pages_url


# ----------------------------------------------------
#  ROUND 2  (adds SVG handling + redeploy)
# ----------------------------------------------------
def round2(data):
    repo_name = f"{data['task']}_{data['nonce']}".replace(" ", "-")
    print(f"🔄 ROUND 2 → updating {repo_name}")

    # Clone
    subprocess.run(["git", "clone", f"https://github.com/{GITHUB_USERNAME}/{repo_name}.git"], check=True)
    os.chdir(repo_name)

    # Update README
    with open("README.md", "a", encoding="utf-8") as f:
        f.write(f"\n\n## Round 2 Update\n{data['brief']}\n")

    # Inject SVG-handling JS
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()

        # simple JS patch
        patch = """
<script>
document.addEventListener('DOMContentLoaded', () => {
  const img = document.querySelector('img, canvas');
  if (img) {
    const src = img.getAttribute('src');
    if (src && src.endsWith('.svg')) {
      fetch(src)
        .then(r => r.text())
        .then(svg => {
          const div = document.createElement('div');
          div.innerHTML = svg;
          img.replaceWith(div.firstChild);
          console.log('✅ SVG loaded inline');
        })
        .catch(err => console.error('SVG load error', err));
    }
  }
});
</script>
"""
        if "SVG loaded inline" not in html:
            html = html.replace("</body>", patch + "\n</body>")

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)

    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "Round 2 update: SVG support"], check=True)
    subprocess.run(["git", "push"], check=True)

    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    os.chdir("..")
    pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    print(f"✅ Round 2 done → {pages_url}")
    return repo_name, commit_sha, pages_url


# ----------------------------------------------------
#  MAIN ENDPOINT
# ----------------------------------------------------
@app.post("/handle_task")
def handle_task(data: dict):
    print("📩 Received:", data)

    if not validate_secret(data.get("secret", "")):
        raise HTTPException(status_code=403, detail="Invalid secret")

    round_number = int(data.get("round", 1))
    email = data.get("email")
    evaluation_url = data.get("evaluation_url")

    try:
        if round_number == 1:
            repo, sha, pages = round1(data)
        elif round_number == 2:
            repo, sha, pages = round2(data)
        else:
            raise HTTPException(status_code=400, detail="Unsupported round")

        # --- notify evaluator ---
        payload = {
            "email": email,
            "task": data["task"],
            "round": round_number,
            "nonce": data["nonce"],
            "repo_url": f"https://github.com/{GITHUB_USERNAME}/{repo}",
            "commit_sha": sha,
            "pages_url": pages,
        }
        headers = {"Content-Type": "application/json"}
        print("📤 Posting to evaluation URL:", evaluation_url)
        resp = requests.post(evaluation_url, headers=headers, json=payload)
        print("✅ Evaluation server replied:", resp.status_code)

        return {"status": "ok", "round": round_number, "repo": repo}

    except Exception as e:
        print("❌ Error:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
