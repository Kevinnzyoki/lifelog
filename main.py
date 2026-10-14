import csv, io, os, datetime as dt, sqlite3
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.progressbar import ProgressBar
import sensors
from devotion import VERSES

CITY, LAT, LON = "Machakos", -1.52, 37.26   # change to your town
GOAL = 8000
BLUE = (0.15, 0.45, 0.9, 1)


def wmo(c):
    return ("Clear" if c == 0 else "Partly cloudy" if c < 4 else "Fog" if c < 50 else "Drizzle" if c < 60
            else "Rain" if c < 70 else "Snow" if c < 80 else "Showers" if c < 90 else "Thunderstorm")


class Card(BoxLayout):
    def __init__(self, **kw):
        kw.update(orientation="vertical", padding=dp(12), spacing=dp(6), size_hint_y=None)
        super().__init__(**kw)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(0.1, 0.3, 0.62, 1)
            self.rr = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=lambda *_: setattr(self.rr, "pos", self.pos),
                  size=lambda *_: setattr(self.rr, "size", self.size))


class WLabel(Label):
    def __init__(self, text="", **kw):
        kw.setdefault("halign", "left")
        super().__init__(text=text, size_hint_y=None, **kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)),
                  texture_size=lambda *_: setattr(self, "height", self.texture_size[1] + dp(4)))

CATS = ["Food", "Transport", "Rent", "Airtime/Data", "Bills", "Health",
        "Shopping", "Salary", "Business", "Other"]


def today():
    return dt.date.today().isoformat()


