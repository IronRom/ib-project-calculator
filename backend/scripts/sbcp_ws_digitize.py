import pdfplumber, re, json
NUM=r'[\d]+(?:[.,][\d]+)?'
RE4=re.compile(rf'^\s*(\d{{1,2}})\s+(.*?)\s+({NUM}|[-—])\s+({NUM}|[-—])\s+(\d{{2}})\s+(\d{{2}})\s*$')  # a b %ПД %РД
RE2=re.compile(rf'^\s*(\d{{1,2}}(?:\.\d{{1,2}})?)\s+(.*?)\s+({NUM}|[-—])\s+({NUM}|[-—])\s*$')            # a b (без стадий)
RE_TBL=re.compile(r'^\s*Таблица\s*№?\s*([\w\d.-]+)')
RE_RANGE=re.compile(r'(?:свыше|до|от|св\.)\s*'+NUM, re.I)
def f2(s):
    s=(s or '').replace(' ','').replace('—','-')
    return None if s in('-','.','') else float(s.replace(',','.'))
def rng(t):
    t=t.lower()
    m=re.search(r'(?:свыше|св\.)\s*('+NUM+r')\s*до\s*('+NUM+r')',t) or re.search(r'от\s*('+NUM+r')\s*до\s*('+NUM+r')',t)
    if m: return f2(m.group(1)),f2(m.group(2))
    m=re.search(r'до\s*('+NUM+r')',t)
    if m: return None,f2(m.group(1))
    m=re.search(r'(?:свыше|св\.)\s*('+NUM+r')',t)
    return (f2(m.group(1)),None) if m else (None,None)
def parse(pdf, mode):
    tables={}; cur=None; hdr=""
    with pdfplumber.open(pdf) as p:
        for pg in p.pages:
            for ln in (pg.extract_text() or "").split("\n"):
                mt=RE_TBL.match(ln)
                if mt: cur=mt.group(1); tables.setdefault(cur,{"table":cur,"rows":[]}); hdr=""; continue
                if cur is None: continue
                m=RE4.match(ln)
                if m and mode==4:
                    n,mid,a,b,pd,rd=m.groups()
                    if not(98<=int(pd)+int(rd)<=102): continue
                    av=f2(a)
                    if not av or av<=0: continue
                    xmin,xmax=rng(mid); tables[cur]["rows"].append({"name":hdr[:110],"mid":mid.strip()[:40],"x_min":xmin,"x_max":xmax,"a":av,"b":f2(b),"pd":int(pd),"rd":int(rd)}); continue
                m=RE2.match(ln)
                if m and mode==2 and RE_RANGE.search(m.group(2)):
                    n,mid,a,b=m.groups(); av=f2(a)
                    if not av or av<=0 or av>100000: continue
                    xmin,xmax=rng(mid); tables[cur]["rows"].append({"name":hdr[:110],"mid":mid.strip()[:40],"x_min":xmin,"x_max":xmax,"a":av,"b":f2(b),"pd":None,"rd":None}); continue
                if ln.strip().endswith(':') or (len(ln.strip())>15 and not re.match(r'^\s*\d',ln) and 'роцент' not in ln and 'тыс. руб' not in ln and 'показа' not in ln):
                    hdr=ln.strip()
    return tables
BASE="/Users/nemo/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/documents/minstroy/publish/sbc/"
for code,fn,mode,spots in [
 ("СБЦП-02",BASE+"СБЦП 81-2001-02 - Объекты связи.pdf",4,[(1.02,0.015),(1.39,0.102)]),
 ("СБЦП-05",BASE+"СБЦП 81-2001-05 - Нормативы подготовки техдокументации для капремонта зданий ЖГ назначения (изд. 2012).pdf",2,[(23.1,0.09)]),
]:
    t=parse(fn,mode); nr=sum(len(v["rows"]) for v in t.values())
    json.dump({"code":code,"tables":[v for v in t.values() if v["rows"]]},open(f"/tmp/{code}.json","w"),ensure_ascii=False)
    print(f"### {code}: таблиц-с-данными {len([v for v in t.values() if v['rows']])}, строк {nr}")
    for ea,eb in spots:
        h=[r for v in t.values() for r in v["rows"] if abs(r["a"]-ea)<0.001]
        print(f"   спот a={ea}: {'OK '+str([(x['name'][:34],x['mid']) for x in h[:1]]) if h else 'НЕ НАЙДЕНО ✗'}")
    # выборка 4 строк для глаз
    sample=[r for v in t.values() for r in v["rows"]][:4]
    for s in sample: print(f"     обр: a={s['a']} b={s['b']} X=[{s['x_min']}..{s['x_max']}] pd={s['pd']} «{s['mid']}»")
