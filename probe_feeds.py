import json, yaml, requests, feedparser
from datetime import datetime, timezone
from src.common import Http
from src.sources import ksg, eurasia as E
cfg=yaml.safe_load(open("config.yaml")); http=Http(cfg); rep={}
feeds={"moscowtimes":"https://www.themoscowtimes.com/rss/news","meduza":"https://meduza.io/rss/en/all","eurasianet":"https://eurasianet.org/rss","timesca":"https://timesca.com/feed/","cargonews":cfg["sources"]["cargonews"]["url"] if "url" in cfg["sources"]["cargonews"] else "https://www.cargonews.co.kr/rss/allArticle.xml"}
for k,u in feeds.items():
    try:
        f=feedparser.parse(http.get(u).content)
        ds=sorted(datetime(*e.published_parsed[:6]).isoformat() for e in f.entries if e.get("published_parsed"))
        rep[k]={"n":len(f.entries),"oldest":ds[0] if ds else None,"newest":ds[-1] if ds else None, "raw_dates":[e.get("published") for e in f.entries[-3:]]}
    except Exception as e: rep[k]={"err":repr(e)[:200]}
# KSG: 카테고리별 페이지 1~3 가장 오래된 날짜
ks={}
for code in cfg["sources"]["ksg"]["categories"]:
    code=code if isinstance(code,str) else list(code)[0]
    row=[]
    for page in (1,2,3):
        try:
            items=ksg.parse_list(http.get(ksg.LIST_URL.format(page=page,code=code)).text, code, cfg)
            row.append([len(items), min(i["published"] for i in items).isoformat() if items else None])
        except Exception as e: row.append(repr(e)[:80])
    ks[code]=row
rep["ksg"]=ks
# PortNews 하루치 페이지
for d in ("2026-11-17","2026-11-18"):
    items=E.parse_portnews_list(http.get(f"https://portnews.ru/news/{d}/").text)
    rep["portnews_"+d]={"n":len(items),"first":str(items[0]["published"]) if items else None,"last":str(items[-1]["published"]) if items else None}
html=http.get("https://portnews.ru/news/2026-11-17/").text
import re; rep["portnews_pages"]=re.findall(r'href="(/news/2026-11-17/[^"]*page[^"]*)"',html)[:5]+re.findall(r'href="([^"]*PAGEN[^"]*)"',html)[:5]
# Barents 홈 링크 수/번호 범위
b=E.parse_barents_home(http.get("https://www.thebarentsobserver.com/").text); rep["barents"]={"n":len(b)}
# Meduza 기사 페이지 본문 추출
f=feedparser.parse(http.get(feeds["meduza"]).content)
link=f.entries[0].link; h=http.get(link).text
rep["meduza_page"]={"url":link,"len":len(E.extract_body(h)),"head":E.extract_body(h)[:200]}
f=feedparser.parse(http.get(feeds["timesca"]).content)
h=http.get(f.entries[0].link).text
rep["tca_page"]={"len":len(E.extract_body(h,[".entry-content"])),"head":E.extract_body(h,[".entry-content"])[:150]}
json.dump(rep,open("feeds-report.json","w"),ensure_ascii=False,indent=1); print(json.dumps(rep,ensure_ascii=False,indent=1))
