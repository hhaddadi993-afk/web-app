# بررسی پروژه (Review) و نقشه راه

## کارهایی که در این مرحله انجام شد
- ساختار پروژه ساخته شد؛ سورس‌های Houdini از روی `MainMenuCommon.xml` استخراج شدند و `build_menu.py` دوباره XML را می‌سازد (تست شد: خروجی دقیقاً با فایل اصلی یکی بود).
- کد بلااستفاده Deadline حذف شد (`hb_submit_deadline`، `_hb_default_deadlinecommand`، `hb_dl_defaults`، `_hb_write`). لیست پاک‌سازی پارم‌های `dl_*` در `install_template.py` ماند تا پارم‌های قدیمی روی SETUP_RUN پاک شوند.
- **باگ:** `RUN ALL CHARACTERS` الگوی `^zebra_01` (exclude) را نمی‌فهمید ولی Run in Background می‌فهمید. حالا هر دو از `_hb_selected_chars` استفاده می‌کنند.
- **باگ:** در Direct mode، File Cacheها bypass می‌شدند و بعد از اجرا همان‌طور می‌ماندند. حالا وضعیت قبلی حتی بعد از خطا برگردانده می‌شود.
- تست با mock: الگوهای `*`، `wildebeest_*`، `^zebra_01`، استخراج نام part، و برگشت bypass بعد از خطا.

## تست نشده (باید در Houdini/Maya امتحان شود)
همه چیزهایی که به `hou` یا `maya.cmds` واقعی نیاز دارند: ساخت UI، اجرای سیم، پروسه‌های background. بعد از نصب XML جدید یک بار «Batch Hair Sim: Setup SETUP_RUN» را دوباره اجرا کنید تا Session Module جدید نصب شود.

## فایل‌های ناقص
`abc_export_by_namespace.py` و `xgen_assign_houdini_cache.py` در این چت در دسترس من نبودند. لطفاً کپی کنید داخل `maya/` یا بفرستید تا اضافه شوند.

## موارد دیده‌شده در `char_pipeline_tool.py` (فعلاً تغییر ندادم)
1. `CharPipelineUI.__init__(parent=maya_main_window())` پیش‌فرض را موقع import محاسبه می‌کند؛ بهتر است `parent=None` و داخل تابع محاسبه شود.
2. `check_xgen` برای هر کاراکتر ممکن است reference را unload/load کند؛ برای ۱۰ کاراکتر کند است. فقط وقتی palette ساخته نشده باشد اجرا می‌شود.
3. Step 1 فقط کنترل‌هایی را برمی‌دارد که `animCurve` وصل دارند؛ کنترل‌هایی که با constraint/driven key حرکت می‌کنند نادیده گرفته می‌شوند.

## پیشنهادهای بعدی (به ترتیب اولویت)
1. **پوشه مشترک `my_pipeline`** + package json برای Houdini + `Maya.env` تا کپی دستی فایل‌ها تمام شود (یک `install.py`).
2. **Maya Shelf** برای `xgen_assign_houdini_cache` و `abc_export` (آیکون + نصب خودکار).
3. **چک RAM حین اجرا** در background (الان فقط قبل از شروع هر سیم چک می‌شود)؛ در صورت کمبود، آخرین job متوقف و دوباره در صف قرار گیرد.
4. **Retry خودکار** برای jobهای background که با خطای license/لود شکست می‌خورند (یک بار).
5. **گزارش نهایی شات** (CSV/JSON): هر کاراکتر × part، زمان، حجم abc، تعداد فریم؛ و چک «تعداد فریم abc خروجی = ۹۵۰–۱۱۰۳».
6. **Validate قبل از export در Maya**: نام namespace معتبر، وجود دوربین `cam_XXXX_YYYY`، و هشدار برای namespaceهای تکراری.
7. تست خودکار با mock برای `build_menu.py` و `session_code.py` (فعلاً دستی انجام شد).
