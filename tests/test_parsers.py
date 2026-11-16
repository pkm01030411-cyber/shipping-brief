"""파서 단위 테스트 — 2026-11-16 실제 사이트 구조를 본뜬 HTML 조각 사용."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.common import load_config  # noqa: E402
from src.sources import cargonews, ksg  # noqa: E402

CFG = load_config()

KSG_LIST = """
<div class="sub_cont"><div class="news_wrap"><ul class="new_list">
<li><p><a href="/news/main_newsView.jsp?pNum=148506"><img src="/x.jpg"></a></p>
<dl class="textarea"><dt><a href="/news/main_newsView.jsp?pNum=148506">[표] 주간 중고선 가격동향</a>
<div class="date">2026-11-16 14:25</div></dt><dd><a href="/news/main_newsView.jsp?pNum=148506">&lt; 코리아쉬핑가제트 &gt;</a></dd></dl></li>
<li><p><a href="/news/main_newsView.jsp?pNum=148502"><img src="/y.jpg"></a></p>
<dl class="textarea"><dt><a href="/news/main_newsView.jsp?pNum=148502">유럽·북미 항만 노사 갈등 표면화…물류 차질 우려</a>
<div class="date">2026-11-16 09:07</div></dt><dd><a href="#"> </a></dd></dl></li>
</ul></div></div>
"""

KSG_ARTICLE = """
<html><body><div class="view_wrap">
<div id="categorySpace" class="categorySpace">해운항만</div>
<div id="newsRegDate" class="subtit">2026-11-16 09:07</div>
<div class="newtopbox"><h1 id="newsTitle" class="maintit">유럽·북미 항만 노사 갈등 표면화…물류 차질 우려</h1>
<div id="newsSubTitle1">LA·롱비치항 협상 장기화…20일까지 연장</div></div>
<div id="newsContent" class="editor_txt">
<div style="text-align:center"><img src="/img.jpg"></div><br><br>
최근 유럽 항만의 파업과 미국 서안의 노사협상 장기화가 국제 공급망의 불확실성을 키우고 있다.<br><br>
▲10월30일 이탈리아 제노바에서 항만 노동자들이 파업을 벌이고 있다.<br><br>
항만 작업엔 하역과 컨테이너 고박 작업이 포함된다.<br><br>
&lt; 박한솔 기자 hsolpark@ksg.co.kr &gt;
</div></div></body></html>
"""

CN_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>카고뉴스(CargoNews) - 전체기사</title>
<item><title>페덱스, 광저우 터미널 본격 운영</title>
<link>http://www.cargonews.co.kr/news/articleView.html?idxno=61245</link>
<description><![CDATA[ 페덱스가 16일부터 중국 광저우공항(CAN)에 ‘제4국제화물터미널’을 본격 운영에 들어갔다. ]]></description>
<author>김시오 편집장</author><pubDate>2026-11-16 17:42:06</pubDate></item>
<item><title>韓→美 ‘컨’ 204만TEU로 3.8% 증가</title>
<link>http://www.cargonews.co.kr/news/articleView.html?idxno=61242</link>
<description><![CDATA[ 지난 1~10월 미국의 전체 수입 컨테이너 물동량은 ]]></description>
<author>김종휘 기자</author><pubDate>2026-11-16 08:34:04</pubDate></item>
</channel></rss>"""

CN_ARTICLE = """
<html><head><title>韓→美 ‘컨’ 204만TEU로 3.8% 증가 &lt; Graphic Market &lt; 해운 &lt; 기사본문 - 카고뉴스(CargoNews)</title>
<meta property="og:title" content="韓→美 ‘컨’ 204만TEU로 3.8% 증가">
<meta property="article:published_time" content="2026-11-16T08:34:04+09:00"></head>
<body><a href="/news/articleList.html?sc_section_code=S1N2">해운</a>
<div class="article-body"><article id="article-view-content-div" class="article-veiw-body">
<p>지난 1~10월 미국의 전체 수입 컨테이너 물동량은 전년동기 대비 2.3% 증가한 2,419만 3,974TEU로 집계됐다.</p>
<p>‘데카르트 데이터마인(Descartes Datamyne)’이 집계한 바에 따르면 204만 2,980TEU로 3.8% 증가했다.</p>
<p>저작권자 © 카고뉴스 무단전재 및 재배포 금지</p>
</article></div></body></html>
"""


def test_ksg_list():
    items = ksg.parse_list(KSG_LIST, "해운", CFG)
    assert len(items) == 2
    assert items[0]["title"] == "[표] 주간 중고선 가격동향"
    assert items[0]["url"] == "https://www.ksg.co.kr/news/main_newsView.jsp?pNum=148506"
    assert items[1]["published"].strftime("%Y-%m-%d %H:%M") == "2026-11-16 09:07"
    assert items[1]["published"].tzinfo is not None


def test_ksg_article():
    d = ksg.parse_article(KSG_ARTICLE, CFG)
    assert d["title"].startswith("유럽·북미 항만")
    assert d["subtitle"] == "LA·롱비치항 협상 장기화…20일까지 연장"
    assert d["category"] == "해운항만"
    assert d["author"] == "박한솔 기자 hsolpark@ksg.co.kr"
    assert "▲" not in d["body"]
    assert "박한솔" not in d["body"]
    assert d["body"].startswith("최근 유럽 항만의")
    assert "고박 작업" in d["body"]


def test_cargonews_feed():
    items = cargonews.parse_feed(CN_RSS, CFG)
    assert len(items) == 2
    assert items[0]["url"].startswith("https://")
    assert items[0]["author"] == "김시오 편집장"
    assert items[1]["published"].hour == 8
    assert "광저우" in items[0]["description"]


def test_cargonews_article():
    d = cargonews.parse_article(CN_ARTICLE, CFG)
    assert d["title"] == "韓→美 ‘컨’ 204만TEU로 3.8% 증가"
    assert d["published"].isoformat() == "2026-11-16T08:34:04+09:00"
    assert "저작권자" not in d["body"]
    assert "204만 2,980TEU" in d["body"]
    assert d["category"] == "해운"
