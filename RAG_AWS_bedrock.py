import os
import json
from datetime import datetime
from time import perf_counter
import difflib
import boto3
import botocore.config

# ========= Environment variables (set in Lambda console) =========
# KB_ID=kb-xxxxxxxxxxxxxxxx
# MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0
# S3_BUCKET=mlflowarnav
# S3_PREFIX=blog-output/
# AWS_REGION=us-east-1
# ================================================================

CFG = botocore.config.Config(read_timeout=300, retries={'max_attempts': 3})
REGION = os.environ.get("AWS_REGION", "us-east-1")
KB_ID = os.environ.get("KB_ID")
MODEL_ARN = os.environ.get("MODEL_ARN")  # e.g., arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0
MODEL_ID = MODEL_ARN.split("foundation-model/")[-1] if (MODEL_ARN and "foundation-model/" in MODEL_ARN) else MODEL_ARN

OUT_BUCKET = os.environ.get("S3_BUCKET")
OUT_PREFIX = os.environ.get("S3_PREFIX", "blog-output/")

# Optional: also write a .diff file when mode="both"
SAVE_DIFF_FILE = True

BEDROCK_RT = boto3.client("bedrock-runtime", region_name=REGION, config=CFG)
KB_RT = boto3.client("bedrock-agent-runtime", region_name=REGION, config=CFG)
S3 = boto3.client("s3", region_name=REGION)


# ----------------- Helpers -----------------
def _strip_templates(txt: str) -> str:
    if not txt:
        return txt
    for t in ("<s>", "</s>", "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>", "[/S]", "[S]"):
        txt = txt.replace(t, "")
    return txt.strip()


def _unified_diff(a: str, b: str) -> str:
    diff_lines = difflib.unified_diff(
        a.splitlines(), b.splitlines(), fromfile="vanilla", tofile="rag", lineterm=""
    )
    out = "\n".join(list(diff_lines))
    return out[:40000]  # cap size


def save_to_s3(key: str, content: str):
    S3.put_object(Bucket=OUT_BUCKET, Key=key, Body=content.encode("utf-8"))
    print(f"Saved to s3: s3://{OUT_BUCKET}/{key}")


# ----------------- Generation paths -----------------
def blog_generate_vanilla(topic: str) -> str:
    """
    Vanilla (no retrieval). Primary: Converse API; Fallback: invoke_model with clean template.
    Returns Markdown (no HTML).
    """
    # Primary: Converse
    try:
        resp = BEDROCK_RT.converse(
            modelId=MODEL_ID,
            messages=[{
                "role": "user",
                "content": [{"text": f"Write a 180–220 word blog about '{topic}'. Output Markdown only (no HTML)."}]
            }],
            inferenceConfig={"maxTokens": 350, "temperature": 0.5, "topP": 0.9, "stopSequences": ["</s>"]}
        )
        return resp["output"]["message"]["content"][0]["text"]
    except Exception as e:
        print(f"[vanilla:converse] Error: {e}")

    # Fallback: invoke_model
    try:
        prompt = f"""<s>[INST] <<SYS>>
You are a concise technical writer. Output Markdown only (no HTML).
Answer length: 180–220 words.
<</SYS>>
Write a blog about "{topic}".
[/INST]"""
        body = {"prompt": prompt, "max_gen_len": 768, "temperature": 0.5, "top_p": 0.9}
        r = BEDROCK_RT.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
        txt = json.loads(r["body"].read()).get("generation", "")
        return _strip_templates(txt)
    except Exception as e2:
        print(f"[vanilla:fallback] Error: {e2}")
        return ""


