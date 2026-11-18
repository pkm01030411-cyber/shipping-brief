# ⚓ 해운물류 데일리

코리아쉬핑가제트·카고뉴스에 매일 올라오는 기사를 자동으로 모아 Claude(`claude-sonnet-5-5`)가 요약하고,
"오늘 꼭 읽을 3건 + 나머지 관련도순"으로 정리해 GitHub Pages에 올려주는 개인 브리핑 사이트입니다.

```
매일 18:30 KST (GitHub Actions)
  ├─ 1. collect    KSG 카테고리 크롤링 + 카고뉴스 RSS  →  data/YYYY-MM-DD.json
  ├─ 2. summarize  Claude 요약·관련도·Top 3·지켜볼 포인트 →  (같은 파일에 추가)
  ├─ 3. build      Jinja2 템플릿으로 정적 HTML 생성      →  site/
  └─ 4. deploy     data/ 커밋 + GitHub Pages 배포
```

서버 없음, 운영비 0원 (API 비용만: 하루 30건 요약 기준 월 1~2천 원 수준).

---

## 1. 처음 설정 (10분)

### ① GitHub 저장소 만들기
1. GitHub에서 새 저장소 생성 (이름 예: `shipping-brief`, Public 또는 Private 모두 가능)
2. 이 폴더를 통째로 올리기

```bash
cd shipping-brief
git init
git add .
git commit -m "init: shipping brief"
git branch -M main
git remote add origin https://github.com/<내아이디>/shipping-brief.git
git push -u origin main
```

### ② Anthropic API 키 등록
1. https://console.anthropic.com → API Keys → 키 발급
2. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
3. Name: `ANTHROPIC_API_KEY`, Secret: 발급받은 키

### ③ GitHub Pages 켜기
저장소 → **Settings → Pages → Build and deployment → Source: `GitHub Actions`** 선택

### ④ 첫 실행
저장소 → **Actions → "Daily shipping brief" → Run workflow**
2~3분 뒤 `https://<내아이디>.github.io/shipping-brief/` 에서 확인.

이후엔 매일 저녁 18:30에 자동으로 돌아갑니다 (그날 낮에 올라온 기사를 저녁에 정리).

> 샘플 데이터 `data/2026-11-16.json`이 들어 있습니다. 첫 실제 실행 후 지워도 되고 그대로 둬도 됩니다.

---

## 2. 로컬에서 돌려보기

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # Windows: set ANTHROPIC_API_KEY=sk-ant-...

