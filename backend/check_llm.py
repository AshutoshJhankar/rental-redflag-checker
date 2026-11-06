"""Check that the AI settings in .env work, and print the provider's exact error if not.

    python check_llm.py            # text request
    python check_llm.py --image    # also send the sample receipt (bill splitter: model must read images)
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


HINTS = {
    401: "The API key is wrong or revoked. Create a new key and paste it into .env.",
    402: "Your OpenRouter balance is negative. Free models need a balance of $0 or more.",
    404: "OpenRouter found no provider for this request. If the message mentions 'data policy', enable free "
         "endpoints in openrouter.ai/settings/privacy. If it mentions 'parameters', the model doesn't support JSON "
         "mode (the app falls back automatically). Otherwise the model ID is wrong or no longer free.",
    403: "Blocked before reaching the model (often Cloudflare). Check the base URL; the app now sends a User-Agent.",
    429: "Rate limited: the free model is busy, or you've used today's free requests. Wait, or try another :free model.",
}


def call(base: str, key: str, model: str, content, json_mode: bool) -> None:
    payload = {"model": model, "temperature": 0, "max_tokens": 300, "messages": [{"role": "user", "content": content}]}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(f"{base.rstrip('/')}/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "rental-redflag-checker/1.0"},
                                 method="POST")
    label = "JSON mode" if json_mode else "plain    "
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        if "error" in data:
            print(f"  {label}: provider error in body -> {data['error']}")
            return
        text = (data["choices"][0]["message"].get("content") or "").strip()
        print(f"  {label}: OK -> {text[:160]!r}")
    except urllib.error.HTTPError as e:
        body = e.read()[:600].decode(errors="replace")
        print(f"  {label}: HTTP {e.code} -> {body}")
        print(f"             hint: {HINTS.get(e.code, 'See the message above.')}")
    except Exception as e:  # network, timeout
        print(f"  {label}: could not connect -> {e}")


def main() -> None:
    env_path = HERE / ".env"
    if not env_path.exists():
        sys.exit(f"No .env found at {env_path}")
    env = load_env(env_path)
    key, base, model = env.get("LLM_API_KEY", ""), env.get("LLM_BASE_URL", ""), env.get("LLM_MODEL", "")
    if not key:
        sys.exit("LLM_API_KEY is empty in .env")
    print(f"Base URL: {base}\nModel:    {model}\nKey:      {key[:8]}… ({len(key)} chars)\n")
    print("Text request:")
    for jm in (True, False):
        call(base, key, model, 'Reply with JSON only: {"ok": true}', jm)
    if "--image" in sys.argv:
        img = HERE.parent / "frontend" / "public" / "sample-receipt.jpg"
        url = "data:image/jpeg;base64," + base64.b64encode(img.read_bytes()).decode()
        print("\nImage request (sample receipt):")
        call(base, key, model, [{"type": "text", "text": "What is the restaurant name and grand total on this bill? "
                                 'Reply as JSON: {"merchant": "...", "total": 0}'},
                                {"type": "image_url", "image_url": {"url": url}}], True)


if __name__ == "__main__":
    main()