class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path)
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS diary(id INTEGER PRIMARY KEY, day TEXT, title TEXT, note TEXT, minutes INT);
        CREATE TABLE IF NOT EXISTS money(id INTEGER PRIMARY KEY, day TEXT, kind TEXT, category TEXT, amount REAL, note TEXT);
        CREATE TABLE IF NOT EXISTS daily(day TEXT PRIMARY KEY, steps INT, screen_min INT);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS phone_temp(day TEXT PRIMARY KEY, tmin REAL, tmax REAL);""")

    def q(self, sql, a=()):
        r = self.c.execute(sql, a).fetchall()
        self.c.commit()
        return r

    def table(self, sql):
        cur = self.c.execute(sql)
        return [d[0] for d in cur.description], cur.fetchall()

    def get(self, k):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return r[0][0] if r else None

    def set(self, k, v):
        self.q("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))


class Rows(ScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.box.bind(minimum_height=self.box.setter("height"))
        self.add_widget(self.box)

    def fill(self, items):
        self.box.clear_widgets()
        for text, rm in items:
            r = BoxLayout(size_hint_y=None, height=dp(56))
            lb = Label(text=text, halign="left", valign="middle", max_lines=2)
            lb.bind(size=lambda w, _: setattr(w, "text_size", w.size))
            r.add_widget(lb)
            r.add_widget(Button(text="X", size_hint_x=None, width=dp(44),
                                on_release=lambda *_, f=rm: f()))
            self.box.add_widget(r)


def field(hint, **kw):
    return TextInput(hint_text=hint, multiline=False, size_hint_y=None, height=dp(44), **kw)


def btn(text, cb):
    return Button(text=text, size_hint_y=None, height=dp(48), background_normal="", background_color=BLUE,
                  on_release=lambda *_: cb())


def info(text=""):
    return Label(text=text, size_hint_y=None, height=dp(34))


def tab(title, content):
    t = TabbedPanelItem(text=title, background_color=BLUE)
    t.add_widget(content)
    return t


class LifeLog(App):
    def build(self):
        self.title = "LifeLog"
        Window.clearcolor = (0.04, 0.13, 0.3, 1)
        self.vo = 0
        self.db = DB(os.path.join(self.user_data_dir, "lifelog.db"))
        tp = TabbedPanel(do_default_tab=False, tab_width=dp(80))
        for t in (self.today_tab(), self.diary_tab(), self.money_tab(), self.export_tab()):
            tp.add_widget(t)
        tp.switch_to(tp.tab_list[-1])  # first added = last in list
        sensors.ask_permissions()
        self.steps = sensors.Steps(self.on_steps)
        Clock.schedule_interval(self.tick, 20)
        Clock.schedule_once(self.tick, 2)
        Clock.schedule_once(self.get_weather, 3)
        Clock.schedule_interval(self.get_weather, 1800)
        self.refresh_all()
        return tp

    # ---------- Today ----------
    def today_tab(self):
        sv = ScrollView()
        b = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10), size_hint_y=None)
        b.bind(minimum_height=b.setter("height"))
        sv.add_widget(b)
        self.l_hello = WLabel(font_size="22sp", bold=True)
        b.add_widget(self.l_hello)

        c = Card()
        self.l_steps, self.bar = WLabel(), ProgressBar(max=GOAL, size_hint_y=None, height=dp(14))
        c.add_widget(self.l_steps); c.add_widget(self.bar); b.add_widget(c)

        c = Card(); self.l_screen, self.l_ptemp = WLabel(), WLabel()
        c.add_widget(self.l_screen); c.add_widget(self.l_ptemp); b.add_widget(c)

        c = Card(); self.l_weather = WLabel("Weather: loading...")
        c.add_widget(self.l_weather); b.add_widget(c)

        c = Card(); self.l_water = WLabel()
        c.add_widget(self.l_water); c.add_widget(btn("+ Glass of water", self.add_water)); b.add_widget(c)

        c = Card(); c.add_widget(WLabel("How are you feeling?"))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for m in ("Great", "Good", "Okay", "Low"):
            row.add_widget(Button(text=m, background_normal="", background_color=BLUE,
                                  on_release=lambda w: self.set_mood(w.text)))
        self.l_mood = WLabel()
        c.add_widget(row); c.add_widget(self.l_mood); b.add_widget(c)

        c = Card()
        self.l_ref, self.l_verse, self.l_refl = WLabel(bold=True), WLabel(), WLabel()
        c.add_widget(WLabel("Daily devotion"))
        for w in (self.l_ref, self.l_verse, self.l_refl):
            c.add_widget(w)
        c.add_widget(btn("Next verse", self.next_verse)); b.add_widget(c)

        self.l_sum = WLabel()
        b.add_widget(self.l_sum)
        b.add_widget(btn("Enable screen-time access", sensors.open_usage_settings))
        return tab("Today", sv)

    def on_steps(self, total):
        total, d, db = int(total), today(), self.db
        last = int(db.get("last_total") or total)
        if db.get("last_day") != d:
            db.set("base", str(last if total >= last else 0))
        elif total < int(db.get("base") or 0):
            db.set("base", "0")  # phone rebooted
        db.set("last_day", d)
        db.set("last_total", str(total))
        steps = total - int(db.get("base") or total)
        db.q("INSERT INTO daily(day,steps) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET steps=?",
             (d, steps, steps))
        self.refresh_today()

    def tick(self, *_):
        self.steps.start()
        m = sensors.screen_minutes()
        if m is not None:
            self.db.q("INSERT INTO daily(day,screen_min) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET screen_min=?",
                      (today(), m, m))
        t = sensors.battery_temp()
        if t is not None:
            self.db.q("INSERT INTO phone_temp VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET "
                      "tmin=MIN(tmin,?), tmax=MAX(tmax,?)", (today(), t, t, t, t))
        self.refresh_today()

    def add_water(self):
        self.db.set("water_" + today(), str(int(self.db.get("water_" + today()) or 0) + 1))
        self.refresh_today()

    def set_mood(self, m):
        self.db.set("mood_" + today(), m)
        self.refresh_today()

    def next_verse(self):
        self.vo += 1
        self.refresh_today()

    def get_weather(self, *_):
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,"
               "relative_humidity_2m,wind_speed_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,"
               "precipitation_probability_max&timezone=auto" % (LAT, LON))
        sensors.http_get_json(url, lambda r: self.on_weather(None, r),
                              lambda: setattr(self.l_weather, "text", "Weather: offline (will retry)"))

    def on_weather(self, req, r):
        c, d = r["current"], r["daily"]
        self.l_weather.text = (
            f"{CITY}: {c['temperature_2m']}\u00b0C, {wmo(c['weather_code'])}\n"
            f"Today low {d['temperature_2m_min'][0]}\u00b0C / high {d['temperature_2m_max'][0]}\u00b0C\n"
            f"Humidity {c['relative_humidity_2m']}%   Wind {c['wind_speed_10m']} km/h   "
            f"Rain chance {d['precipitation_probability_max'][0]}%")

    def refresh_today(self):
        h = dt.datetime.now().hour
        self.l_hello.text = ("Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening") \
            + "\n" + dt.date.today().strftime("%A, %d %B")
        r = self.db.q("SELECT steps, screen_min FROM daily WHERE day=?", (today(),))
        steps, mins = r[0] if r else (None, None)
        self.l_steps.text = f"Steps: {steps if steps is not None else 'waiting for sensor...'}  (goal {GOAL})"
        self.bar.value = steps or 0
        self.l_screen.text = ("Screen time: %dh %02dm" % divmod(mins, 60)) if mins is not None \
            else "Screen time: tap the button below to enable"
        t = self.db.q("SELECT tmin, tmax FROM phone_temp WHERE day=?", (today(),))
        self.l_ptemp.text = f"Phone temp today: low {t[0][0]}\u00b0C / high {t[0][1]}\u00b0C" if t \
            else "Phone temp: no reading yet"
        w = int(self.db.get("water_" + today()) or 0)
        self.l_water.text = f"Water: {w} / 8 glasses" + ("  - goal reached!" if w >= 8 else "")
        self.l_mood.text = "Today: " + (self.db.get("mood_" + today()) or "tap how you feel")
        ref, text, refl = VERSES[(dt.date.today().toordinal() + self.vo) % len(VERSES)]
        self.l_ref.text, self.l_verse.text, self.l_refl.text = ref, text, "Reflect: " + refl
        n = self.db.q("SELECT COUNT(*) FROM diary WHERE day=?", (today(),))[0][0]
        self.l_sum.text = f"Diary entries today: {n}"

    # ---------- Diary ----------
    def diary_tab(self):
        b = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        self.d_title, self.d_note = field("Activity / title"), field("Notes")
        self.d_min = field("Minutes spent (optional)", input_filter="int")
        for w in (self.d_title, self.d_note, self.d_min, btn("Add entry", self.add_diary)):
            b.add_widget(w)
        self.d_rows = Rows()
        b.add_widget(self.d_rows)
        return tab("Diary", b)

    def add_diary(self):
        if not self.d_title.text.strip():
            return
        self.db.q("INSERT INTO diary(day,title,note,minutes) VALUES(?,?,?,?)",
                  (today(), self.d_title.text.strip(), self.d_note.text, int(self.d_min.text or 0)))
        self.d_title.text = self.d_note.text = self.d_min.text = ""
        self.refresh_all()

    def del_row(self, table, rid):
        self.db.q(f"DELETE FROM {table} WHERE id=?", (rid,))
        self.refresh_all()

    # ---------- Money ----------
    def money_tab(self):
        b = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        self.m_kind = Spinner(text="Expense", values=("Expense", "Income"), size_hint_y=None, height=dp(44))
        self.m_cat = Spinner(text="Food", values=CATS, size_hint_y=None, height=dp(44))
        self.m_amt = field("Amount", input_filter="float")
        self.m_note = field("Note")
        self.m_sum = info()
        for w in (self.m_kind, self.m_cat, self.m_amt, self.m_note,
                  btn("Add", self.add_money), self.m_sum):
            b.add_widget(w)
        self.m_rows = Rows()
        b.add_widget(self.m_rows)
        return tab("Money", b)

    def add_money(self):
        try:
            amt = float(self.m_amt.text)
        except ValueError:
            return
        self.db.q("INSERT INTO money(day,kind,category,amount,note) VALUES(?,?,?,?,?)",
                  (today(), self.m_kind.text, self.m_cat.text, amt, self.m_note.text))
        self.m_amt.text = self.m_note.text = ""
        self.refresh_all()

    # ---------- Export ----------
    def export_tab(self):
        b = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        self.x_msg = Label(halign="center")
        self.x_msg.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        b.add_widget(btn("Export all data (CSV)", self.export))
        b.add_widget(self.x_msg)
        return tab("Export", b)

    def export(self):
        folder = sensors.export_dir() or os.getcwd()
        queries = {
            "diary": "SELECT day,title,note,minutes FROM diary ORDER BY day",
            "money": "SELECT day,kind,category,amount,note FROM money ORDER BY day",
            "daily": "SELECT day,steps,screen_min FROM daily ORDER BY day",
            "phone_temp": "SELECT day,tmin,tmax FROM phone_temp ORDER BY day"}
        text = ""
        for name, sql in queries.items():
            cols, rows = self.db.table(sql)
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(cols)
            w.writerows(rows)
            with open(os.path.join(folder, f"lifelog_{name}.csv"), "w", newline="", encoding="utf-8") as f:
                f.write(buf.getvalue())
            text += f"## {name}\n{buf.getvalue()}\n"
        self.x_msg.text = f"Saved 4 CSV files in:\n{folder}\nShare sheet opened."
        sensors.share(text)

    # ---------- Refresh ----------
    def refresh_all(self):
        self.d_rows.fill([(f"{d}  {t}  ({m} min)\n{n}", lambda i=i: self.del_row("diary", i))
                          for i, d, t, n, m in self.db.q(
                              "SELECT id,day,title,note,minutes FROM diary ORDER BY id DESC LIMIT 60")])
        self.m_rows.fill([(f"{d}  {k}  {a:,.0f}  [{c}]\n{n}", lambda i=i: self.del_row("money", i))
                          for i, d, k, c, a, n in self.db.q(
                              "SELECT id,day,kind,category,amount,note FROM money ORDER BY id DESC LIMIT 60")])
        mo = today()[:7] + "%"
        inc = self.db.q("SELECT COALESCE(SUM(amount),0) FROM money WHERE kind='Income' AND day LIKE ?", (mo,))[0][0]
        exp = self.db.q("SELECT COALESCE(SUM(amount),0) FROM money WHERE kind='Expense' AND day LIKE ?", (mo,))[0][0]
        self.m_sum.text = f"This month  In: {inc:,.0f}  Out: {exp:,.0f}  Net: {inc - exp:,.0f}"
        self.refresh_today()


if __name__ == "__main__":
    LifeLog().run()
