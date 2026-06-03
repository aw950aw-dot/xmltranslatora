from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
import threading, re, urllib.request, json, xml.etree.ElementTree as ET

Window.clearcolor = (0.04, 0.06, 0.12, 1)
ACCENT = (0, 0.9, 0.63, 1)
CARD = (0.07, 0.1, 0.15, 1)
API_KEY = ""

def call_claude(strings_dict):
    prompt = ("Translate the following English Android strings to Hebrew. "
              "Return ONLY a JSON object with keys=original keys, values=Hebrew translations. "
              "Preserve %s %d %1$s placeholders exactly. No markdown.\n\n"
              + json.dumps(strings_dict, ensure_ascii=False))
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    text = "".join(c.get("text", "") for c in data["content"])
    return json.loads(re.sub(r"```json|```", "", text).strip())

def parse_xml(xml_text):
    root = ET.fromstring(xml_text)
    return [{"name": el.get("name"), "value": el.text or ""}
            for el in root.findall("string") if el.get("translatable") != "false"]

def build_xml(orig, tmap):
    root = ET.fromstring(orig)
    for el in root.findall("string"):
        if el.get("name") in tmap:
            el.text = tmap[el.get("name")]
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")

class TranslatorApp(App):
    def build(self):
        self.title = "XML Translator"
        self.translations = {}
        self.orig_xml = ""
        root = BoxLayout(orientation="vertical", padding=14, spacing=8)
        root.add_widget(Label(text="[b]XML Translator EN→HE[/b]", markup=True,
            font_size="20sp", color=ACCENT, size_hint_y=None, height=42))
        root.add_widget(Label(text="מתרגם קבצי strings.xml לעברית באמצעות Claude AI",
            font_size="12sp", color=(.6,.7,.8,1), size_hint_y=None, height=24))
        root.add_widget(Label(text="Anthropic API Key:", font_size="13sp",
            color=(.7,.8,.9,1), size_hint_y=None, height=26,
            halign="left", text_size=(800, None)))
        self.api_in = TextInput(hint_text="sk-ant-...", password=True, multiline=False,
            size_hint_y=None, height=40, background_color=CARD,
            foreground_color=(.9,.95,1,1), font_size="13sp")
        root.add_widget(self.api_in)
        root.add_widget(Label(text="הדבק את תוכן strings.xml:", font_size="13sp",
            color=(.7,.8,.9,1), size_hint_y=None, height=26,
            halign="left", text_size=(800, None)))
        self.xml_in = TextInput(
            hint_text='<resources>\n    <string name="app_name">My App</string>\n    <string name="hello">Hello</string>\n</resources>',
            multiline=True, size_hint_y=None, height=160,
            background_color=CARD, foreground_color=(.7,.85,1,1), font_size="12sp")
        root.add_widget(self.xml_in)
        self.status_lbl = Label(text="", font_size="12sp", color=ACCENT,
            size_hint_y=None, height=24)
        root.add_widget(self.status_lbl)
        self.pb = ProgressBar(max=100, value=0, size_hint_y=None, height=10)
        root.add_widget(self.pb)
        self.trans_btn = Button(text="תרגם לעברית ←", size_hint_y=None, height=50,
            background_color=ACCENT, color=(0,0,0,1), font_size="16sp", bold=True)
        self.trans_btn.bind(on_press=self.start)
        root.add_widget(self.trans_btn)
        self.grid = GridLayout(cols=1, spacing=3, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        sv = ScrollView(size_hint=(1, 1))
        sv.add_widget(self.grid)
        root.add_widget(sv)
        self.save_btn = Button(text="↓ שמור strings-he.xml", size_hint_y=None, height=50,
            background_color=(.1,.15,.25,1), color=(.4,.5,.6,1), font_size="14sp")
        self.save_btn.bind(on_press=self.save)
        root.add_widget(self.save_btn)
        return root

    def start(self, *a):
        global API_KEY
        API_KEY = self.api_in.text.strip()
        xml = self.xml_in.text.strip()
        if not API_KEY:
            self.popup("שגיאה", "נא להזין Anthropic API Key")
            return
        if not xml:
            self.popup("שגיאה", "נא להדביק קובץ XML")
            return
        self.orig_xml = xml
        self.grid.clear_widgets()
        self.pb.value = 0
        self.trans_btn.disabled = True
        self.status_lbl.text = "מתחיל תרגום..."
        threading.Thread(target=self.translate, args=(xml,), daemon=True).start()

    def translate(self, xml):
        try:
            items = parse_xml(xml)
            if not items:
                Clock.schedule_once(lambda dt: self.popup("שגיאה", "לא נמצאו מחרוזות"))
                Clock.schedule_once(lambda dt: setattr(self.trans_btn, "disabled", False))
                return
            all_t = {}
            batches = [items[i:i+25] for i in range(0, len(items), 25)]
            for i, batch in enumerate(batches):
                pct = int(i / len(batches) * 100)
                Clock.schedule_once(lambda dt, p=pct: (
                    setattr(self.pb, "value", p),
                    setattr(self.status_lbl, "text", f"מתרגם... {p}%")
                ))
                all_t.update(call_claude({s["name"]: s["value"] for s in batch}))
            self.translations = all_t
            Clock.schedule_once(lambda dt: self.show_results(items, all_t))
        except Exception as e:
            Clock.schedule_once(lambda dt, e=e: self.popup("שגיאה", str(e)))
            Clock.schedule_once(lambda dt: setattr(self.trans_btn, "disabled", False))

    def show_results(self, items, t):
        self.pb.value = 100
        self.status_lbl.text = f"✓ {len(items)} מחרוזות תורגמו בהצלחה!"
        self.trans_btn.disabled = False
        self.grid.clear_widgets()
        for item in items:
            n = item["name"]
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=78, padding=6, spacing=2)
            with row.canvas.before:
                Color(0.07, 0.1, 0.15, 1)
                row._rect = Rectangle(pos=row.pos, size=row.size)
            row.bind(pos=lambda w, v: setattr(w._rect, "pos", v),
                     size=lambda w, v: setattr(w._rect, "size", v))
            row.add_widget(Label(text=f"[color=00e5a0]{n}[/color]  →  {item['value']}",
                markup=True, font_size="10sp", size_hint_y=None, height=18,
                halign="left", text_size=(800, None)))
            ti = TextInput(text=t.get(n, item["value"]), multiline=False,
                size_hint_y=None, height=38, background_color=(.05,.08,.13,1),
                foreground_color=(.9,.95,1,1), font_size="13sp")
            ti.bind(text=lambda w, v, n=n: self.translations.update({n: v}))
            row.add_widget(ti)
            self.grid.add_widget(row)
        self.save_btn.background_color = ACCENT
        self.save_btn.color = (0, 0, 0, 1)

    def save(self, *a):
        if not self.translations:
            self.popup("שגיאה", "אין תרגומים לשמירה")
            return
        try:
            try:
                from android.storage import primary_external_storage_path
                path = primary_external_storage_path() + "/Download/strings-he.xml"
            except Exception:
                path = "/sdcard/Download/strings-he.xml"
            with open(path, "w", encoding="utf-8") as f:
                f.write(build_xml(self.orig_xml, self.translations))
            self.popup("נשמר! ✓", f"הקובץ נשמר ב:\n{path}")
        except Exception as e:
            self.popup("שגיאה בשמירה", str(e))

    def popup(self, title, msg):
        c = BoxLayout(orientation="vertical", padding=12, spacing=8)
        c.add_widget(Label(text=msg, font_size="13sp", text_size=(280, None), halign="center"))
        b = Button(text="סגור", size_hint_y=None, height=40,
            background_color=ACCENT, color=(0,0,0,1))
        c.add_widget(b)
        p = Popup(title=title, content=c, size_hint=(.85, .45))
        b.bind(on_press=p.dismiss)
        p.open()

if __name__ == "__main__":
    TranslatorApp().run()
