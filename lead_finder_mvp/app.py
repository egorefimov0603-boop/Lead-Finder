import io, re, sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

DB_PATH = Path("leads.db")
NICHES = ["Детейлинг", "Автомойки", "Аренда спецтехники", "Мотопрокаты"]
STATUSES = ["Новый", "Проверен", "Готов к отправке", "Написал", "Ответил", "Переговоры", "Клиент", "Отказ"]

st.set_page_config(page_title="Lead Finder", page_icon="🎯", layout="wide")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL, niche TEXT DEFAULT '', categories TEXT DEFAULT '',
          city TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '',
          website TEXT DEFAULT '', whatsapp TEXT DEFAULT '', telegram TEXT DEFAULT '',
          address TEXT DEFAULT '', rating TEXT DEFAULT '', reviews TEXT DEFAULT '',
          source TEXT DEFAULT '2ГИС', source_url TEXT DEFAULT '', notes TEXT DEFAULT '',
          score INTEGER DEFAULT 0, status TEXT DEFAULT 'Новый',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, dedupe_key TEXT UNIQUE
        )""")
        # Миграция старой базы MVP 0.1
        existing = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
        for name, typ in [("categories","TEXT DEFAULT ''"),("email","TEXT DEFAULT ''"),
                          ("whatsapp","TEXT DEFAULT ''"),("telegram","TEXT DEFAULT ''"),
                          ("rating","TEXT DEFAULT ''"),("reviews","TEXT DEFAULT ''")]:
            if name not in existing:
                c.execute(f"ALTER TABLE leads ADD COLUMN {name} {typ}")
init_db()

def s(v):
    return "" if pd.isna(v) else str(v).strip()

def phone_digits(v):
    return re.sub(r"\D", "", s(v))

def key_for(name, city, phone):
    p = phone_digits(phone)
    if p:
        if len(p) == 11 and p.startswith("8"): p = "7" + p[1:]
        return "p:" + p
    return "n:" + re.sub(r"[^a-zа-я0-9]", "", (name + city).lower())

def detect_niche(categories):
    x = (categories or "").lower()
    if "аренда спецтехники" in x or "спецтехник" in x or "самосвал" in x or "экскаватор" in x:
        return "Аренда спецтехники"
    if "мотопрокат" in x or "аренда мото" in x:
        return "Мотопрокаты"
    if "детейлинг" in x:
        return "Детейлинг"
    if "автомойк" in x or "мойка автомобилей" in x:
        return "Автомойки"
    return ""

def score_row(r):
    score = 0
    if not r.get("website"): score += 25
    if r.get("phone"): score += 15
    if r.get("name"): score += 10
    if r.get("city"): score += 5
    try:
        rating = float(r.get("rating") or 0)
        reviews = int(float(r.get("reviews") or 0))
        if rating >= 4.7: score += 10
        if reviews >= 50: score += 10
        if reviews >= 150: score += 5
    except Exception: pass
    if r.get("whatsapp") or r.get("telegram"): score += 5
    return min(score, 100)

def message_for(r):
    name, city, niche = r.get("name") or "вашей компании", r.get("city") or "", r.get("niche") or ""
    intros = {
      "Детейлинг":"Можно сделать для вашей студии удобное сайт-приложение: услуги, пакеты, цены, фотографии работ и заявки на запись.",
      "Автомойки":"Можно собрать сайт-приложение автомойки с видами мойки, дополнительными услугами, ценами и заявками на удобное время.",
      "Аренда спецтехники":"Можно сделать каталог вашей техники с характеристиками, фотографиями, стоимостью аренды, доставкой и календарём доступности.",
      "Мотопрокаты":"Можно сделать каталог мотоциклов с фотографиями, ценами, свободными датами и отправкой заявки."
    }
    detail = intros.get(niche, "Можно сделать удобный сайт-приложение с каталогом, фотографиями, ценами и заявками.")
    return f"Здравствуйте! Посмотрел информацию о {name}" + (f" в {city}" if city else "") + f". {detail} Могу показать демонстрационный вариант, чтобы вы оценили, насколько это удобно."

def guess(cols, terms):
    for col in cols:
        if any(t in str(col).lower() for t in terms): return col
    return None

st.title("🎯 Lead Finder")
st.caption("Локальная система поиска и подготовки потенциальных клиентов · MVP 0.2")

with db() as c:
    total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    ready = c.execute("SELECT COUNT(*) FROM leads WHERE status='Готов к отправке'").fetchone()[0]
    replied = c.execute("SELECT COUNT(*) FROM leads WHERE status='Ответил'").fetchone()[0]
    clients = c.execute("SELECT COUNT(*) FROM leads WHERE status='Клиент'").fetchone()[0]
a,b,c1,d = st.columns(4)
a.metric("Компаний в базе", total); b.metric("Готовы к контакту", ready)
c1.metric("Ответили", replied); d.metric("Клиенты", clients)

t_import, t_base, t_export, t_help = st.tabs(["📥 Импорт CSV", "🗂 База компаний", "📤 Экспорт", "ℹ️ Инструкция"])

with t_import:
    st.subheader("Импорт CSV из 2ГИС")
    up = st.file_uploader("Выбери CSV-файл", type=["csv"])
    if up:
        raw = up.getvalue()
        # Экспорт 2ГИС может начинаться со служебной строки sep=,
        if raw.lstrip(b"\\xef\\xbb\\xbf").startswith(b"sep="):
            raw = raw.split(b"\\n", 1)[1]
        frame = None
        for enc in ["utf-8-sig", "utf-8", "cp1251"]:
            try:
                frame = pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str).fillna("")
                break
            except Exception: continue
        if frame is None:
            st.error("Не удалось прочитать CSV. Пересохрани его в UTF-8 и попробуй снова.")
        else:
            cols = list(frame.columns)
            st.success(f"Файл распознан: {len(frame)} строк, {len(cols)} столбцов.")
            st.dataframe(frame.head(8), use_container_width=True)
            st.markdown("#### Сопоставление полей")
            mappings = {
              "name":("Название компании",["наименование","название","компан","name"]),
              "categories":("Рубрики / категории",["рубрики","категор","вид деятель"]),
              "city":("Город",["город","city"]),
              "phone":("Телефон",["телефон","phone"]),
              "email":("E-mail",["e-mail","email","почта"]),
              "website":("Веб-сайт",["веб-сайт","сайт","website"]),
              "whatsapp":("WhatsApp",["whatsapp","вотсап"]),
              "telegram":("Telegram",["telegram","телеграм"]),
              "address":("Адрес",["адрес","address"]),
              "rating":("Рейтинг",["рейтинг","rating"]),
              "reviews":("Количество отзывов",["количество отзывов","отзывов","reviews"]),
              "source_url":("Ссылка на карточку",["2gis url","ссылка","карточка"])
            }
            selected = {}
            grid = st.columns(3)
            for i,(field,(label,terms)) in enumerate(mappings.items()):
                g = guess(cols,terms)
                with grid[i%3]:
                    opts = ["— пропустить —"] + cols
                    selected[field] = st.selectbox(label, opts, index=(cols.index(g)+1 if g in cols else 0), key=f"map_{field}")
            st.markdown("#### Категория компаний")
            mode = st.radio("Как определить нишу?", ["Автоматически по рубрикам", "Задать одну нишу всему файлу"], horizontal=True)
            chosen = st.selectbox("Ниша файла", NICHES) if mode.startswith("Задать") else ""
            if st.button("Импортировать в базу", type="primary"):
                added=skipped=0
                now=datetime.now().isoformat(timespec="seconds")
                with db() as con:
                    for _, rr in frame.iterrows():
                        def val(field):
                            col=selected[field]
                            return s(rr.get(col,"")) if col!="— пропустить —" else ""
                        name=val("name")
                        if not name: skipped+=1; continue
                        cats=val("categories")
                        niche=chosen if chosen else detect_niche(cats)
                        row={"name":name,"niche":niche,"city":val("city"),"phone":val("phone"),
                             "website":val("website"),"rating":val("rating"),"reviews":val("reviews"),
                             "whatsapp":val("whatsapp"),"telegram":val("telegram")}
                        score=score_row(row)
                        key=key_for(name,row["city"],row["phone"])
                        try:
                            con.execute("""INSERT INTO leads
                            (name,niche,categories,city,phone,email,website,whatsapp,telegram,address,rating,reviews,
                             source,source_url,score,status,created_at,updated_at,dedupe_key)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (name,niche,cats,row["city"],row["phone"],val("email"),row["website"],row["whatsapp"],
                             row["telegram"],val("address"),row["rating"],row["reviews"],"2ГИС",val("source_url"),
                             score,"Новый",now,now,key))
                            added+=1
                        except sqlite3.IntegrityError: skipped+=1
                st.success(f"Готово. Добавлено: {added}. Пропущено (пустое название или дубль): {skipped}.")
                st.info("Компании с неизвестной рубрикой останутся без ниши — назначь её вручную в базе.")

