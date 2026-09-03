# 부업 자동화 시스템 — 1단계 (콘텐츠 엔진 + 텔레그램 승인봇)

> **이게 뭐 하는 건가요?**
> 매일 새벽에 로봇이 오늘의 화젯거리를 모아서 X(트위터)용 글 10개, 스레드용 글 3개를 씁니다.
> 아침 7시 / 점심 12시 / 저녁 8시에 텔레그램으로 글을 보내주고, 당신은 **버튼 세 개(승인/수정/삭제)** 만 누르면 됩니다.
> 바빠서 못 누르면 3시간 뒤 자동으로 승인되어 예약 시간에 알아서 올라갑니다.
> **당신이 하는 일: 하루 3분.**

```
        새벽 06:40                아침7시·점심12시·저녁8시              예약 시간
  ┌──────────────────┐        ┌──────────────────────┐        ┌──────────────┐
  │ 트렌드 수집       │        │ 텔레그램으로 글 전송   │        │ X / 스레드에  │
  │  ↓               │  ───▶  │  [승인] [수정] [삭제]  │  ───▶  │ 자동 발행     │
  │ AI가 글 13개 작성 │        │  3시간 무응답 → 자동승인│        │              │
  └──────────────────┘        └──────────────────────┘        └──────────────┘
                                                                      │
                                                            밤 11시 마감 보고 ◀┘
```

---

## 0. 준비물 (딱 2개만 있으면 시작됩니다)

| 무엇 | 어디서 | 돈 |
|---|---|---|
| **Gemini API 키** (글 쓰는 AI) | aistudio.google.com | **무료 · 카드 등록 불필요** |
| **텔레그램 봇 토큰** | 텔레그램 앱 안에서 | 무료 |
| GitHub 계정 | github.com | 무료 |
| (선택) X API 키 | developer.x.com | **종량제(유료)** — 없어도 시스템은 돕니다 |

**월 고정비 합계: 0원.** (Claude로 바꾸면 약 1만2천원 — 둘 다 제한 5만원 안쪽)

> **왜 무료로 되나요?** 이 시스템은 글 13개를 한 번에 뽑기 때문에 **하루 API 호출이 2~4번뿐**입니다.
> Gemini 무료 한도가 하루 250~1,500회라 20배 이상 여유입니다.
>
> **글맛을 더 올리고 싶다면** `config/settings.yml` 의 `llm.provider` 를 `claude` 로 바꾸고
> `model` 을 `claude-opus-5` 로 적으면 됩니다. 대신 해외결제 카드가 필요하고 월 1만2천원쯤 듭니다.
> 코드는 안 건드려도 됩니다 — **한 줄만 바꾸면 엔진이 통째로 바뀝니다.**

---

## 1단계 — 이 폴더를 내 컴퓨터에서 준비하기 (10분)

### 1-1. 키를 적을 파일 만들기

이 폴더(`auto-income`) 안에 있는 `.env.example` 파일을 복사해서 이름을 **`.env`** 로 바꾸세요.
(윈도우 탐색기에서 Ctrl+C, Ctrl+V 후 이름 변경)

### 1-2. Gemini API 키 받기 (무료, 3분)

1. https://aistudio.google.com/apikey 접속 → **구글 계정으로 로그인** (평소 쓰는 지메일이면 됩니다)
2. **`Create API key`** 또는 **`API 키 만들기`** 버튼 클릭
3. 프로젝트를 고르라고 하면 아무거나 (또는 `Create API key in new project`)
4. `AQ.` 로 시작하는 키가 나옵니다 → **복사**
   (2026년부터 바뀐 새 형식입니다. 예전 안내글의 `AIza...` 도 아직 동작합니다)
5. `.env` 파일을 메모장으로 열어서 이 줄에 붙여넣기:
   ```
   GEMINI_API_KEY=AQ.여기에붙여넣기
   ```

> 카드 등록 없습니다. 결제 화면 안 나옵니다. 무료 한도를 넘으면 그냥 잠깐 막힐 뿐, 요금이 청구되지 않습니다.

<details>
<summary><b>대신 Claude를 쓰고 싶다면 (유료, 글맛 최상) — 눌러서 펼치기</b></summary>

1. `config/settings.yml` 을 열어 두 줄을 고칩니다:
   ```yaml
   llm:
     provider: claude
     model: claude-opus-5
   ```
2. https://console.anthropic.com 가입 → **Billing** → 카드 등록 후 **$10 충전**
   (해외결제 되는 카드여야 합니다. Claude Pro 구독과는 **별개**로 결제됩니다)
