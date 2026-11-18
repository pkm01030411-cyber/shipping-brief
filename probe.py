import os, re, json, sys, time
import requests, feedparser
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 shipping-brief"}
os.makedirs("out", exist_ok=True)
FEEDS = {
 "mt_news": "https://www.themoscowtimes.com/rss/news",
 "mt_feeds": "https://www.themoscowtimes.com/feeds/news.xml",
 "meduza_en": "https://meduza.io/rss/en/all",
 "meduza_ru": "https://meduza.io/rss/all",
 "eurasianet_rss": "https://eurasianet.org/rss.xml",
 "eurasianet_feed": "https://eurasianet.org/feed",
 "eurasianet_rss2": "https://eurasianet.org/rss",
 "tca": "https://timesca.com/feed/",
 "barents_rss": "https://www.thebarentsobserver.com/rss",
 "barents_feed": "https://www.thebarentsobserver.com/feed",
 "barents_en": "https://thebarentsobserver.com/en/rss.xml",
 "portnews_en_rss": "https://en.portnews.ru/rss/",
 "portnews_en_rss2": "https://en.portnews.ru/rss.xml",
 "portnews_ru_rss": "https://portnews.ru/rss/",
 "hnn": "https://www.highnorthnews.com/en/rss.xml",
}
PAGES = {
 "portnews_en_news": "https://en.portnews.ru/news/",
 "barents_home": "https://www.thebarentsobserver.com/",
 "eurasianet_home": "https://eurasianet.org/",
 "kotra_dream": "https://dream.kotra.or.kr/kotranews/index.do",
 "kotra_news_list": "https://dream.kotra.or.kr/kotranews/cms/com/index.do?MENU_ID=410",
 "kotra_rss": "https://dream.kotra.or.kr/kotranews/rss.do",
}
rep = {}
def get(u):
    t=time.time()
    try:
        r = requests.get(u, headers=UA, timeout=25)
        return r, round(time.time()-t,1), None
    except Exception as e:
        return None, round(time.time()-t,1), repr(e)[:200]
for k,u in FEEDS.items():
    r,dt,err = get(u)
    d = {"url":u,"sec":dt,"err":err}
    if r is not None:
        d.update(status=r.status_code, ctype=r.headers.get("content-type"), final=r.url, bytes=len(r.content))
        open(f"out/{k}.txt","wb").write(r.content[:400000])
        f = feedparser.parse(r.content)
        d["entries"] = len(f.entries)
        d["sample"] = [{"title":e.get("title"),"link":e.get("link"),"pub":e.get("published"),"summ_len":len(e.get("summary","") or ""),"content_len":sum(len(c.get("value","")) for c in e.get("content",[]) or [])} for e in f.entries[:4]]
        if f.entries:
            link = f.entries[0].get("link")
            ar,adt,aerr = get(link)
            d["article"] = {"url":link,"status":getattr(ar,"status_code",None),"sec":adt,"err":aerr}
            if ar is not None: open(f"out/{k}__article.html","wb").write(ar.content[:600000])
    rep[k]=d; print(k, json.dumps({x:d.get(x) for x in ("status","entries","sec","err")}), flush=True)
for k,u in PAGES.items():
    r,dt,err = get(u)
    d={"url":u,"sec":dt,"err":err}
    if r is not None:
        d.update(status=r.status_code, final=r.url, bytes=len(r.content))
        open(f"out/{k}.html","wb").write(r.content[:600000])
        d["rss_links"] = re.findall(r'<link[^>]+(?:rss|atom)[^>]*>', r.text)[:5]
    rep[k]=d; print(k, d.get("status"), d.get("err"), flush=True)
json.dump(rep, open("out/report.json","w"), ensure_ascii=False, indent=1)
