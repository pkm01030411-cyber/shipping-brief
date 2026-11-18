import os, re, json, time, requests, feedparser
from urllib.parse import urljoin
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 shipping-brief"}
os.makedirs("out2", exist_ok=True)
rep={}
def save(k,u):
    try:
        r=requests.get(u,headers=UA,timeout=25)
        open(f"out2/{k}","wb").write(r.content[:800000])
        rep[k]={"url":u,"status":r.status_code,"final":r.url,"bytes":len(r.content),"ctype":r.headers.get("content-type")}
        return r
    except Exception as e:
        rep[k]={"url":u,"err":repr(e)[:200]}; return None
r=save("kotra_rsspage.html","https://dream.kotra.or.kr/kotranews/cms/com/index.do?MENU_ID=720")
if r is not None:
    urls=sorted(set(re.findall(r'(?:https?://dream\.kotra\.or\.kr)?/kotranews/[^"\'\s<>]*rss[^"\'\s<>]*',r.text,re.I)))
    rep["kotra_rss_urls"]=urls[:60]
    for i,u in enumerate(urls[:6]):
        rr=save(f"kotra_rss_{i}.xml",urljoin("https://dream.kotra.or.kr",u.replace('&amp;','&')))
save("pn_home.html","https://en.portnews.ru/")
save("pn_day.html","https://en.portnews.ru/news/2026-11-17/")
save("pn_art.html","https://en.portnews.ru/news/399780/")
save("pn_ru_news.html","https://portnews.ru/news/")
save("bo_art.html","https://www.thebarentsobserver.com/news/pressure-builds-on-wellconnected-russian-businessman-who-wants-to-buy-norwegian-arctic-copper-mine/462079")
for k,u in [("bo_sitemap.xml","https://www.thebarentsobserver.com/sitemap.xml"),("bo_newssitemap.xml","https://www.thebarentsobserver.com/news-sitemap.xml"),("bo_robots.txt","https://www.thebarentsobserver.com/robots.txt"),("bo_news.html","https://www.thebarentsobserver.com/news"),("bo_rss_xml","https://www.thebarentsobserver.com/rss.xml"),("bo_feed_xml","https://www.thebarentsobserver.com/feed.xml")]:
    save(k,u)
json.dump(rep,open("out2/report.json","w"),ensure_ascii=False,indent=1)
print(json.dumps(rep,ensure_ascii=False,indent=1))
