#!/usr/bin/env python
"""LLM Explainer 테스트 스크립트 v4 - Raw 응답 출력"""
import os
import sys
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv()

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

project = os.getenv('PROJECT_ID')
location = os.getenv('VERTEX_LOCATION', 'us-central1')
model_name = os.getenv('EXPLAINER_LLM_MODEL', 'gemini-2.5-flash')
max_tokens = int(os.getenv('SSOT_EXPLAIN_LLM_MAX_TOKENS', 512))

print(f"Project: {project}")
print(f"Location: {location}")
print(f"Model: {model_name}")
print(f"Max Tokens: {max_tokens}")

vertexai.init(project=project, location=location)
model = GenerativeModel(model_name)

signals = [{"source": "default", "name": "baseline", "delta": 0, "evidence": "표준 신뢰도 기준 적용"}]

prompt = """You are a Document Reliability Analyst.
Based on the following reliability signals, provide a ONE-LINE summary.

Signals:
""" + json.dumps(signals, ensure_ascii=False) + """

Respond with ONLY a valid JSON object:
{"one_liner": "한국어 요약", "keywords": ["keyword1"]}
"""

print("=" * 50)

try:
    response = model.generate_content(
        prompt,
        generation_config=GenerationConfig(max_output_tokens=max_tokens)
    )
    
    print(f"finish_reason: {response.candidates[0].finish_reason}")
    print(f"finish_reason name: {response.candidates[0].finish_reason.name}")
    
    # Raw bytes/repr
    raw_text = response.text
    print(f"\nRAW TEXT (repr):")
    print(repr(raw_text))
    print(f"\nRAW TEXT (display):")
    print(raw_text)
    print(f"\nLength: {len(raw_text)}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
