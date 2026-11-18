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
