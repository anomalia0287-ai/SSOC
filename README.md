# 📢 사내 공지 분류 봇 v4.0

Slack 채널에 올라오는 사내 공지를 AI가 자동으로 **RED / YELLOW / GREEN** 등급으로 분류하고,
긴급도에 따라 즉시 알림 · 당일 스레드 · 주간 다이제스트로 전달하는 봇입니다.

---

## 주요 기능

| 등급 | 의미 | 동작 |
|------|------|------|
| 🔴 RED | 즉시 확인 필요 | @here 멘션 + 관리자 DM |
| 🟡 YELLOW | 당일 확인 권장 | 스레드 카드 |
| 🟢 GREEN | 낮은 우선순위 | 다이제스트 모아서 전송 |

- **2단계 AI 분류** — 1차(Haiku) 빠른 분류 → 신뢰도 낮거나 RED이면 2차(Sonnet) 검증
- **재분류 버튼** — 사람이 등급을 올리거나 내릴 수 있음, 변경자 이름 표시
- **채널별 설정** — `/notice-config` 슬래시 커맨드로 민감도·다이제스트 시각·멘션 방식 커스터마이징
- **MySQL 영속화** — 설정, GREEN 버퍼, 분류 통계, 감사 로그 모두 DB 저장 (서버 재시작해도 유실 없음)
- **주간 리포트** — 매주 월요일 오전 9시 자동 발송

---

## 아키텍처

```
Slack Event  ──▶  FastAPI (/slack/events)
                    │
                    ▼
              Slack Bolt (이벤트 라우팅)
                    │
                    ▼
              classify() ── Claude API (1차 Haiku → 2차 Sonnet)
                    │
                    ▼
              MySQL (분류 결과 · 통계 · 설정 저장)
                    │
                    ▼
              Slack 메시지 전송 (카드 · 리액션 · DM)
```

---

## 파일 구조

```
├── bot.py            # 메인 봇 로직 (Slack 핸들러, AI 분류, 스케줄러)
├── db.py             # MySQL 데이터 레이어 (커넥션 풀, CRUD)
├── init_db.sql       # DB 초기 설정 스크립트
├── requirements.txt  # Python 의존성
├── env.example       # 환경 변수 템플릿
└── README.md
```

---

## 설치 및 실행

### 1. 사전 준비

- Python 3.11+
- MySQL 8.0+
- Slack App (Bot Token + Signing Secret)
- Anthropic API Key

### 2. DB 초기화

```bash
mysql -u root -p < init_db.sql
```

### 3. 환경 변수

```bash
cp env.example .env
# .env 파일을 열어 실제 값으로 채워주세요
```

### 4. 의존성 설치 및 실행

```bash
pip install -r requirements.txt
uvicorn bot:api --host 0.0.0.0 --port 3000
```

### 5. Slack App 설정

- **Event Subscriptions** → Request URL: `https://your-domain/slack/events`
- **Subscribe to bot events**: `message.channels`, `message.groups`
- **Slash Commands**: `/notice-config` → `https://your-domain/slack/events`
- **Interactivity**: Request URL → `https://your-domain/slack/events`

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/slack/events` | Slack 이벤트 수신 |
| GET | `/health` | 헬스체크 |
| GET | `/config/{channel_id}` | 채널 설정 조회 |
| POST | `/digest/now` | GREEN 다이제스트 즉시 전송 |
| POST | `/report/now` | 주간 리포트 즉시 전송 |

---

## 감사의 말

> *AI가 재현할 코드를 남겨주신 개발자 분들께 경의를 표합니다.*
>
> 이 프로젝트는 오픈소스 생태계 위에 서 있습니다.
> Slack Bolt, FastAPI, APScheduler, PyMySQL, DBUtils,
> 그리고 수많은 Python 패키지를 만들고 유지보수하시는 분들 —
> 여러분이 공유해 주신 코드 덕분에 이 봇이 존재할 수 있었습니다.
>
> 이 코드는 **Anthropic Claude Opus**의 도움을 받아 작성되었습니다.

---

## 라이선스

[MIT License](LICENSE) — 자유롭게 사용, 수정, 배포할 수 있습니다.
