import sys,json,re; sys.path.insert(0,"/app")
from datetime import datetime,timezone
from app.database import SessionLocal
from app.models import ReferenceBook,BookObjectType,ReferenceRow,BookCondition
from app.services.calculator import calculate
db=SessionLocal()
def unit_of(mid):
    for u in ["абонент","номер","пара","м²","м2","га","тыс.мест","мест","этаж","п.м","м"]:
        if u in mid: return u
    return ""
def imp(jf,code,name,pd,rd):
    data=json.load(open(jf))
    old=db.query(ReferenceBook).filter(ReferenceBook.code==code).first()
    if old:
        if not (old.notes or "").startswith("Оцифровано"): 
            print(f"{code}: кураторская — пропуск"); return old
        for M in (ReferenceRow,BookObjectType,BookCondition): db.query(M).filter(M.book_version_id==old.id).delete()
        db.delete(old); db.flush()
    b=ReferenceBook(code=code,official_name=name,version=1,status="consistent",is_active=True,
        price_base_year=2001,calc_method="standard",pricing_method="mu620",pd_pct=pd,rd_pct=rd,
        uploaded_at=datetime.now(timezone.utc),notes="Оцифровано ws-парсером из текст-слоя PDF. База 2001. Спот-чек по эталону Рейсовой; прочие таблицы — автопарс, требуют выверки.")
    db.add(b); db.flush()
    nr=nt=0
    for t in data["tables"]:
        tnum=int(re.sub(r"\D","",t["table"]) or 0)
        grp={}
        for r in t["rows"]: grp.setdefault(r["name"] or f"т{tnum}",[]).append(r)
        for nm,rows in grp.items():
            ot=BookObjectType(book_version_id=b.id,name=nm,table_num=tnum); db.add(ot); db.flush(); nt+=1
            for r in rows:
                db.add(ReferenceRow(book_version_id=b.id,object_type_id=ot.id,table_num=tnum,
                    a=r["a"],b=r["b"],x_min=r["x_min"],x_max=r["x_max"],x_unit=unit_of(r["mid"]),description=r["mid"])); nr+=1
    db.commit(); print(f"{code}: таблиц {len(data['tables'])}, типов {nt}, строк {nr}, pd/rd={pd}/{rd}, id={b.id}")
    return b

b02=imp("/tmp/sbcp02.json","СБЦП 81-2001-02","СБЦП 81-2001-02 Объекты связи",0.48,0.52)
b05=imp("/tmp/sbcp05.json","СБЦП 81-2001-05","СБЦП 81-2001-05 Нормативы подготовки техдокументации для капремонта зданий ЖГ",None,None)

def tid_by_a(book,tnum,a):
    r=db.query(ReferenceRow).filter(ReferenceRow.book_version_id==book.id,ReferenceRow.table_num==tnum,ReferenceRow.a==a).first()
    return r.object_type_id if r else None
print("\n=== СПОТ-ЧЕК: 3 новые позиции Рейсовой vs эталон ===")
tests=[("Громкоговорящая связь",b02,9,1.39,7,"абонент",7.5876,"ПД48%"),
       ("Оперативно-диспетч. связь",b02,9,1.02,50,"номер",None,"ПД48% (эталон непослед. 40%)"),
       ("Канализация зданий",b05,8,23.1,30,"м",50.0976,"ПД40%×Кэ0.6")]
for nm,bk,tn,a,x,unit,exp_pd,note in tests:
    oid=tid_by_a(bk,tn,a)
    if not oid: print(f"  {nm}: object_type НЕ найден ✗"); continue
    r=calculate({"stage":"П+Р","region":"Москва","financing":"federal","entities":[
        {"object_name":nm,"object_type":"объект","category":"reconstruction","sbts_code":bk.code,
         "sbts_table":tn,"sbts_object_type_id":oid,"x_value":x,"x_unit":unit,"coefficients":[],
         "sections":[],"section_num":0,"section_name":""}]},db)
    pd=next((p["cost"]/1000 for p in r["positions"] if p.get("stage_label")=="ПД"),None)
    tag="✓" if (exp_pd and abs(pd-exp_pd)<0.05) else ("~" if exp_pd else "info")
    print(f"  {nm}: ПД={pd:.4f} тыс | эталон={exp_pd} [{tag}] ({note})")
db.close()
