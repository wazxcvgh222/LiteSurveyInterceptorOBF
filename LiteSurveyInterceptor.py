#!/usr/bin/env python3
"""Lite Survey Interceptor - Full Version
   Bot logic and intelligence and provides an enhanced Tkinter GUI.
"""

import time
import random
import threading
import os
import queue
import tkinter as tk
from tkinter import ttk, messagebox

# Selenium imports are used at runtime; keep imports in try/except for environments where selenium isn't installed.
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.action_chains import ActionChains
except Exception:
    webdriver = None
    By = None
    Options = None
    Service = None
    ActionChains = None

# --------- CONFIG ----------
CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"   # <-- change if needed
CHROME_BINARY = "/usr/bin/google-chrome"            # <-- change if needed
SELENIUM_PROFILE = os.path.expanduser("~/selenium_profile_lite")  # persistent profile
MIN_DELAY_DEFAULT = 1.0
MAX_DELAY_DEFAULT = 2.5

PRESET_WORDS = ["Yes", "No", "Maybe", "Sure", "I agree"]
TEXTAREA_SENTENCES = [
    "I think that's reasonable and I'd consider it.",
    "No additional comments.",
    "I don't have a strong preference.",
    "This seems okay to me."
]

QUESTION_KEYWORDS = {
    "yesno": ["support", "agree", "do you", "should", "is it", "yes/no", "would you"],
    "numbers": ["age", "years", "how many", "number of", "how old"],
    "favorite": ["favorite", "prefer", "which do you prefer"],
    "opinion": ["thoughts", "comments", "suggestions", "opinion", "ideas", "why", "explain"],
    "location": ["city", "state", "country", "where do you live", "residence"]
}

HUMAN_WEIGHTS = {"radio": 0.7, "checkbox": 0.6, "dropdown": 0.8, "text": 0.9, "textarea": 0.9}
NEXT_BUTTON_TEXTS = ["next","submit","continue","enter","go","ok","agree","confirm","send","complete","finish","proceed","advance"]


# ---------- thread-safe logger for GUI ----------
class ThreadLogger:
    def __init__(self, gui_log_callback=None):
        self.q = queue.Queue()
        self.gui_log_callback = gui_log_callback

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        try:
            print(full)
        except Exception:
            pass
        self.q.put(full)

    def attach_gui(self, gui_log_callback):
        self.gui_log_callback = gui_log_callback

    def flush_to_gui(self):
        if not self.gui_log_callback:
            while not self.q.empty():
                try:
                    _ = self.q.get_nowait()
                except queue.Empty:
                    break
            return
        while True:
            try:
                m = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                self.gui_log_callback(m)
            except Exception:
                pass

_shared_logger = ThreadLogger()