python run.py                           # 수집 → 요약 → 빌드
python -m http.server -d site 8000      # http://localhost:8000 에서 확인
```

유용한 옵션:

| 명령 | 설명 |
|---|---|
| `python run.py --build-only` | 사이트만 다시 생성 (템플릿/CSS 수정 시) |
| `python run.py --skip-collect` | 수집 생략, 요약·빌드만 |
| `python run.py --resummarize` | 오늘 기사 요약을 처음부터 다시 |
| `python run.py --date 2026-11-16` | 특정 날짜 파일로 작업 |
| `python -m pytest tests` | 파서 테스트 |

API 키가 없으면 **오프라인 모드**로 동작합니다 (본문 첫 문단을 요약 대신 사용). 크롤러·사이트만 확인할 때 편합니다.

---

## 2.5 사이트 기능

| 기능 | 설명 |
|---|---|
| 대문(홈) | 오늘의 핵심·읽기 진행·연속 읽은 날·주간 리뷰·7일 키워드 흐름을 한눈에. 브리핑 본문은 "오늘"(`today.html`) |
| 용어 해설 · 인사이트 | 기사마다 Sonnet이 업계 용어 0~3개를 한 줄 해설(▸), "어떻게 읽어야 하나" 인사이트 한 줄. 하루치 용어는 "오늘의 용어"에 모임 |
| 정세 대시보드 | `/geo.html` — 기사마다 Sonnet이 지역·국가·해상 요충지·동인·영향(−2~+2)을 태깅. 요충지 위험 보드, 오늘의 세계 지도(당일 기사를 대표 지역 10곳에 점으로, 점을 누르면 기사 목록), 지역×주 히트맵, 동인 추이, 국가 상위 10. 기사 카드의 ◎ 칩을 누르면 해당 요충지·국가로 이동 |
| 읽음 체크 · 진행 바 | 기사 카드의 ☐ 를 누르거나 원문을 열면 읽음 처리. 상단 바에 "n / 17 읽음". 브라우저(localStorage)에 저장 |
| 출처 필터 · 읽은 것 숨기기 | 상단 칩. 설정은 다음 방문에도 유지 |
| 낮은 관련도 접기 | 관련도 1~2 기사는 기본 접힘, "더 보기"로 펼침 |
| 관심 키워드 배지 | `config.yaml`의 `highlight_keywords`가 등장한 기사에 배지 + 상단 "포워더 1 · 파업 1" 칩 |
| 태그 페이지 | 태그 클릭 → 전체 아카이브에서 같은 태그 기사 모아보기 (`/tag/`, `/tags.html`) |
| 스크랩 | ☆ 로 모아두고 `/scrap.html`에서 Markdown·JSON으로 내보내기 (자소서·면접 자료함) |
| 주간 리뷰 | 매주 월요일 지난 7일을 Sonnet이 종합: 흐름·테마·꼭 기억할 5건·면접용 질문 (`/weekly.html`) |
| 키보드 | `j`/`k` 이동, `x` 읽음, `s` 스크랩, `o` 원문, `?` 도움말 |
| PWA | 폰 브라우저에서 "홈 화면에 추가"하면 앱처럼 실행. 오프라인에서도 마지막 브리핑 열람 |
| RSS | `/feed.xml` — RSS 리더나 Slack에 연결 가능 |

> 읽음·스크랩 상태는 서버가 없어 **브라우저별**로 저장됩니다. 폰과 PC는 따로예요. 스크랩은 내보내기로 백업하세요.

주간 리뷰를 지금 바로 보고 싶으면 Actions → Run workflow에서 **weekly** 체크. 프롬프트를 바꾼 뒤 오늘 요약을 다시 만들려면 **resummarize** 체크. 정세 태깅이 없는 과거 기사를 채우려면 **backfill_geo** 체크(1회).

## 2.6 모바일(안드로이드) 화면

같은 페이지가 폰(폭 640px 이하 + 터치)에서만 앱처럼 바뀝니다. 데스크톱 화면은 그대로입니다.
`static/mobile.css`(미디어 쿼리로만 로드)와 `static/mobile.js`(모바일이 아니면 바로 종료)에 모여 있습니다.

| 기능 | 설명 |
|---|---|
| 하단 내비 | 홈 · 오늘(안 읽은 수) · 정세 · 스크랩(개수) · 더보기(주간·태그·지난·설정) |
| 앱 바 | 페이지 제목·날짜, 내리면 숨고 올리면 나타남, 오늘 화면엔 읽기 진행 막대 |
| 뒤로 가기 | 시트·선택 모드가 열려 있으면 안드로이드 뒤로 가기(제스처 포함)가 그것만 닫음 |
| 기사 카드 | 요약 3줄 + '해설 보기', 하단 읽음·스크랩·공유·원문. 오른쪽 스와이프 = 읽음, 왼쪽 = 스크랩 |
| 필터 | 오른쪽 아래 버튼 → 시트 (출처·읽은 것 숨기기·낮은 관련도·모두 읽음) |
| 정세 | 지도 점·지역 칩·요충지 → 바텀 시트(반 → 끌어 올리면 전체), 히트맵은 최근 4주 + '8주 보기' |
| 스크랩 | 길게 눌러 여러 개 선택 → 공유(Markdown 파일로 카카오톡·노션) · 삭제(되돌리기) |
| 설정 | 글자 크기 · 테마(시스템/라이트/다크) · 카드 기본 펼침 · 햅틱 |
| 앱 설치 | 대문에 '홈 화면에 추가' 배너, 아이콘 길게 누르면 오늘·정세·스크랩 바로가기 |
| 오프라인 | 핵심 페이지와 최근 7일 브리핑을 미리 저장, 오프라인이면 상단에 마지막 업데이트 시각 |
| 당겨서 새로고침 | 홈 화면 앱으로 실행했을 때 오늘 화면 맨 위에서 당기기 |

**푸시 알림은 넣지 않았습니다.** 안드로이드 PWA도 웹 푸시를 받을 수 있지만, 알림을 보내려면 구독 정보를 저장하고
푸시 서비스에 요청하는 서버가 필요합니다. 이 사이트는 서버 없이 GitHub Pages로만 돌아가기 때문에 범위에서 뺐습니다.

### 실제 폰에서 확인하기
1. 안드로이드 크롬으로 사이트 열기 → 대문의 '홈 화면에 추가' (또는 크롬 메뉴 ⋮ → 홈 화면에 추가)
2. 홈 화면의 닻 아이콘을 길게 눌러 오늘 · 정세 · 스크랩 바로가기가 뜨는지
3. 앱으로 열어 오늘 화면 맨 위에서 아래로 당겨 새로고침
4. 기사 카드를 좌우로 밀어 읽음·스크랩, 정세에서 지도 점 → 시트 → 뒤로 가기 제스처로 닫히는지
5. 비행기 모드로 앱을 열어 최근 브리핑과 상단의 '오프라인' 띠
6. 휴대폰 설정 → 디스플레이 → 글자 크기를 키워도 화면이 깨지지 않는지

## 2.7 러시아·유라시아 섹션 (`eurasia.html`)

러시아·중앙아시아·코카서스·북극 정세 기사를 매일 골라 **한국어로 번역·요약**합니다. 해운물류 브리핑과 같은 워크플로에서 이어서 실행되고, 실패해도 해운물류 브리핑 배포에는 영향이 없습니다.

| 소스 | 수집 방식 | 출처 시각 라벨 |
|---|---|---|
| The Moscow Times | RSS | 독립 언론 · 암스테르담 |
| Meduza (영어판) | RSS (본문 포함) | 독립 언론 · 리가 |
| Eurasianet | RSS | 중앙아·코카서스 전문지 · 미국 |
| The Times of Central Asia | RSS (본문 포함) | 중앙아 지역 매체 |
| The Barents Observer | 홈 목록 + 기사 메타 (RSS 없음) | 북극 독립 언론 · 노르웨이 |
| PortNews (러시아어판) | 날짜별 목록 (RSS 없음) | 러시아 해운 업계지 · 상트페테르부르크 |
| KOTRA 해외시장뉴스 | 국가별 목록 API (RSS 중지됨) | 한국 정부기관 · 무역관 — **주간 리뷰 전용** |

모두 GitHub Actions 서버에서 접속되는 것을 확인했습니다(2026-11-18).

**하루 흐름**
1. 소스별 새 기사 후보를 모읍니다 (최근 40시간, 이미 본 URL 제외, 소스별 상한). 보통 하루 80~120건.
2. 제목·리드만으로 Claude가 관련도(1~5)와 한국어 제목을 매깁니다 — 60건당 호출 1번.
3. **관련도 3 이상 상위 15건**만 본문을 가져와 번역·요약합니다. 3점 이상이 10건이 안 되면 2점짜리로 10건까지 채웁니다(1점은 넣지 않음).
4. 오늘의 헤드라인·흐름·Top 3·지켜볼 포인트를 만듭니다.
5. 선별에서 빠진 후보는 "그 밖의 기사"에 한국어 제목만 남깁니다.

카드에는 번역 제목 아래 **원제**, 요약, 의미, **물류·무역** 영향, 인사이트, 용어, **출처 시각** 라벨이 붙습니다. 같은 날 백업 실행에서 새 기사가 없으면 API를 부르지 않습니다.

**주간 리뷰 (`eurasia-weekly.html`)** — 월요일 저녁, 지난 7일의 유라시아 기사와 KOTRA 러시아·카자흐스탄·우즈베키스탄·아제르바이잔·벨라루스·키르기스스탄·조지아·우크라이나 무역관 뉴스를 묶어 흐름, 무역관 소식 요약과 실무 시사점, 면접용 질문을 정리합니다.

설정은 `config.yaml`의 `eurasia:` — 관심사(관련도 기준), 하루 게재 건수(`min_daily`/`max_daily`), 소스 켜고 끄기, KOTRA 국가 목록. 수동 실행: `python run.py --eurasia-only`, 다시 요약: Actions의 "Run workflow"에서 `eurasia_resummarize` 체크.

## 3. 내 입맛에 맞게 바꾸기 — `config.yaml`

가장 자주 손댈 곳은 **관심사**입니다. 관련도 점수와 Top 3 선정에 그대로 반영됩니다.

```yaml
summarize:
  interests:
    - "컨테이너 정기선사 (ONE, HMM, 머스크 …)와 얼라이언스 동향"
    - "해상 운임 지수 (SCFI, KCCI, BDI 등)"
    - ...