3. **Billing → Usage limits** 에서 월 한도를 **$20** 으로 걸어두세요 (과금 사고 방지)
4. **API Keys** → `Create Key` → `sk-ant-...` 복사 (**딱 한 번만 보여줍니다**)
5. `.env` 에 `ANTHROPIC_API_KEY=sk-ant-...` 로 넣고 `GEMINI_API_KEY=` 는 비워두기
6. GitHub Secrets에도 `GEMINI_API_KEY` 대신 `ANTHROPIC_API_KEY` 를 등록

</details>

### 1-3. 텔레그램 봇 만들기

1. 텔레그램에서 **@BotFather** 를 검색해서 대화 시작
2. `/newbot` 이라고 보내기 → 봇 이름과 아이디를 정하라고 하면 아무거나 (예: `내부업봇`, `my_income_bot`)
3. `123456789:AAxx...` 같은 **토큰**을 줍니다. `.env` 에 붙여넣기:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAxx...
   ```
4. 방금 만든 **내 봇을 검색해서 대화창을 열고 "안녕" 이라고 아무 말이나 보내세요.** (이걸 안 하면 봇이 나에게 말을 걸 수 없습니다)

### 1-4. 검사 프로그램 돌리기

이 폴더에서 마우스 오른쪽 클릭 → "터미널에서 열기" 후 아래를 붙여넣기:

```bash
.venv/Scripts/python.exe scripts/setup_check.py
```

- `찾은 CHAT_ID: 123456789` 같은 숫자가 나오면 그 숫자를 `.env` 의 `TELEGRAM_CHAT_ID=` 뒤에 넣고 **다시 한 번 실행**하세요.
- 전부 ✅ 가 나오면 성공입니다. 텔레그램에 테스트 메시지가 도착합니다.

### 1-5. 진짜 글을 만들어 보기

```bash
.venv/Scripts/python.exe src/generate.py
```

```bash
.venv/Scripts/python.exe src/tick.py
```

텔레그램으로 글이 버튼과 함께 오면 **1단계 완성**입니다. 👏

---

## 2단계 — 클라우드에 올려서 24시간 자동으로 돌리기 (20분)

내 컴퓨터가 꺼져 있어도 돌아가게 만듭니다. **무료입니다.**

### 2-1. GitHub 저장소 만들기

1. https://github.com/new 접속
2. Repository name: `auto-income`
3. **Public 을 선택하세요.** ← 중요
   - Public: GitHub Actions 실행 시간 **무제한 무료**
   - Private: 월 2,000분만 무료인데 이 시스템은 그걸 넘깁니다
   - 걱정 마세요. **비밀키는 저장소에 절대 안 올라갑니다** (`.env` 는 `.gitignore` 로 차단됨). 올라가는 건 트윗 초안뿐입니다.
   - 그래도 비공개가 좋다면 Private으로 하고 `config/settings.yml` 아래 방법으로 심장박동을 20분마다로 늦추세요 (README 맨 아래 참고).
4. `Create repository` 클릭

### 2-2. 내 폴더를 GitHub로 올리기

터미널에서 아래를 **한 줄씩** 붙여넣기 (마지막 줄의 `내아이디` 는 본인 GitHub 아이디로 바꾸세요):

```bash
git init -b main
```

```bash
git add . && git commit -m "부업 자동화 시스템 1단계"
```

```bash
git remote add origin https://github.com/내아이디/auto-income.git
```

```bash
git push -u origin main
```

로그인 창이 뜨면 GitHub 계정으로 로그인하세요.

### 2-3. 비밀키를 GitHub에 등록하기

내 저장소 페이지 → 위쪽 **Settings** → 왼쪽 아래 **Secrets and variables** → **Actions** → `New repository secret`

아래 3개를 하나씩 등록합니다 (이름은 **정확히** 아래 그대로):

| Name | Secret (값) |
|---|---|
| `GEMINI_API_KEY` | `.env` 에 넣었던 `AQ.` 로 시작하는 키 (Claude를 쓴다면 `ANTHROPIC_API_KEY`) |
| `TELEGRAM_BOT_TOKEN` | `.env` 에 넣었던 봇 토큰 |
| `TELEGRAM_CHAT_ID` | `.env` 에 넣었던 숫자 |

### 2-4. 자동 실행 켜기

1. 저장소 위쪽 **Actions** 탭 클릭 → `I understand my workflows, go ahead and enable them` 클릭
2. 왼쪽에서 **`1. 오늘의 글 만들기`** 클릭 → 오른쪽 **`Run workflow`** 버튼 클릭 (테스트용 수동 실행)
3. 1~2분 뒤 초록색 ✅ 가 뜨면 성공
4. 왼쪽에서 **`2. 심장박동 (10분마다)`** 도 한 번 `Run workflow` → **텔레그램으로 글이 옵니다**

이제 끝났습니다. 내일 아침 7시부터는 알아서 돌아갑니다.

---

## 3단계 (선택) — X에 완전 자동으로 올리기

**X API 키가 없어도 시스템은 완전히 돌아갑니다.** 발행 시간이 되면 텔레그램이 글을 보내면서
**`📮 X에 올리기`** 버튼을 같이 줍니다. 누르면 X 앱이 열리고 **글이 이미 채워져 있습니다.**
사진을 붙이고 싶으면 그 자리에서 첨부하고 "게시"만 누르면 됩니다. (글 하나에 약 15초)

### ⚠️ X API 무료 티어는 없어졌습니다

**2026년 2월 6일부로 X는 무료 티어 신규 가입을 중단**했습니다.
신규 개발자는 **종량제(Pay Per Use)** 로만 가입됩니다. 기존 무료 사용자는 종량제로 이관되며
$10 크레딧을 받았습니다.

즉 완전 자동 발행은 **유료**입니다. 서두를 필요 없습니다 — 위 반자동 방식으로 충분히 운영되고,
요금을 확인한 뒤 결정하셔도 됩니다.

### 그래도 붙이려면

1. https://developer.x.com/en/portal/dashboard → X 계정으로 로그인
2. 신청서의 용도 설명란에는 **사실만** 적습니다. (예시는 아래)
3. 앱 → **Settings** → **User authentication settings** → App permissions 를 **`Read and write`** 로 변경
4. **권한을 바꿨으면 Access Token 을 반드시 `Regenerate`(재발급)** ← 가장 흔한 실패 원인
5. **Keys and tokens** 탭에서 4개 복사 → 폴더의 **`X키넣기.bat`** 더블클릭해서 붙여넣기
6. GitHub Secrets 에도 같은 4개 등록: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`

