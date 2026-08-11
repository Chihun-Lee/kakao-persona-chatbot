# -*- coding: utf-8 -*-
"""빌드된 페르소나를 MLX-LM LoRA 파인튜닝용 chat JSONL로 내보내기.

사용:  python scripts/export_finetune.py <화자이름> [--build build] [--out finetune]
결과: {out}/{화자}/train.jsonl, valid.jsonl  (mlx_lm.lora --data 디렉토리로 사용)

이후 맥북(Apple Silicon)에서:
  pip install mlx-lm
  mlx_lm.lora --model Qwen/Qwen2.5-7B-Instruct --train --data finetune/<화자> --iters 600
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("speaker")
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", default="finetune")
    ap.add_argument("--valid-ratio", type=float, default=0.05)
    args = ap.parse_args()

    src = Path(args.build) / "personas" / f"{args.speaker}.json"
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    system = f"너는 '{args.speaker}'이다. 카카오톡에서 평소 말투 그대로 짧게 답장한다."
    rows = []
    for ex in data["fewshot"]:
        ctx = "\n".join(f"{c['speaker']}: {' / '.join(c['texts'])}" for c in ex["context"])
        rows.append({"messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": ctx},
            {"role": "assistant", "content": "\n".join(ex["response"])},
        ]})

    out_dir = Path(args.out) / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)
    n_valid = max(1, int(len(rows) * args.valid_ratio))
    for name, subset in [("valid.jsonl", rows[:n_valid]), ("train.jsonl", rows[n_valid:])]:
        with open(out_dir / name, "w", encoding="utf-8") as f:
            for r in subset:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{args.speaker}: train {len(rows)-n_valid} / valid {n_valid} → {out_dir}")


if __name__ == "__main__":
    main()
