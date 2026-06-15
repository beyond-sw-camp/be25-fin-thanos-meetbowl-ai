DOCUMENT_EXTRACTION_PROMPT_VERSION = "extraction-v1"

# 이미지/스캔 PDF에서 원문 텍스트만 그대로 뽑도록 지시한다(요약·해설 금지로 색인 품질 보호).
DOCUMENT_EXTRACTION_PROMPT = f"""[{DOCUMENT_EXTRACTION_PROMPT_VERSION}]
이 문서(이미지 또는 PDF)에 있는 모든 텍스트를 읽어, 보이는 순서대로 그대로 추출한다.
한국어와 영어를 모두 정확히 인식하고, 설명·요약·번역 없이 추출한 텍스트만 출력한다.
텍스트가 전혀 없으면 빈 문자열을 반환한다.
"""
