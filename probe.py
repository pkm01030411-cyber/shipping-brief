import os, json, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 shipping-brief"}
os.makedirs("out3", exist_ok=True)
B="https://dream.kotra.or.kr/kotranews/cms"
U={
 "nat_ru.html": B+"/nation/actionNatIemList.do?pageNo=&pagePerCnt=10&SITE_NO=3&MENU_ID=220&CONTENTS_NO=1&pRegnCd=03&pNatCd=643",
 "list70.html": B+"/com/index.do?MENU_ID=70",
 "boardlist_ru.html": B+"/news/actionKotraBoardList.do?SITE_NO=3&MENU_ID=70&CONTENTS_NO=1&pNatCd=643&pageNo=1&pagePerCnt=20",
 "boardlist_ru2.html": B+"/news/actionKotraBoardList.do?SITE_NO=3&MENU_ID=70&CONTENTS_NO=1&pNatCd=643",
 "detail.html": B+"/news/actionKotraBoardDetail.do?SITE_NO=3&MENU_ID=180&CONTENTS_NO=1&pNttSn=244954",
 "ukr1590.html": B+"/com/index.do?MENU_ID=1590",
 "search_ru.html": "https://dream.kotra.or.kr/kotranews/search.do?query=%EB%9F%AC%EC%8B%9C%EC%95%84",
}
rep={}
for k,u in U.items():
    try:
        r=requests.get(u,headers=UA,timeout=25); open("out3/"+k,"wb").write(r.content[:900000])
        rep[k]={"status":r.status_code,"final":r.url,"bytes":len(r.content)}
    except Exception as e: rep[k]={"err":repr(e)[:200]}
json.dump(rep,open("out3/report.json","w"),indent=1); print(json.dumps(rep,indent=1))
