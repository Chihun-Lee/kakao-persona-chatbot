# 페르소나 말투 변환

전하고 싶은 말을 적으면 고른 사람의 말투로 바꿔 주는 웹 도구입니다. 카카오톡 내보내기와 보낸 메일에서 페르소나를 만들고, API로 변환합니다. 띄어쓰기를 붙이거나 마침표를 빼는 정도의 작은 실수도 넣을 수 있습니다.

이전의 페르소나 챗봇 코드는 지웠습니다. 필요하면 태그 `v0.1-chatbot`에서 볼 수 있습니다.

## 하는 일

1. 페르소나를 고릅니다. 공개 예시는 가상 인물 `한도윤`입니다.
2. 메일, 업무 카톡, 친구 카톡 중 어디에 쓸 글인지 고릅니다.
3. 전할 말을 적으면 그 사람의 말투로 바뀝니다.
4. 실수 정도(없음, 아주 가끔, 가끔, 자주)에 따라 흐트러짐이 들어가고, 바뀐 곳이 표시됩니다.

## 실수가 들어가는 방식

| 종류 | 예 | 기준 |
|---|---|---|
| 오타 | 부탁드립니다 → 부탇드립니다 | 그 사람이 실제로 냈던 오타를 먼저, 다음으로 두벌식 자판 실수 |
| 붙여 쓰기 | 할 수 있습니다 → 할수 있습니다 | 그 사람 글에서 잰 빈도 |
| 마침표 | 있었다가 없었다가 | 채널별로 잰 비율 |
| 맺음말 | 한도윤 드림 → 도윤듦 (아주 드물게) | 페르소나에 적은 변형 |

숫자, 날짜, 금액, 영문, 메일 주소, 호칭이 붙은 이름은 바꾸지 않습니다. 원문의 숫자가 결과에서 사라지면 경고가 나옵니다. 욕처럼 보이는 오타는 만들지 않습니다.

사람이 쓴 글처럼 보이게 하지만, 구별되지 않는다고 보장하지는 않습니다. 보내기 전에 직접 읽어 보세요.

## 실행

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...      # 또는 ant auth login
cp config.example.json config.json
python -m kpc.server              # http://127.0.0.1:8917
```

키 없이 내 컴퓨터에서만 시험하려면 `config.json`의 `provider`를 `claude-cli`로 바꿉니다. Claude Code 로그인이 필요합니다.

## 내 페르소나 만들기

```bash
python scripts/build_persona.py --id me --name 홍길동 --me 길동 \
  --kakao-work "data/work/*.csv" --kakao-friend "data/friend/*.csv" \
  --mail-jsonl data/sent.jsonl --mail-field text \
  --rare-signoff "길동듦" --out personas/private/me.json
```

- 본인이 보낸 글만 씁니다. 상대방이 쓴 글은 통계에도 예문에도 들어가지 않습니다.
- 전화번호, 계좌, 메일 주소, 사람 이름을 가리고, 민감한 낱말이 있는 문장은 예문에서 뺍니다.
- `personas/private/`는 Git에 올라가지 않습니다.
- Claude Code를 쓴다면 `skill/voice-builder`를 스킬 폴더에 복사해 대화로 진행할 수 있습니다.

## 모두에게 공개하기

공개 모드에서는 `public: true` 페르소나만 보이고, 시간당 횟수와 하루 총량을 제한하며, 입력한 글을 저장하지 않습니다. 비용은 키 주인에게 청구됩니다.

```bash
# 내 컴퓨터를 잠시 공개
KPC_CONFIG=config.public.json python -m kpc.server
cloudflared tunnel --url http://127.0.0.1:8917

# 또는 서버에 배포
docker build -t persona-voice .
docker run -p 8917:8917 -e ANTHROPIC_API_KEY=... persona-voice
```

## 지켜 주세요

- 본인의 말투, 허락받은 사람의 말투, 가상 인물만 쓰세요.
- 다른 사람인 척 메시지를 보내거나 속여서 돈이나 정보를 얻는 데 쓰면 안 됩니다.
- 본인 페르소나를 공개하면 누구나 그 말투로 글을 만들 수 있습니다. 공개 전에 한 번 더 생각해 주세요.

## 라이선스

MIT
