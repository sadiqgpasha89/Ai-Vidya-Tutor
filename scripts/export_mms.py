#!/usr/bin/env python3
"""Convert Meta's MMS voices for Tamil, Gujarati, Kannada and Odia to ONNX, so the server can speak them without PyTorch.
(CC-BY-NC 4.0 licence: free for non-commercial and school use.)  Run once, with a Python that has PyTorch:

  python3 -m venv /tmp/mms && /tmp/mms/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
  /tmp/mms/bin/pip install transformers onnx onnxscript
  /tmp/mms/bin/python scripts/export_mms.py            # all four (about 150 MB each), written to data/voices/
  /tmp/mms/bin/python scripts/export_mms.py tam        # only one
"""
import json
import sys
from pathlib import Path

import torch
from transformers import VitsModel, VitsTokenizer

OUT = Path(__file__).resolve().parent.parent / "data" / "voices"
SAMPLES = {"tam": "வணக்கம், இன்று நாம் இயக்கம் பற்றி கற்றுக்கொள்வோம்.", "guj": "નમસ્તે, આજે આપણે ગતિ વિશે શીખીશું.", "kan": "ನಮಸ್ಕಾರ, ಇಂದು ನಾವು ಚಲನೆಯ ಬಗ್ಗೆ ಕಲಿಯೋಣ.", "ory": "ନମସ୍କାର, ଆଜି ଆମେ ଗତି ବିଷୟରେ ଶିଖିବା."}


class Wave(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        return self.model(input_ids=input_ids, attention_mask=attention_mask).waveform


def export(iso: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"facebook/mms-tts-{iso}"
    print(f"↓ {name}", flush=True)
    tok, model = VitsTokenizer.from_pretrained(name), VitsModel.from_pretrained(name).eval()
    ids = tok(SAMPLES[iso], return_tensors="pt")
    onnx = OUT / f"mms-{iso}.onnx"
    torch.onnx.export(Wave(model), (ids["input_ids"], ids["attention_mask"]), str(onnx), input_names=["input_ids", "attention_mask"], output_names=["waveform"],
                      dynamic_axes={"input_ids": {1: "t"}, "attention_mask": {1: "t"}, "waveform": {1: "s"}}, opset_version=17, dynamo=False)
    vocab = tok.get_vocab()
    meta = {"vocab": vocab, "sampling_rate": model.config.sampling_rate, "blank_id": vocab[tok.pad_token] if tok.add_blank else None, "lowercase": bool(tok.normalize), "source": name, "license": "CC-BY-NC-4.0"}
    (OUT / f"mms-{iso}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"✓ {onnx} ({onnx.stat().st_size // 1_000_000} MB)", flush=True)


if __name__ == "__main__":
    for iso in sys.argv[1:] or list(SAMPLES):
        export(iso)
