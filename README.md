# 🗨️ kakao persona chatbot

카카오톡 대화 내보내기 파일로 **두 사람의 페르소나와 문체를 학습**해서, 웹에서 어느 쪽 역할로든 1:1 대화를 나눠볼 수 있는 챗봇입니다. 과거 대화를 검색하는 **가상 메모리(RAG)** 가 내장되어 있어, 봇이 "그때 그 얘기"를 기억한 것처럼 대답합니다.

> ⚠️ **개인 대화 데이터는 이 저장소에 포함되지 않으며, 절대 커밋되지 않습니다.**
> `data/`, `build/`, `*.csv` 는 `.gitignore` 로 차단됩니다. 코드만 공개됩니다.

## 방법론

개인 채팅 클론 분야에서 검증된 접근을 조합했습니다.

| 구성요소 | 방법 | 참고 |
|---|---|---|
| 문체 학습 | 통계적 문체 프로파일(어미·ㅋㅋ율·메시지 분절 습관) + 실제 대화 **대량 few-shot 프롬프팅** | [Edward Donner — fine-tuning an LLM on 240k text messages](https://edwarddonner.com/2024/01/02/fine-tuning-an-llm-on-240k-text-messages/), [WhatsApp-Llama](https://github.com/Ads97/WhatsApp-Llama) |
| 가상 메모리 | 대화를 에피소드로 분할 → **BM25 검색**(한국어 어절+바이그램) + 일자별 키워드 타임라인 | RAG 기반 에피소드 메모리 |
| 검증(권장) | 지인 블라인드 튜링 테스트, Burrows' Delta 스타일로메트리 | [ECHO (arXiv 2404.13957)](https://arxiv.org/abs/2404.13957), [faststylometry](https://github.com/fastdatascience/faststylometry) |
| 파인튜닝(선택) | few-shot 뱅크를 MLX LoRA용 JSONL로 내보내기 | `scripts/export_finetune.py` |

## 빠른 시작

```bash
# 0. 의존성
pip install -r requirements.txt

# 1. 카카오톡 대화 내보내기
#    모바일: 채팅방 → 설정 → 대화 내용 내보내기 (CSV/텍스트)
#    → data/ 폴더에 저장 (gitignore됨)

# 2. 페르소나 + 메모리 빌드 (샘플로 먼저 체험 가능)
python scripts/build.py sample_data/sample_chat.csv
python scripts/build.py data/KakaoTalk_Chat_xxx.csv   # 실제 데이터

# 3. 서버 실행 → http://127.0.0.1:8917
python -m kpc.server
```

## LLM 백엔드 (3종 중 택1 — `config.json`)

`config.example.json` 을 `config.json` 으로 복사 후 수정합니다.

| provider | 필요한 것 | 비고 |
|---|---|---|
| `claude-cli` (기본) | [Claude Code](https://claude.com/claude-code) 설치+로그인 | **API 키 불필요**, 구독 인증 사용 |
| `anthropic` | `pip install anthropic` + `ANTHROPIC_API_KEY` | 기본 모델 `claude-opus-5`, 프롬프트 캐싱 및 안전거절 서버측 폴백 적용 |
| `openai-compat` | Ollama / LM Studio / `mlx_lm.server` | 완전 로컬·오프라인 |

## 웹 UI 기능

- **역할 전환** — 내가 A가 되어 B 봇과 대화하거나, 반대로 B가 되어 A 봇과 대화
- **자동 대화** — 두 페르소나 봇이 서로 1:1로 대화하는 셀프플레이 모드
- **🧠 기억 표시** — 봇이 이번 답장에서 떠올린 과거 실제 대화(에피소드)를 함께 표시
- 카카오톡 스타일 말풍선, 실제처럼 짧은 메시지 여러 개로 분할 전송

## 동작 원리

```
내보내기 CSV ─▶ parser ─▶ 턴 병합 ─▶ 에피소드 분할
                              │            │
                    persona (화자별)   memory (공용)
                    · 문체 통계 프로파일   · BM25 에피소드 인덱스
                    · few-shot 예시 뱅크   · 일자별 키워드 타임라인
                              └─────┬──────┘
                                 engine ─▶ 시스템프롬프트(프로파일+예시)
                                          + [기억] 검색결과 + 현재 대화
                                          ─▶ LLM ─▶ ["짧은", "메시지들"]
```

## 파인튜닝으로 확장 (선택)

프롬프트 기반으로 부족하면 Apple Silicon에서 LoRA 파인튜닝:

```bash
python scripts/export_finetune.py "화자이름"
pip install mlx-lm
mlx_lm.lora --model Qwen/Qwen2.5-7B-Instruct --train --data finetune/화자이름 --iters 600
mlx_lm.server --model Qwen/Qwen2.5-7B-Instruct --adapter-path adapters   # openai-compat로 연결
```

## 프라이버시

- 원본 대화·빌드 산출물은 전부 로컬에만 존재합니다 (`.gitignore` 참조)
- `claude-cli`/`anthropic` 프로바이더는 대화 맥락이 Anthropic API로 전송됩니다. 완전 오프라인을 원하면 `openai-compat` + 로컬 모델을 사용하세요
- 타인의 대화 데이터를 사용할 때는 반드시 당사자 동의를 받으세요

## License

MIT