# --------- SurveyBot ----------
class SurveyBot:
    def __init__(self, log_func=None):
        # log_func optional; default to shared logger
        self.log = log_func or _shared_logger.log
        self.driver = None
        self.profile = {
            "name": "Default",
            "text": PRESET_WORDS[:],
            "textarea": TEXTAREA_SENTENCES[:],
            "description": "Balanced responses. Risk: Low."
        }
        self.delay_min = MIN_DELAY_DEFAULT
        self.delay_max = MAX_DELAY_DEFAULT
        self.alive = False
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

    # ---------- Driver ----------
    def create_driver_if_needed(self):
        if self.driver is not None:
            return
        if webdriver is None:
            raise RuntimeError("Selenium is not installed in this environment.")
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument(f"--user-data-dir={SELENIUM_PROFILE}")
            if CHROME_BINARY:
                chrome_options.binary_location = CHROME_BINARY
            service = Service(CHROMEDRIVER_PATH)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_window_size(1200, 900)
            self.log("🔧 Selenium Chrome started (persistent profile).")
        except Exception as e:
            self.log(f"❌ Failed to start browser: {e}")
            raise

    # ---------- start / stop ----------
    def configure(self, url, dmin, dmax, profile):
        self.delay_min = float(dmin)
        self.delay_max = float(dmax)
        self.profile = profile
        # if driver not created yet, GUI will handle initial navigation; keep behavior safe

    def start(self):
        with self.lock:
            if not self.alive:
                self.alive = True
                self.running = True
                self.thread = threading.Thread(target=self._thread_main, daemon=True)
                self.thread.start()
                self.log("▶ Automation thread started.")
            else:
                self.running = True
                self.log("▶ Automation resumed.")

    def pause(self):
        self.running = False
        self.log("⏸ Paused.")

    def stop_and_close(self):
        self.running = False
        self.alive = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.4)
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                self.log("🛑 Driver closed.")
        except Exception as e:
            self.log(f"❌ Error closing driver: {e}")

    # ---------- helpers ----------
    def _rand_delay(self):
        return random.uniform(self.delay_min, self.delay_max) + random.uniform(0, 0.4)

    def _interruptible_sleep(self):
        total = self._rand_delay()
        slept = 0.0
        resolution = 0.1
        while slept < total:
            if not self.running:
                return False
            time.sleep(min(resolution, total - slept))
            slept += resolution
        return True

    def _safe_click(self, el):
        # try a sequence of ways to click, including dispatching events for React
        if el is None:
            return False
        try:
            el.click()
            return True
        except Exception:
            pass
        if ActionChains is not None and self.driver is not None:
            try:
                ActionChains(self.driver).move_to_element(el).click().perform()
                return True
            except Exception:
                pass
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.05)
        except Exception:
            pass
        try:
            # dispatch multiple events to trigger frameworks
            self.driver.execute_script('''
                var el = arguments[0];
                function emit(n){ el.dispatchEvent(new MouseEvent(n, {bubbles:true, cancelable:true})); }
                emit('mouseover'); emit('mousemove'); emit('mousedown'); emit('mouseup'); emit('click');
                ''', el)
            return True
        except Exception:
            self.log("❌ Click failed.")
            return False

    def _get_label_text(self, el):
        # try label ancestors and aria labels
        try:
            lbl = el.find_element(By.XPATH, "ancestor::label[1]")
            txt = lbl.text.strip()
            if txt:
                return txt
        except Exception:
            pass
        try:
            lbl = el.find_element(By.XPATH, "preceding::label[1]")
            txt = lbl.text.strip()
            if txt:
                return txt
        except Exception:
            pass
        try:
            aria = (el.get_attribute("aria-label") or "").strip()
            if aria:
                return aria
        except Exception:
            pass
        try:
            labid = (el.get_attribute("aria-labelledby") or "").strip()
            if labid:
                nodes = self.driver.find_elements(By.ID, labid)
                if nodes:
                    return nodes[0].text.strip()
        except Exception:
            pass
        return ""

    def _detect_captcha(self):
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for f in iframes:
                src = (f.get_attribute("src") or "").lower()
                if "recaptcha" in src or "hcaptcha" in src or "geetest" in src:
                    return True
            if self.driver.find_elements(By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha')]"):
                return True
            return False
        except Exception:
            return False

    # ---------- intelligence ----------
    def intelligent_answer(self, qtext, options=None, qtype="text"):
        q = (qtext or "").lower()
        if any(k in q for k in QUESTION_KEYWORDS["yesno"]):
            yes_weight = HUMAN_WEIGHTS.get("radio", 0.7)
            return random.choices(["Yes","No"], weights=[yes_weight, 1-yes_weight])[0]
        if any(k in q for k in QUESTION_KEYWORDS["numbers"]):
            return str(random.randint(18, 65))
        if options and any(k in q for k in QUESTION_KEYWORDS["favorite"]):
            return random.choice(options)
        if any(k in q for k in QUESTION_KEYWORDS["opinion"]):
            # longer opinion responses sometimes
            if random.random() < 0.5:
                return random.choice(self.profile.get("textarea", TEXTAREA_SENTENCES))
            else:
                return random.choice(self.profile.get("text", PRESET_WORDS))
        if options:
            try:
                return random.choice(options)
            except Exception:
                return options[0]
        return random.choice(self.profile.get("text", PRESET_WORDS))

    # ---------- answering routines ----------
    def _answer_radios(self):
        radios = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], [role='radio']")
        if not radios:
            return
        seen = set()
        for r in radios:
            if not self.running:
                return
            try:
                anc = r.find_element(By.XPATH, "ancestor::div[1]")
                cid = anc.get_attribute("data-interceptor-id") or anc.get_attribute("id") or str(hash(anc))
            except Exception:
                cid = str(hash(r))
            if cid in seen:
                continue
            seen.add(cid)
            try:
                opts = anc.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            except Exception:
                opts = [r]
            if any(o.is_selected() for o in opts):
                continue
            opts_text = []
            for o in opts:
                txt = (o.get_attribute("value") or o.get_attribute("aria-label") or self._get_label_text(o) or "").strip()
                opts_text.append(txt or "<opt>")
            question = self._get_label_text(r) or "question"
            pick_text = self.intelligent_answer(question, opts_text, "radio")
            chosen = None
            for i, o in enumerate(opts):
                if opts_text[i].lower() == str(pick_text).lower():
                    chosen = o
                    break
            if chosen is None:
                chosen = random.choice(opts)
            if self._safe_click(chosen):
                self.log(f"[Radio] → {pick_text}")
            if not self._interruptible_sleep():
                return

    def _answer_checkboxes(self):
        boxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], [role='checkbox']")
        if not boxes:
            return
        seen = set()
        for b in boxes:
            if not self.running:
                return
            try:
                anc = b.find_element(By.XPATH, "ancestor::div[1]")
                cid = anc.get_attribute("id") or anc.get_attribute("data-interceptor-id") or str(hash(anc))
            except Exception:
                cid = str(hash(b))
            if cid in seen:
                continue
            seen.add(cid)
            try:
                group = anc.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            except Exception:
                group = [b]
            candidates = [g for g in group if not g.is_selected()]
            if not candidates:
                continue
            count = random.randint(2, min(5, len(candidates)))
            to_select = random.sample(candidates, count)
            for s in to_select:
                if not self.running:
                    return
                if self._safe_click(s):
                    lab = self._get_label_text(s) or s.get_attribute("value") or "<box>"
                    self.log(f"[Checkbox] → {lab}")
                if not self._interruptible_sleep():
                    return

    def _answer_selects(self):
        selects = self.driver.find_elements(By.TAG_NAME, "select")
        for sel in selects:
            if not self.running:
                return
            try:
                opts = sel.find_elements(By.TAG_NAME, "option")
                candidates = [(o, (o.get_attribute("value") or o.text or "").strip()) for o in opts if (o.get_attribute("value") or o.text).strip() != ""]
                if not candidates:
                    continue
                vals = [v for (_, v) in candidates]
                question = self._get_label_text(sel) or "select"
                is_multiple = sel.get_attribute("multiple")
                if is_multiple:
                    count = random.randint(2, min(5, len(candidates)))
                    chosen = random.sample([el for (el, _) in candidates], count)
                    for el in chosen:
                        if not self.running: return
                        self._safe_click(el)
                        self.log(f"[Multi-Select] → {el.text.strip() or el.get_attribute('value')}")
                        if not self._interruptible_sleep(): return
                else:
                    pick = self.intelligent_answer(question, vals, qtype="dropdown")
                    chosen_el = None
                    for (el, v) in candidates:
                        if v.lower() == pick.lower():
                            chosen_el = el
                            break
                    if chosen_el is None:
                        chosen_el = random.choice([el for (el, _) in candidates])
                    self._safe_click(chosen_el)
                    self.log(f"[Select] → {chosen_el.text.strip() or chosen_el.get_attribute('value')}")
            except Exception as e:
                self.log(f"❌ Select error: {e}")
            if not self._interruptible_sleep():
                return

    def _answer_texts(self):
        inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type]), [role='textbox']")
        for inp in inputs:
            if not self.running:
                return
            try:
                cur = (inp.get_attribute("value") or "").strip()
                if cur:
                    continue
                question = self._get_label_text(inp) or "text"
                ans = self.intelligent_answer(question, qtype="text")
                try:
                    inp.clear()
                except Exception:
                    pass
                inp.send_keys(ans)
                self.log(f"[Text] → {ans}")
            except Exception as e:
                self.log(f"❌ Text fill error: {e}")
            if not self._interruptible_sleep():
                return

    def _answer_textareas(self):
        areas = self.driver.find_elements(By.TAG_NAME, "textarea")
        for ta in areas:
            if not self.running:
                return
            try:
                cur = (ta.get_attribute("value") or "").strip()
                if cur:
                    continue
                question = self._get_label_text(ta) or "textarea"
                ans = self.intelligent_answer(question, qtype="textarea")
                try:
                    ta.clear()
                except Exception:
                    pass
                ta.send_keys(ans)
                self.log(f"[Textarea] → {ans}")
            except Exception as e:
                self.log(f"❌ Textarea fill error: {e}")
            if not self._interruptible_sleep():
                return

    def _click_next_if_any(self):
        try:
            for t in NEXT_BUTTON_TEXTS:
                btns = self.driver.find_elements(By.XPATH,
                    f"//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{t}')]")
                for btn in btns:
                    if self._safe_click(btn):
                        self.log("🟢 Clicked Next/Submit")
                        return True
            for t in NEXT_BUTTON_TEXTS:
                btns = self.driver.find_elements(By.XPATH,
                    f"//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{t}')]")
                for btn in btns:
                    if self._safe_click(btn):
                        self.log("🟢 Clicked Submit")
                        return True
            try:
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                for f in forms:
                    sub = f.find_elements(By.TAG_NAME, "button")
                    for b in sub:
                        if b.text and any(x in b.text.lower() for x in NEXT_BUTTON_TEXTS):
                            if self._safe_click(b):
                                self.log("🟢 Clicked Next (form button)")
                                return True
            except Exception:
                pass
            return False
        except Exception as e:
            self.log(f"❌ Next button search error: {e}")
            return False

    # ---------- loop ----------
    def _thread_main(self):
        self.log("Thread ready.")
        while self.alive:
            if not self.running:
                time.sleep(0.12)
                continue
            try:
                if self._detect_captcha():
                    self.log("⚠️ Captcha detected - please solve it in browser. Automation paused.")
                    self.running = False
                    continue
                self._answer_radios()
                if not self.running: continue
                self._answer_checkboxes()
                if not self.running: continue
                self._answer_texts()
                if not self.running: continue
                self._answer_textareas()
                if not self.running: continue
                self._answer_selects()
                if not self.running: continue

                clicked = self._click_next_if_any()
                if not clicked:
                    self.log("⚠️ No next/submit — automation paused for this page.")
                    self.running = False
            except Exception as e:
                self.log(f"❌ Automation loop error: {e}")
                self.running = False
        self.log("Thread stopped (alive=False).")


