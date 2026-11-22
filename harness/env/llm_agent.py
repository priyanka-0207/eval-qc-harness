import hashlib
import json
import re
import time
import urllib.request

from .. import config

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma4"
NUM_CTX = 12288
MAX_OBS_CHARS = 8000
CACHE_NAME = "env_llm_cache.jsonl"

SYSTEM = (
    "You are an agent working inside a task environment. Use the tools to complete the task. "
    "Call exactly one tool per turn. Read each tool result before deciding the next step. "
    "When the task is complete, call submit. Do not ask the user questions; nobody will answer."
)

ARG_TYPES = {
    "amount": {"type": "number"},
    "row_ids": {"type": "array", "items": {"type": "integer"}},
}


def tool_schemas(tools):
    schemas = []
    for name, desc in tools.items():
        props, required = {}, []
        m = re.match(r"args:\s*(.+?)\.\s", desc + " ")
        if m:
            for arg in m.group(1).split(","):
                arg = re.sub(r"\(.*?\)", "", arg).strip()
                if arg:
                    props[arg] = ARG_TYPES.get(arg, {"type": "string"})
                    required.append(arg)
        schemas.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}})
    schemas.append({"type": "function", "function": {
        "name": "submit", "description": "Finish the task. Call this once you are done.",
        "parameters": {"type": "object", "properties": {}, "required": []}}})
    return schemas


def task_message(start):
    text = start["prompt"]
    if start.get("spec"):
        text += "\n\nSpec:\n" + json.dumps(start["spec"], indent=1)
    return text


def _obs_text(obs):
    text = json.dumps(obs, default=str)
    if len(text) > MAX_OBS_CHARS:
        text = text[:MAX_OBS_CHARS] + ' ... (truncated, use a narrower query)"'
    return text


class OllamaClient:
    def __init__(self, model=DEFAULT_MODEL, temperature=0.0, seed=0, cache_path=None, url=OLLAMA_URL):
        self.model, self.temperature, self.seed, self.url = model, temperature, seed, url
        self.cache_path = cache_path or (config.DATA / CACHE_NAME)
        self.cache = {}
        self.calls = 0
        self.seconds = 0.0
        if self.cache_path.exists():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.cache[row["key"]] = row["message"]

    def _key(self, messages, tools):
        blob = json.dumps({"model": self.model, "t": self.temperature, "seed": self.seed, "ctx": NUM_CTX,
                           "messages": messages, "tools": tools}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def chat(self, messages, tools):
        key = self._key(messages, tools)
        if key in self.cache:
            return self.cache[key]
        body = {"model": self.model, "messages": messages, "tools": tools, "stream": False, "think": False,
                "options": {"temperature": self.temperature, "seed": self.seed, "num_ctx": NUM_CTX}}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        start = time.time()
        with urllib.request.urlopen(req, timeout=1800) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.seconds += time.time() - start
        self.calls += 1
        msg = data["message"]
        message = {"role": "assistant", "content": msg.get("content", ""),
                   "tool_calls": [{"function": {"name": c["function"]["name"],
                                                "arguments": c["function"].get("arguments") or {}}}
                                  for c in msg.get("tool_calls") or []]}
        self.cache[key] = message
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "model": self.model, "message": message}) + "\n")
        return message


def make_agent(client, max_text_replies=2):
    def agent(start):
        tools = tool_schemas(start["tools"])
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task_message(start)}]
        text_replies = 0
        while True:
            reply = client.chat(messages, tools)
            calls = reply.get("tool_calls") or []
            if not calls:
                text_replies += 1
                messages.append({"role": "assistant", "content": reply.get("content", "")})
                if text_replies > max_text_replies:
                    yield {"tool": "submit", "args": {}}
                    return
                messages.append({"role": "user", "content": "Use a tool. Call submit when you are done."})
                continue
            call = calls[0]["function"]
            name, args = call["name"], call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            messages.append({"role": "assistant", "content": reply.get("content", ""),
                             "tool_calls": [{"function": {"name": name, "arguments": args}}]})
            if name == "submit":
                yield {"tool": "submit", "args": {}}
                return
            obs = yield {"tool": name, "args": args}
            messages.append({"role": "tool", "tool_name": name, "content": _obs_text(obs)})
    return agent
