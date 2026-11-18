import os, json, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 shipping-brief",
      "X-Requested-With":"XMLHttpRequest","Referer":"https://dream.kotra.or.kr/kotranews/cms/com/index.do?MENU_ID=70"}
os.makedirs("out4", exist_ok=True)
s=requests.Session(); s.headers.update(UA)
s.get("https://dream.kotra.or.kr/kotranews/cms/com/index.do?MENU_ID=70",timeout=25)
rep={}
for cd in ["03","01"]:
    r=s.post("https://dream.kotra.or.kr/ajaxf/frNews/getInNewsNationList.do",data={"cd":cd,"bbsSn":"242,244,322,245,246,444,464,518,505,484,519"},timeout=25)
    open(f"out4/nat_{cd}.json","wb").write(r.content); rep[f"nat_{cd}"]=[r.status_code,len(r.content)]
base={"pageNo":"1","pagePerCnt":"20","SITE_NO":"3","MENU_ID":"70","CONTENTS_NO":"1","bbsGbn":"00","bbsSn":"242,244,322,245,246,444,464,518,505,484,519","pNttSn":"","recordCountPerPage":"20","viewType":"","pNewsGbn":"","pStartDt":"","pEndDt":"","sSearchVal":""}
for name,extra in {"ru":[("pRegnCd","03"),("pNatCd","643")],"cis":[("pNatCd","643"),("pNatCd","398"),("pNatCd","860"),("pNatCd","031"),("pNatCd","112"),("pNatCd","417")],"all":[]}.items():
    data=list(base.items())+extra
    r=s.post("https://dream.kotra.or.kr/ajaxf/frNews/getKotraBoardList.do",data=data,timeout=25)
    open(f"out4/list_{name}.json","wb").write(r.content); rep["list_"+name]=[r.status_code,len(r.content),r.headers.get("content-type")]
json.dump(rep,open("out4/report.json","w"),indent=1); print(rep)