with t_base:
    st.subheader("База компаний")
    f1,f2,f3=st.columns(3)
    with f1: nf=st.selectbox("Ниша",["Все"]+NICHES,key="nf")
    with f2: sf=st.selectbox("Статус",["Все"]+STATUSES,key="sf")
    with f3: q=st.text_input("Поиск")
    sql="SELECT * FROM leads WHERE 1=1"; args=[]
    if nf!="Все": sql+=" AND niche=?"; args.append(nf)
    if sf!="Все": sql+=" AND status=?"; args.append(sf)
    if q: sql+=" AND (name LIKE ? OR city LIKE ? OR phone LIKE ?)"; args += [f"%{q}%"]*3
    sql+=" ORDER BY score DESC, created_at DESC"
    with db() as con: items=[dict(x) for x in con.execute(sql,args).fetchall()]
    if not items: st.info("База пока пустая. Загрузи CSV во вкладке «Импорт CSV».")
    for r in items:
        with st.expander(f"{r['name']} · {r['city']} · {r['score']}/100"):
            x,y=st.columns([2,1])
            with x:
                st.write(f"**Ниша:** {r['niche'] or 'не определена'}")
                st.write(f"**Рубрики:** {r['categories'] or '—'}")
                st.write(f"**Телефон:** {r['phone'] or '—'}")
                st.write(f"**WhatsApp:** {r['whatsapp'] or '—'}")
                st.write(f"**Telegram:** {r['telegram'] or '—'}")
                st.write(f"**Сайт:** {r['website'] or 'не указан в выгрузке'}")
                st.write(f"**Рейтинг / отзывы:** {r['rating'] or '—'} / {r['reviews'] or '—'}")
                st.write(f"**Адрес:** {r['address'] or '—'}")
                if r["source_url"]: st.markdown(f"[Открыть карточку 2ГИС]({r['source_url']})")
                st.text_area("Заготовка сообщения",message_for(r),key=f"msg_{r['id']}")
            with y:
                ni=st.selectbox("Ниша",[""]+NICHES,index=(NICHES.index(r["niche"])+1 if r["niche"] in NICHES else 0),key=f"niche_{r['id']}")
                si=st.selectbox("Статус",STATUSES,index=STATUSES.index(r["status"]),key=f"status_{r['id']}")
                if st.button("Сохранить",key=f"save_{r['id']}"):
                    with db() as con: con.execute("UPDATE leads SET niche=?,status=?,updated_at=? WHERE id=?",(ni,si,datetime.now().isoformat(timespec="seconds"),r["id"]))
                    st.rerun()
                st.metric("Предварительная оценка",f"{r['score']}/100")
                if r["phone"]: st.code(phone_digits(r["phone"]))
                if r["whatsapp"]: st.markdown(f"[Открыть WhatsApp]({r['whatsapp']})")
                elif r["phone"]:
                    st.caption("WhatsApp-ссылку нужно проверить вручную: номер может быть не личным или отличаться от телефона карточки.")

with t_export:
    with db() as con: out=pd.read_sql_query("SELECT name,niche,categories,city,phone,email,website,whatsapp,telegram,address,rating,reviews,source,source_url,score,status,created_at FROM leads ORDER BY score DESC",con)
    st.write(f"Компаний: {len(out)}")
    st.download_button("Скачать CSV",out.to_csv(index=False).encode("utf-8-sig"),"lead_finder_export.csv","text/csv")

with t_help:
    st.markdown("""
**Локальная база:** `leads.db` создаётся рядом с приложением.

**Импорт 2ГИС:** приложение распознаёт служебную строку `sep=,`, русские заголовки и поля экспорта 2ГИС. Рубрики автоматически сопоставляются с четырьмя нишами.

**Дедупликация:** по нормализованному телефону; если телефон отсутствует — по названию и городу. Разные номера одной компании пока могут попасть как отдельные записи.

**Оценка:** предварительный балл по наличию сайта, контактов, рейтингу и отзывам. Это не гарантия интереса к покупке.

**Важно:** отсутствие сайта в выгрузке не доказывает, что у компании нет сайта; сайт нужно дополнительно проверять. WhatsApp и MAX не рассылают сообщения автоматически.
""")
