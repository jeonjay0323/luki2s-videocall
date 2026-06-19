# LUKI2DS — AI 영상통화

루키즈(LUKI2DS) 브랜드의 실시간 AI 영상통화. 연습생 아바타와 한국어로 영상통화를 한다.

피그마 `videocall` 화면 디자인을 그대로 입힌 웹 UI(`web/`)에서 **CONNECT**를 누르면, AI 연습생이 `어 뭐야! 누구세요?`로 먼저 말을 걸고 대화가 시작된다.

## 파이프라인 (`bot.py`)

| 단계 | 사용 |
|------|------|
| STT | Google Cloud Speech-to-Text (한국어) |
| LLM | Vertex AI Gemini 2.5 Flash (OpenAI 호환 엔드포인트) |
| TTS | ElevenLabs (`eleven_turbo_v2_5`) |
| 얼굴 | Simli 영상 아바타 |
| 전송 | WebRTC (pipecat smallwebrtc) |

## 실행

```bash
# 1) 의존성
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2) 키 설정
cp .env.example .env   # 값 채우기

# 3) Google 인증 (Vertex/STT)
gcloud auth application-default login

# 4) 봇 실행
GRPC_DNS_RESOLVER=native ./venv/bin/python bot.py --transport webrtc
```

- 브라우저에서 **http://localhost:7860/luki/** 접속 → 마이크 허용 → CONNECT
- 기본 pipecat UI는 http://localhost:7860/client/

### `GRPC_DNS_RESOLVER=native` 가 필요한 이유

macOS의 `/etc/resolv.conf`에 IPv6 링크로컬 네임서버만 있는 환경에서는 gRPC 기본 리졸버(c-ares)가 DNS를 못 풀어 Google STT가 실패한다. native(getaddrinfo) 리졸버로 강제하면 해결된다.

## 브랜드 사이트 (`site/`)

LUKI2DS 브랜드북 데스크톱 웹사이트 (피그마 → 단일 HTML). 정적 파일이라 그냥 열면 된다.

- `site/index.html` — 브랜드 가이드(01~08: Intro·Traits·Logo·Color·Typo·Application·Service·Plan)
- `site/demo.html` — 워프 로딩 진입 화면 → `site/call.html` 영상통화 화면(피그마 `videocall` 목업)

```bash
open site/index.html        # 브랜드북
```

## 구조

```
bot.py            파이프라인 + /luki 정적 서빙
web/index.html    영상통화 UI (피그마 videocall 디자인 + pipecat JS SDK, 봇 연동)
web/assets/       카드 이미지·아이콘
site/             LUKI2DS 브랜드북 사이트 (정적)
requirements.txt
.env.example
```
