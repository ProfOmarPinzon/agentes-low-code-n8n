"""Genera la plantilla de pago (DeepSeek) a partir de la plantilla gratis (Groq).

Solo reemplaza los nodos de modelo `lmChatGroq` por `lmChatDeepSeek`.
Prompts, tools MCP, parsers, conexiones y Retry On Fail quedan idénticos,
así la plantilla gratis sigue siendo la única fuente de verdad.

Uso (desde la raíz del repo):
    uv run scripts/make_deepseek.py                 # regenera P1 y P2
    uv run scripts/make_deepseek.py --model deepseek-v4-pro
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "demo-basic" / "workflow",
    ROOT / "demo-advanced" / "workflow",
]
GROQ_TYPE = "@n8n/n8n-nodes-langchain.lmChatGroq"
DEEPSEEK_TYPE = "@n8n/n8n-nodes-langchain.lmChatDeepSeek"


def convert(workflow: dict, model: str) -> tuple[dict, int]:
    renames = {}
    for node in workflow["nodes"]:
        if node["type"] != GROQ_TYPE:
            continue
        old_name = node["name"]
        new_name = old_name.replace("Groq", "DeepSeek")
        renames[old_name] = new_name
        node["name"] = new_name
        node["type"] = DEEPSEEK_TYPE
        node["typeVersion"] = 1
        node["parameters"] = {"model": model, "options": node["parameters"].get("options", {})}
        node["credentials"] = {"deepSeekApi": {"name": "DeepSeek account"}}

    # Las conexiones de n8n se indexan por nombre de nodo.
    connections = {}
    for src, outputs in workflow["connections"].items():
        for kind in outputs.values():
            for branch in kind:
                for link in branch:
                    link["node"] = renames.get(link["node"], link["node"])
        connections[renames.get(src, src)] = outputs
    workflow["connections"] = connections
    workflow["name"] = workflow["name"].replace("Groq gratis", "DeepSeek de pago")
    return workflow, len(renames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="deepseek-flash", help="modelo de DeepSeek (default: deepseek-flash)")
    args = parser.parse_args()

    for folder in TARGETS:
        src = folder / "workflow-groq-free.json"
        dst = folder / "workflow-deepseek.json"
        workflow, count = convert(json.loads(src.read_text(encoding="utf-8")), args.model)
        dst.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{dst.relative_to(ROOT)}: {count} nodos de modelo -> {args.model}")


if __name__ == "__main__":
    main()