# --------- GUI (dark/orange LANC-ish) ----------
class SurveyGUI:
    def __init__(self, bot: SurveyBot):
        self.bot = bot
        _shared_logger.attach_gui(self._gui_log)
        self.bot.log = _shared_logger.log

        self.root = tk.Tk()
        self.root.title("Lite Survey Interceptor")
        self.root.geometry("980x700")
        self.root.configure(bg="#1e1e1e")
        self.root.tk.call('tk', 'scaling', 1.0)

        # theme / style
        self.current_theme = {
            "bg": "#1e1e1e", "fg": "#ffffff", "btn_bg": "#ff8a00",
            "btn_fg": "#000", "entry_bg": "#2c2c2c", "entry_fg": "#ffffff"
        }

        # profiles
        self.profiles_data = {
            "Default": {"desc": "Balanced responses. Risk: Low.", "text": PRESET_WORDS[:], "textarea": TEXTAREA_SENTENCES[:]},
            "Conservative": {"desc": "Cautious approach. Risk: Very Low.", "text": ["No","Maybe"], "textarea": ["No comment."]},
            "Bold": {"desc": "Fast/aggressive responses. Risk: Medium.", "text": ["Yes","Absolutely"], "textarea": ["Strongly agree."]}
        }

        self.panels = {}
        # layout
        self.sidebar = tk.Frame(self.root, bg="#2c2c2c", width=220)
        self.sidebar.pack(side="left", fill="y")
        tk.Label(self.sidebar, text="MENU", fg="#ffffff", bg="#2c2c2c", font=("Segoe UI", 12, "bold")).pack(pady=10)
        self.menu_buttons = {}
        for name in ["Dashboard", "Profiles", "Settings"]:
            btn = tk.Button(self.sidebar, text=name, bg="#3a3a3a", fg="#ffffff", bd=0, relief="flat",
                            font=("Segoe UI", 10, "bold"), activebackground="#505050",
                            command=lambda n=name: self.show_panel(n))
            btn.pack(fill="x", padx=12, pady=6)
            self.apply_rounded_corners(btn)
            self.menu_buttons[name] = btn

        self.main_panel = tk.Frame(self.root, bg=self.current_theme["bg"])
        self.main_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # create subpanels
        self.create_dashboard_panel()
        self.create_profiles_panel()
        self.create_settings_panel()
        self.show_panel("Dashboard")

        # status
        self.status_var = tk.StringVar(value="Idle")
        status = tk.Label(self.root, textvariable=self.status_var, bg="#111111", fg="#ffa500", anchor="w")
        status.pack(fill="x", side="bottom")

        # schedule flush
        self.root.after(100, self._periodic_flush_logs)

    def apply_rounded_corners(self, widget):
        try:
            widget.configure(highlightthickness=0, relief="flat", bd=0)
        except Exception:
            pass

    def _periodic_flush_logs(self):
        _shared_logger.flush_to_gui()
        self.root.after(100, self._periodic_flush_logs)

    # Panels
    def create_dashboard_panel(self):
        panel = tk.Frame(self.main_panel, bg=self.current_theme["bg"])
        tk.Label(panel, text="Lite Survey Interceptor", fg="#ffa500", bg=self.current_theme["bg"], font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(panel, text="Tip: READ the readme file before using this, otherwise you will be confused.", fg="#ffa500", bg=self.current_theme["bg"], font=("Segoe UI", 10, "bold")).pack(anchor="w")

        ctrl_frame = tk.Frame(panel, bg=self.current_theme["bg"])
        ctrl_frame.pack(fill="x", pady=8)
        tk.Label(ctrl_frame, text="Survey URL:", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).grid(row=0, column=0, sticky="w")
        self.url_entry = tk.Entry(ctrl_frame, width=70, bg=self.current_theme["entry_bg"], fg=self.current_theme["entry_fg"], insertbackground=self.current_theme["entry_fg"])
        self.url_entry.grid(row=0, column=1, padx=6)

        self.start_btn = tk.Button(ctrl_frame, text="Intercept (Open + Start)", bg=self.current_theme["btn_bg"], fg=self.current_theme["btn_fg"],
                                   bd=0, font=("Segoe UI", 10, "bold"), command=self.start_pressed)
        self.start_btn.grid(row=0, column=2, padx=6)
        self.apply_rounded_corners(self.start_btn)

        self.pause_btn = tk.Button(ctrl_frame, text="Pause", bg="#333333", fg="#fff", bd=0, font=("Segoe UI", 10, "bold"), command=self.pause_pressed)
        self.pause_btn.grid(row=0, column=3, padx=6)
        self.apply_rounded_corners(self.pause_btn)

        cfg_frame = tk.Frame(panel, bg=self.current_theme["bg"])
        cfg_frame.pack(fill="x", pady=6)
        tk.Label(cfg_frame, text="Min(s):", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).grid(row=0, column=0, sticky="w")
        self.min_delay = tk.Entry(cfg_frame, width=6, bg=self.current_theme["entry_bg"], fg=self.current_theme["entry_fg"])
        self.min_delay.insert(0, str(MIN_DELAY_DEFAULT))
        self.min_delay.grid(row=0, column=1, padx=4)
        tk.Label(cfg_frame, text="Max(s):", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).grid(row=0, column=2, sticky="w")
        self.max_delay = tk.Entry(cfg_frame, width=6, bg=self.current_theme["entry_bg"], fg=self.current_theme["entry_fg"])
        self.max_delay.insert(0, str(MAX_DELAY_DEFAULT))
        self.max_delay.grid(row=0, column=3, padx=4)

        tk.Label(cfg_frame, text="Active Profile:", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).grid(row=0, column=4, padx=(12,0))
        self.active_profile_label = tk.Label(cfg_frame, text=self.bot.profile.get("name","Default"), fg="#ffc87a", bg=self.current_theme["bg"])
        self.active_profile_label.grid(row=0, column=5)

        tk.Label(panel, text="Log:", fg="#ffa500", bg=self.current_theme["bg"]).pack(anchor="w", pady=(8,0))
        self.log_box = tk.Text(panel, bg="#121212", fg="#ffffff", height=22, wrap="word")
        self.log_box.pack(fill="both", expand=True, pady=6)
        self.log_tag_index = 0
        self.log_box.tag_configure("odd", foreground="#ffffff")
        self.log_box.tag_configure("even", foreground="#ffd59a")

        self.panels["Dashboard"] = panel

    def _gui_log(self, msg):
        try:
            tag = "even" if (self.log_tag_index % 2 == 0) else "odd"
            self.log_box.insert("end", msg + "\n", (tag,))
            self.log_box.see("end")
            self.log_tag_index += 1
        except Exception:
            pass

    def create_profiles_panel(self):
        panel = tk.Frame(self.main_panel, bg=self.current_theme["bg"])
        tk.Label(panel, text="Profiles", fg="#ffa500", bg=self.current_theme["bg"], font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0,10))

        self.profile_var = tk.StringVar(value=self.bot.profile.get("name","Default"))
        self.profile_desc_var = tk.StringVar(value=self.profiles_data[self.profile_var.get()]["desc"])

        rb_frame = tk.Frame(panel, bg=self.current_theme["bg"])
        rb_frame.pack(anchor="w", pady=6)
        for p in self.profiles_data.keys():
            rb = tk.Radiobutton(rb_frame, text=p, variable=self.profile_var, value=p,
                                fg=self.current_theme["fg"], bg=self.current_theme["entry_bg"],
                                selectcolor="#505050", font=("Segoe UI", 12),
                                command=self.update_profile_desc)
            rb.pack(anchor="w", pady=3, padx=4, fill="x")
            self.apply_rounded_corners(rb)

        self.desc_label = tk.Label(panel, textvariable=self.profile_desc_var, fg="#ffc87a",
                                   bg=self.current_theme["bg"], font=("Segoe UI", 10), wraplength=520, justify="left")
        self.desc_label.pack(anchor="w", pady=6)

        self.save_profile_btn = tk.Button(panel, text="Save Profile (apply to bot)", bg=self.current_theme["btn_bg"],
                                          fg=self.current_theme["btn_fg"], font=("Segoe UI", 10, "bold"),
                                          command=self.save_profile)
        self.save_profile_btn.pack(pady=10)
        self.apply_rounded_corners(self.save_profile_btn)

        self.panels["Profiles"] = panel

    def create_settings_panel(self):
        panel = tk.Frame(self.main_panel, bg=self.current_theme["bg"])
        tk.Label(panel, text="Settings", fg="#ffa500", bg=self.current_theme["bg"], font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0,10))

        tk.Label(panel, text="Theme:", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).pack(anchor="w")
        self.theme_var = tk.StringVar(value="Dark/Orange")
        themes = ["Dark/Orange", "Slate/Blue", "Red/Dark", "Green/Slate"]
        self.theme_combo = ttk.Combobox(panel, textvariable=self.theme_var, values=themes, state="readonly")
        self.theme_combo.pack(anchor="w", pady=5)
        self.theme_combo.bind("<<ComboboxSelected>>", self.change_theme)

        tk.Label(panel, text="Selenium profile folder:", fg=self.current_theme["fg"], bg=self.current_theme["bg"]).pack(anchor="w", pady=(12,0))
        self.profile_path_label = tk.Label(panel, text=SELENIUM_PROFILE, bg=self.current_theme["bg"], fg="#ddd")
        self.profile_path_label.pack(anchor="w", pady=2)

        self.panels["Settings"] = panel

    def show_panel(self, name):
        for p in self.panels.values():
            p.pack_forget()
        self.panels[name].pack(fill="both", expand=True)
        for n, btn in self.menu_buttons.items():
            btn.configure(bg="#3a3a3a" if n != name else "#505050")

    def update_profile_desc(self):
        p = self.profile_var.get()
        self.profile_desc_var.set(self.profiles_data[p]["desc"])

    def save_profile(self):
        p = self.profile_var.get()
        pd = self.profiles_data[p]
        self.bot.profile = {
            "name": p,
            "text": pd.get("text", PRESET_WORDS[:]),
            "textarea": pd.get("textarea", TEXTAREA_SENTENCES[:]),
            "description": pd.get("desc", "")
        }
        self.active_profile_label.config(text=p)
        _shared_logger.log(f"Profile saved and applied: {p} - {pd.get('desc')}")
        self._gui_log(f"[Profile] saved: {p} — {pd.get('desc')}")

    def change_theme(self, event=None):
        theme = self.theme_var.get()
        if theme == "Dark/Orange":
            self.current_theme = {
                "bg": "#1e1e1e", "fg": "#ffffff", "btn_bg": "#ff8a00",
                "btn_fg": "#000", "entry_bg": "#2c2c2c", "entry_fg": "#ffffff"
            }
        elif theme == "Slate/Blue":
            self.current_theme = {
                "bg": "#222633", "fg": "#e6eef8", "btn_bg": "#1e88e5",
                "btn_fg": "#ffffff", "entry_bg": "#2b3140", "entry_fg": "#e6eef8"
            }
        elif theme == "Red/Dark":
            self.current_theme = {
                "bg": "#1b1b1b", "fg": "#f8d7d7", "btn_bg": "#d32f2f",
                "btn_fg": "#ffffff", "entry_bg": "#2a2a2a", "entry_fg": "#ffffff"
            }
        else:  # Green/Slate
            self.current_theme = {
                "bg": "#17201a", "fg": "#dff5e1", "btn_bg": "#2e7d32",
                "btn_fg": "#ffffff", "entry_bg": "#22312a", "entry_fg": "#dff5e1"
            }
        self.apply_theme()

    def apply_theme(self):
        self.root.configure(bg=self.current_theme["bg"])
        self.main_panel.configure(bg=self.current_theme["bg"])
        for panel in self.panels.values():
            panel.configure(bg=self.current_theme["bg"])
        try:
            self.log_box.configure(bg="#121212" if self.current_theme["bg"].startswith("#1e") else "#23293a", fg=self.current_theme["fg"])
        except Exception:
            pass
        try:
            self.active_profile_label.configure(bg=self.current_theme["bg"], fg="#ffc87a")
        except Exception:
            pass
        for btn in [self.start_btn, self.pause_btn, self.save_profile_btn]:
            try:
                btn.configure(bg=self.current_theme["btn_bg"], fg=self.current_theme["btn_fg"])
            except Exception:
                pass

    # Button handlers
    def start_pressed(self):
        url = self.url_entry.get().strip()
        # validate delays
        try:
            dmin = float(self.min_delay.get())
            dmax = float(self.max_delay.get())
            if dmin < 0 or dmax < 0 or dmin > dmax:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid delays", "Enter valid min/max (min <= max).")
            return
        # If driver exists and currently paused, resume without reloading
        if self.bot.driver and self.bot.alive and not self.bot.running:
            self.bot.delay_min = dmin
            self.bot.delay_max = dmax
            self.bot.start()
            self.status_var.set("Running")
            return
        if not url:
            messagebox.showwarning("No URL", "Enter the survey URL to intercept.")
            return
        try:
            # configure bot
            self.bot.configure(url, dmin, dmax, self.bot.profile)
            # create driver if needed
            if not self.bot.driver:
                self.bot.create_driver_if_needed()
                # open url
                try:
                    self.bot.driver.get(url)
                    self._gui_log(f"🌐 Opened {url} in Selenium browser.")
                except Exception as e:
                    self._gui_log(f"❌ Failed opening URL in driver: {e}")
            # start automation thread
            self.bot.start()
            self.status_var.set("Running")
        except Exception as e:
            self._gui_log(f"❌ Could not configure/start: {e}")

    def pause_pressed(self):
        self.bot.pause()
        self.status_var.set("Paused")

    def open_new_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter the survey URL to open.")
            return
        try:
            if not self.bot.driver:
                self.bot.create_driver_if_needed()
            self.bot.driver.get(url)
            self._gui_log(f"🌐 Opened {url} in Selenium browser.")
        except Exception as e:
            self._gui_log(f"❌ Could not open URL: {e}")

    def quit_app(self):
        if messagebox.askyesno("Quit", "Quit and close browser?"):
            try:
                self.bot.stop_and_close()
            except Exception:
                pass
            self.root.destroy()

    def run(self):
        _shared_logger.attach_gui(self._gui_log)
        self.active_profile_label.config(text=self.bot.profile.get("name", "Default"))
        self.root.mainloop()


# ---------- main ----------
if __name__ == "__main__":
    bot = SurveyBot(log_func=_shared_logger.log)
    gui = SurveyGUI(bot)
    gui.run()