용도 설명란에 쓸 문구 (우리 시스템의 실제 동작과 일치합니다):

```
I use the X API to manage my own single personal account. Posts are drafted and
reviewed by me, approved through a private Telegram bot, and then published
automatically at scheduled times. I only use the create-post and media-upload
endpoints. I do not collect, analyze, or store other users' data, do not display
X content outside of X, and do not share or resell any data with third parties.
```

키를 넣으면 **텔레그램에서 붙인 사진까지 그대로 자동 발행**됩니다.
`config/settings.yml` 의 `daily_publish_cap` 이 하루 발행 상한을 지켜 과금 사고를 막습니다.

---

## 🖼 사진 붙이기

글 카드 아래 **`🖼 사진 붙이기`** 버튼을 누르고, 갤러리에서 사진을 골라 **그냥 보내면** 됩니다.
봇이 사진과 글을 합쳐서 다시 보여줍니다. 마음에 안 들면 `🖼 사진 바꾸기`로 교체하면 됩니다.

- 사진은 저장소에 저장되지 않습니다 (용량 문제). 텔레그램에 보관되고 발행 순간에만 가져옵니다
- **X API가 있으면** 글+사진이 자동으로 올라갑니다
- **X API가 없으면** 사진은 참고용이고, X 앱에서 직접 첨부하셔야 합니다

> ⚠️ **남의 사진을 쓰지 마세요.** 뉴스 사진·언론사 영상은 크롭하거나 문구를 얹어도 저작권 침해입니다.
> DMCA 신고가 쌓이면 계정이 영구정지되고, X 수익화(광고 배분)는 오리지널 콘텐츠가 자격 요건이라
> 무단 전재 계정은 500만 노출을 채워도 정산을 못 받습니다.
> 직접 찍은 사진, 직접 만든 이미지, 라이선스가 확인된 이미지만 쓰세요.

---

## 매일 어떻게 쓰나요?

| 시간 | 무슨 일이 | 내가 할 일 |
|---|---|---|
| 새벽 6:40 | 로봇이 오늘 X 글 10개를 씀 | 없음 |
| 아침 7:00 | 텔레그램에 4개 도착 | 출근길에 버튼 누르기 (1분) |
| 점심 12:00 | 3개 도착 | 점심시간에 버튼 (1분) |
| 저녁 20:00 | 3개 도착 | 버튼 (1분) |
| 밤 23:00 | 하루 마감 보고 도착 | 읽기만 |

**바빠서 못 눌렀다면?** 3시간 뒤 자동 승인되어 그대로 올라갑니다.

단, **📰 오늘의 이슈**와 **🛒 생활 제품** 은 자동 승인되지 않습니다. 사실이 틀리면 계정이 위험하고,
제품 글에는 나중에 제휴 링크가 붙어 돈이 걸리기 때문입니다. 하루 5개 정도는 눈으로 보고 승인해 주세요.
믿을 만해지면 `config/pillars.yml` 의 `needs_check: true` 를 `false` 로 바꾸면 자동화됩니다.

### 텔레그램에서 쓸 수 있는 명령

