# سیستم کنترل دستگاه چاپ تامپو کاپ بسته‌ی بزرگ (Large-Format Closed-Cup Pad Printer)

کنترلر: **Delta DVP-28SV211T** · HMI: **Delta DOP-107BV** · درایور: **Leadshine CL57** + استپر کلوزلوپ NEMA24 · Z: پنوماتیک SMC MGPM

| فایل | محتوا |
|---|---|
| [docs/01_design_review.md](docs/01_design_review.md) | **نقد فنی طرح: مشکلات و پیشنهادها** (مطالعه‌ی آن پیش از ساخت ضروری است) |
| [docs/02_io_map.md](docs/02_io_map.md) | جدول کامل X، Y، M، D و T |
| [docs/03_state_machine.md](docs/03_state_machine.md) | ماشین وضعیت: هومینگ، اتومات، جوهرزنی و دستی |
| [docs/04_plc_program.md](docs/04_plc_program.md) | توضیح کد نردبانی، اینترلاک‌های ضدبرخورد و چک‌لیست راه‌اندازی |
| [docs/05_hmi.md](docs/05_hmi.md) | ساختار صفحات HMI، سطوح دسترسی و Recipe |
| [docs/06_electrical_safety_troubleshooting.md](docs/06_electrical_safety_troubleshooting.md) | تغذیه، ضد نویز، گراندینگ، مدار ایمنی، جدول آلارم‌ها و عیب‌یابی |
| [plc/TampoPrinter_SV2.il](plc/TampoPrinter_SV2.il) | برنامه‌ی کامل PLC (Instruction List) |
| [hmi/tag_list.csv](hmi/tag_list.csv) | فهرست Tagهای HMI |
| [hmi/hmi_mockup.html](hmi/hmi_mockup.html) | **نمونه‌ی تعاملی ۹ صفحه‌ی HMI** با آدرس هر شیء |
| [plc/TampoPrinter_SV2_clean.txt](plc/TampoPrinter_SV2_clean.txt) | برنامه‌ی PLC بدون توضیحات برای WPLSoft |
| [tools/plc_sim.py](tools/plc_sim.py) | شبیه‌ساز و تست خودکار برنامه‌ی PLC |
| [docs/07_bom_cost_estimate.md](docs/07_bom_cost_estimate.md) | برآورد هزینه‌ی قطعات (BOM) |
| [bom/bom_estimate.csv](bom/bom_estimate.csv) | فهرست قطعات و قیمت برای Excel |
| [docs/08_field_data_redesign.md](docs/08_field_data_redesign.md) | **داده‌های دستگاه موجود و طراحی از صفر** (معتبرترین بخش) |
| [docs/09_final_bom.md](docs/09_final_bom.md) | **لیست خرید نهایی طرح جدید** |
| [docs/10_operators_shifts_erp.md](docs/10_operators_shifts_erp.md) | **ورود کارگر، شیفت‌ها و ارسال آمار به ERP** |
| [tools/erp_gateway.py](tools/erp_gateway.py) | دروازه‌ی Modbus TCP به ERP |
| [docs/11_test_report.md](docs/11_test_report.md) | **گزارش تست نقطه‌به‌نقطه** (خودکار) |
| [docs/12_zones_error_handling.md](docs/12_zones_error_handling.md) | **مناطق ممنوع، مدیریت خطا و بازیابی نرم‌افزاری** |
| [tools/test_suite.py](tools/test_suite.py) | مجموعه‌ی تست (۴۶ سناریو، موازی) |
| [tools/axis_sizing.py](tools/axis_sizing.py) | محاسبه‌ی سرعت پیک، گشتاور، نسبت اینرسی و نیروی جک |
| [docs/13_3d_design.md](docs/13_3d_design.md) | **طراحی سه‌بعدی کل دستگاه** (قطعات و اسکلت)، راهنمای AutoCAD و ساخت |
| [cad/tampo_machine.py](cad/tampo_machine.py) | مدل پارامتریک CadQuery: خروجی STEP، DXF ورق‌ها، نقشه‌ی کلی، لیست برش و بررسی تداخل |
| [cad/out/tampo_viewer.html](cad/out/tampo_viewer.html) | نمایشگر سه‌بعدی با انیمیشن چرخه‌ی چاپ (در مرورگر باز کنید) |

## مهم‌ترین نتیجه‌ها (طرح نهایی بر اساس دستگاه موجود)

1. **Z پنوماتیک می‌ماند:** جک **SC63×100** (حدود ۱۶۰ کیلوگرم نیرو، مثل دستگاه فعلی)، به همراه شیر 3/8، شیر تخلیه‌ی سریع، رگولاتور جدا و پایلوت‌چک.
2. **X:** استپر کلوزلوپ ۴ N·m با گیربکس ۱:۳ و تسمه‌ی HTD5M عرض ۲۵. کورس ۱۰۱۰ mm: پد تا ۷۰ سانت از بدنه بیرون می‌آید و روی **دیسک پلاستیکی** (مثلاً Ø1000/500) روی میز گردانِ پیچ‌شده به دستگاه چاپ می‌کند. جرم متحرک ۲۲ kg.
3. **Y:** همان استپر، مستقیم، روی **همان تسمه‌ی ۲۰ mm** دستگاه فعلی با پولی ۲۴ دندانه.
4. **سیکل:** جوهرزنی موازی، هم‌پوشانی حرکت X و Z، و برداشت زودتر. از **۱۰.۵ ثانیه** به حدود **۴.۵ تا ۵.۵ ثانیه**.
5. **ایمنی:** پرده‌ی نوری و رله‌ی ایمنی الزامی‌اند. اپراتور بعد از هر چاپ دستش را زیر پد می‌برد.
6. **اینترلاک ضدبرخورد:** سنسور ارتفاع امن (X20) و آلارم‌های A10 و A17 که قانون «پد روی سطح = X ساکن» را تضمین می‌کنند.

> ⚠️ کد یک **طرح مرجع** است و روی سخت‌افزار واقعی تست نشده است. شماره‌ی رجیسترها و بیت‌های ویژه‌ی SV2 را با دفترچه‌ی فریمور خودتان تطبیق دهید. PLC استاندارد جایگزین مدار ایمنی نیست.

## اجرای محاسبات

```bash
python3 cad/tampo_machine.py      # مدل سه‌بعدی و همه‌ی خروجی‌های ساخت (نیاز: pip install cadquery ezdxf)
python3 tools/axis_sizing.py
```