```

그 외:
- `collect.window_hours` — 몇 시간 이내 기사를 모을지 (기본 30시간, 하루 1회 실행 기준 여유분)
- 실행 시각은 `.github/workflows/daily.yml`의 cron (UTC 기준, 현재 09:30 = 18:30 KST)
- `collect.max_per_source` — 소스별 상한 (비용 상한 역할)
- `sources.ksg.categories` — KSG에서 볼 카테고리
- `summarize.batch_size` / `body_chars` — API 호출당 기사 수, 본문 전달 길이
- `site.title` / `tagline` — 사이트 이름

요약 톤·규칙을 바꾸고 싶으면 `src/summarize.py` 상단의 `SYSTEM` 프롬프트를 수정하세요.

---

## 4. 구조

```
shipping-brief/
├─ run.py                  # 파이프라인 진입점
├─ config.yaml             # 설정 (관심사, 소스, 모델)
├─ src/
│  ├─ common.py            # 설정·HTTP·날짜·데이터 파일 유틸
│  ├─ collect.py           # 1단계 수집
│  ├─ summarize.py         # 2단계 Claude 요약 (tool-use 구조화 출력)
│  ├─ build_site.py        # 3단계 정적 사이트 생성
│  └─ sources/
│     ├─ ksg.py            # 코리아쉬핑가제트 크롤러 (RSS 없음 → 목록 페이지)
│     └─ cargonews.py      # 카고뉴스 (RSS + 본문)
├─ templates/              # Jinja2 HTML
├─ static/style.css
├─ data/YYYY-MM-DD.json    # 하루치 기사 + 요약 (git에 커밋되어 아카이브가 됨)
├─ tests/test_parsers.py
└─ .github/workflows/daily.yml
```

### 데이터 파일 한 건의 모양
```json
{
  "date": "2026-11-16",
  "brief": { "headline": "…", "overview": "…", "top": [{"id": "ksg:148502", "reason": "…"}], "watch": ["…"] },
  "articles": [
    { "id": "ksg:148502", "source_name": "코리아쉬핑가제트", "title": "…", "url": "…",
      "published": "2026-11-16T09:07:00+09:00", "body": "…",
      "summary": "…", "why": "…", "tags": ["항만파업"], "relevance": 5 }
  ]
}
```

---

## 5. 소스 추가하기

`src/sources/` 에 모듈 하나 만들고 `collect(cfg, http, cutoff, known) -> list[Article]` 함수를 구현한 뒤
`src/collect.py`의 `SOURCES` 딕셔너리와 `config.yaml`의 `sources`에 등록하면 됩니다.
RSS가 있는 매체는 `cargonews.py`를, 없는 매체는 `ksg.py`를 복사해서 시작하세요.

## 6. 알아둘 것
- 사이트 구조가 바뀌면 파서가 깨질 수 있습니다. Actions 로그에 `본문 없음` / `목록 실패`가 반복되면 `src/sources/*.py`의 CSS 셀렉터를 확인하세요. `tests/test_parsers.py`의 HTML 조각이 2026-11-16 기준 실제 구조입니다.
- 개인 열람용 요약 + 원문 링크 구조입니다. 기사 본문은 요약에만 쓰고 저장하지 않습니다(`keep_body: false`). 사이트에도 요약과 원문 링크만 노출됩니다.
- 크롤러는 요청 간 0.7초 대기하고 소스당 25건으로 제한해 사이트에 부담을 주지 않습니다.

---
지도: Natural Earth (public domain), world-atlas (ISC). 재생성: `scripts/build_world_path.py`