def blog_generate_rag(topic: str, k: int = 5):
    """
    RAG via Bedrock Knowledge Bases.
    Returns (markdown_text, citations[list of s3:// or web URLs])
    """
    prompt = (
        f"Write a 180–220 word blog about '{topic}'. "
        "Use ONLY facts from the knowledge base. Respond in Markdown (no HTML). "
        "End with a short 'Sources' list using [1], [2]…"
    )
    try:
        resp = KB_RT.retrieve_and_generate(
            input={"text": prompt},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {"numberOfResults": int(k)}
                    },
                },
            },
        )
        text = resp["output"]["text"]
        citations = []
        for c in resp.get("citations", []):
            for r in c.get("retrievedReferences", []):
                loc = r.get("location", {})
                s3uri = (loc.get("s3Location", {}) or {}).get("uri")
                url = (loc.get("webLocation", {}) or {}).get("url")
                if s3uri or url:
                    citations.append(s3uri or url)
        return text, citations
    except Exception as e:
        print(f"[rag] Error: {e}")
        return "", []


# ----------------- Lambda handler -----------------
def lambda_handler(event, context):
    print("== RAG_COMPARE v1.2 ==")
    print("REGION:", REGION)
    print("KB_ID:", KB_ID)
    print("MODEL_ID:", MODEL_ID)

    # Parse input body robustly
    body_raw = event.get("body") if isinstance(event, dict) else None
    if isinstance(body_raw, dict):
        body = body_raw
    else:
        try:
            body = json.loads(body_raw) if body_raw else {}
        except Exception:
            body = {}

    topic = body.get("blog_topic") or "Reinforcement Learning basics"
    mode = (body.get("mode") or "both").lower()  # "vanilla" | "rag" | "both"
    k = int(body.get("k", 5))

    result = {
        "topic": topic,
        "mode": mode,
        "generated_at": datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
        "timings_ms": {},
        "outputs": {}
    }

    # VANILLA
    if mode in ("vanilla", "both"):
        t0 = perf_counter()
        vanilla_md = blog_generate_vanilla(topic)
        t1 = perf_counter()
        result["outputs"]["vanilla"] = {"text": vanilla_md}
        result["timings_ms"]["vanilla"] = int((t1 - t0) * 1000)

    # RAG
    if mode in ("rag", "both"):
        t0 = perf_counter()
        rag_md_text, rag_cites = blog_generate_rag(topic, k=k)
        t1 = perf_counter()
        result["outputs"]["rag"] = {"text": rag_md_text, "citations": rag_cites}
        result["timings_ms"]["rag"] = int((t1 - t0) * 1000)

    # Prepare outputs to S3
    ts = result["generated_at"]
    key_json = f"{OUT_PREFIX}{ts}_{mode}.json"
    S3.put_object(Bucket=OUT_BUCKET, Key=key_json, Body=json.dumps(result).encode("utf-8"))

    # Save separate markdowns for easy viewing
    if "vanilla" in result["outputs"] and result["outputs"]["vanilla"]["text"]:
        save_to_s3(f"{OUT_PREFIX}{ts}_{mode}_vanilla.md", result["outputs"]["vanilla"]["text"])

    if "rag" in result["outputs"]:
        rag_text = result["outputs"]["rag"].get("text", "")
        if rag_text:
            cites = result["outputs"]["rag"].get("citations", [])
            # Append sources to RAG markdown if present
            if cites:
                sources_md = "\n\n**Sources**\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(cites))
                rag_text_to_save = rag_text.rstrip() + sources_md
            else:
                rag_text_to_save = rag_text
            save_to_s3(f"{OUT_PREFIX}{ts}_{mode}_rag.md", rag_text_to_save)

    # Save diff file (optional, only if both present)
    if SAVE_DIFF_FILE and mode == "both":
        vtxt = result["outputs"].get("vanilla", {}).get("text", "")
        rtxt = result["outputs"].get("rag", {}).get("text", "")
        if vtxt and rtxt:
            diff_txt = _unified_diff(vtxt, rtxt)
            if diff_txt:
                save_to_s3(f"{OUT_PREFIX}{ts}_{mode}.diff", diff_txt)
            # also include diff in the JSON response artifact next time (optional)
            # (keep API response small)

    # Compact API response
    api_resp = {
        "message": "Generated",
        "s3_key": key_json,
        "timings_ms": result["timings_ms"],
        "has_diff": (mode == "both"),
        "rag_citations": result["outputs"].get("rag", {}).get("citations", [])
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(api_resp)
    }