| 입력 | 뜻 |
|---|---|
| `/status` | 오늘 현황 보기 |
| `/ok` | 대기 중인 글 전부 승인 |
| `/stop` | 오늘 남은 글 전부 취소 |

### ✏️ 수정 버튼을 누르면

말로 지시하면 AI가 고쳐서 다시 보여줍니다.
- `더 짧게` / `더 담담하게` / `회의 얘기로 바꿔줘`
- 직접 쓴 글로 통째로 바꾸려면 맨 앞에 `=` 를 붙이세요 → `=내가 직접 쓴 문장`

---

## 뭔가 잘못됐을 때

| 증상 | 해결 |
|---|---|
| 텔레그램에 아무것도 안 옴 | GitHub → Actions 탭에서 빨간 ❌ 가 있는지 확인. 클릭하면 이유가 한글로 나옵니다 |
| "TELEGRAM_CHAT_ID" 오류 | 내 봇에게 먼저 아무 말이나 보낸 뒤 `setup_check.py` 재실행 |
| Gemini `429` 오류 | 무료 한도를 잠깐 넘었습니다. 10분 뒤 자동으로 다시 시도합니다 |
| Gemini `400 API key not valid` | 키를 다시 복사하세요. `AQ.` (신형) 또는 `AIza` (구형) 로 시작합니다 |
| Claude 오류 | console.anthropic.com → Billing 에 잔액이 있는지 확인 |
| X 발행 실패 (403) | X 앱 권한을 `Read and write` 로 바꾸고 **Access Token 재발급** |
| 글이 다 비슷비슷함 | `config/topics.yml` 에 주제를 더 추가하세요 |
| 글 톤이 마음에 안 듦 | `config/prompts/x.md` 를 고치세요. **코드가 아니라 그냥 글입니다** |

> **60일 주의:** GitHub는 저장소에 60일간 사람이 아무 활동을 안 하면 자동 실행을 꺼버립니다.
> 두 달에 한 번 정도 Actions 탭에서 아무 워크플로나 `Run workflow` 를 눌러주면 됩니다.
> (꺼지면 GitHub가 이메일로 알려줍니다.)

---

## 설정 바꾸기 — `config/settings.yml`

코드는 건드릴 필요 없습니다. 이 파일의 숫자만 바꾸세요.

```yaml
llm:
  provider: gemini                # gemini(무료) 또는 claude(유료)  ← 여기 한 줄로 엔진 교체
  model: gemini-2.5-flash         # claude 라면 claude-opus-5

auto_approve_after_minutes: 180   # 자동 승인까지 기다리는 시간(분). 0 = 자동승인 끔
slots:
  morning: "07:00"                # 알림 시간
channels:
  x:
    slots: { morning: 4, lunch: 3, evening: 3 }   # 하루 몇 개
    daily_publish_cap: 12                          # 하루 최대 발행 (안전장치)
```

**Private 저장소로 하고 싶다면**: `.github/workflows/2-tick.yml` 의 `5-59/10` 을 `5-59/20` 으로 바꾸세요 (심장박동 20분마다 → 무료 시간 안에 들어옵니다).

---

## 폴더 구조 (궁금할 때만 보세요)

```
auto-income/
├─ .env                  ← 내 비밀키 (절대 GitHub에 안 올라감)
├─ 키넣기.bat           ← 더블클릭하면 키를 물어보고 자동 저장
├─ X키넣기.bat          ← X 자동발행 키 4개 입력용
├─ config/
│   ├─ settings.yml      ← 시간·개수·믹스비율·AI엔진  ⭐
│   ├─ pillars.yml       ← 카테고리별 말투와 금지규칙  ⭐ 글 방향을 바꾸는 곳
│   └─ topics.yml        ← 카테고리별 글감 목록  ⭐
├─ src/
│   ├─ llm.py            ← AI 엔진 갈아끼우는 부분 (gemini / claude)
│   ├─ news.py           ← 실시간 뉴스 글감 (제목만 가져옴)
│   ├─ generate.py       ← 글 만드는 두뇌
│   ├─ tick.py           ← 알림/승인/발행 심장
│   ├─ report.py         ← 밤 11시 보고
│   └─ channels/         ← X, 스레드에 실제로 올리는 부분
├─ data/                 ← 글 목록이 저장되는 곳 (자동)
└─ .github/workflows/    ← 클라우드 자동 실행 설정
```

---

## 다음 단계 (아직 안 만듦)

- **3. 수익 연결** — 쿠팡파트너스 제휴 링크 자동 삽입 ← 키 보유, 다음 작업
- **4. 성과 루프** — 조회·클릭 집계 → 하위 30% 패턴 폐기, 상위 20% 변형 재생산
- **5. 대시보드** — 구글시트에 일별 수익·비용·순익 자동 기록

1단계가 3일 이상 안정적으로 돌아가는 걸 확인한 뒤에 진행합니다.
