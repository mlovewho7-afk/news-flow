import os

import requests

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"


def translate_to_ko(text: str) -> str | None:
    api_key = os.environ.get("DEEPL_API_KEY")
    if not api_key:
        return None
    try:
        response = requests.post(
            DEEPL_API_URL,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            data={"text": text, "target_lang": "KO"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data["translations"][0]["text"]
    except Exception:
        # 의도적으로 광범위하게 잡는다 — 이 함수는 어떤 이유로도 예외를 밖으로
        # 내보내지 않는다는 게 호출자와의 계약이다(설계 문서에서 명시적으로
        # 결정된 사항이지, 실수로 넓게 잡은 게 아니다). 원인별로 다르게 처리하지
        # 않고 전부 None으로 뭉개는 대신, 호출자가 성공/실패 개수를 세어 로그로
        # 남긴다(Task 2 참고).
        return None
