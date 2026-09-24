# ۷. برآورد هزینه‌ی قطعات (BOM)

> **تاریخ برآورد:** شهریور ۱۴۰۵ · **واحد:** میلیون تومان
> فایل قابل باز شدن در Excel: [`bom/bom_estimate.csv`](../bom/bom_estimate.csv)

## ⚠️ اعتبار اعداد (پیش از استفاده بخوانید)

* از محیط اجرای این پروژه، دسترسی مستقیم به **ترب** و بیشتر فروشگاه‌های ایرانی (پارتینه، مانا موتور و مانند آن‌ها) **مسدود بود**. اعداد از سه منبع جمع شده‌اند:
  * **user:** قیمتی که خودتان اعلام کردید (PLC و HMI).
  * **search:** قیمتی که در خلاصه‌ی نتایج جستجو از ترب و فروشگاه‌ها دیده شد. **تاریخ این قیمت‌ها معلوم نیست.** برای مثال، در نتایج جستجو برای همین PLC قیمت‌هایی از ۱۰.۵ تا ۴۰.۶ میلیون دیده شد. عدد پایین‌تر احتمالاً قدیمی است.
  * **estimate:** برآورد مهندسی من، هم‌سطح با قیمت اعلامی شما برای PLC و HMI. **این‌ها استعلام نیستند.**
* قیمت کالاهای **اصل** (SMC، Pilz، MeanWell و Leadshine) با **کپی یا چینی** معمولاً ۲ تا ۵ برابر فرق دارد. سنسور D-M9N و شیرهای SMC تقلبی زیاد دارند.
* پیش از خرید، سه قلم گران را **استعلام کتبی** بگیرید: رله‌ی ایمنی، جک Z و مجموعه‌ی موتور و درایور.

## ستون‌های دلاری

* **قیمت جهانی (USD):** قیمت‌هایی که از **سایت‌های مرجع خارجی** در نتایج جستجو دیده شد (DigiKey، RS، MISUMI، MROSupply، AutomationDirect، Automation Distribution، eBay و فروشگاه‌های رسمی)، در شهریور ۱۴۰۵ (سپتامبر ۲۰۲۶). لینک هر قلم در ستون «منبع» آمده است. قیمت‌ها **بدون حمل، گمرک و مالیات** هستند.
  * اقلامی که قیمتشان در سایت‌ها پیدا نشد با برچسب *برآورد* مشخص شده‌اند: گیربکس ۱:۳، تسمه، کنتاکتور و اقلام عمومی تابلو.
  * صفحه‌ی سایت‌ها مستقیم باز نشد (دسترسی از این محیط مسدود بود). قیمت‌ها از متن نتایج جستجو خوانده شده‌اند.
* **معادل دلاری قیمت ایران:** قیمت تومانی تقسیم بر نرخ دلار آزاد **≈ ۲۳۱٬۰۰۰ تومان** (۳۰ شهریور ۱۴۰۵).

> **نکته:** جمع قیمت‌های بازار ایران تقریباً **34٪ تا 37٪ قیمت جهانی** است. قیمت فروشگاه‌ها هنوز به نرخ روز دلار نرسیده است. با ورود بار جدید، قیمت‌ها احتمالاً به **قیمت جهانی × ۲۳۱ هزار تومان** بعلاوه‌ی هزینه‌ی واردات نزدیک می‌شوند. برای کل تجهیزات این یعنی تقریباً **702 تا 1,123 میلیون تومان** بدون هزینه‌ی واردات.

## جمع‌بندی بر اساس گروه

| گروه | قیمت جهانی (USD) | تومان ایران (میلیون) | معادل دلاری قیمت ایران |
|---|---:|---:|---:|
| کنترل | $435 تا $626 | 61.0 تا 65.0 | $265 تا $282 |
| حرکت | $256 تا $344 | 35.0 تا 60.0 | $152 تا $260 |
| تغذیه | $124 تا $124 | 7.5 تا 12.5 | $32 تا $54 |
| پنوماتیک | $587 تا $865 | 36.2 تا 66.4 | $156 تا $286 |
| سنسورها | $156 تا $232 | 5.2 تا 12.4 | $22 تا $52 |
| ایمنی | $918 تا $1,344 | 40.0 تا 86.0 | $173 تا $373 |
| مکانیک | $133 تا $306 | 9.5 تا 29.3 | $39 تا $125 |
| تابلو | $430 تا $1,020 | 43.0 تا 84.0 | $187 تا $364 |
| **جمع کل** | **$3,039 تا $4,861** | **237 تا 416** | **$1,026 تا $1,796** |

## جدول اقلام

| قلم | مدل | تعداد | قیمت جهانی واحد (USD) | جمع ردیف (USD) | منبع | معادل دلاری قیمت ایران (واحد) |
|---|---|:-:|---|---:|---|---|
| PLC | Delta DVP28SV11T2 | 1 | $182 تا 330 | $182 تا 330 | [YingZhou / PLC ERA / eBay](https://www.ebay.com/itm/395576838844) | $152 |
| HMI 7in | Delta DOP-107BV | 1 | $136 تا 169 | $136 تا 169 | [eBay (+$20–50 حمل)](https://www.ebay.com/itm/185015742358) | $87 |
| Expansion I/O 8DI/8DO | Delta DVP16SP11T | 1 | $117 تا 127 | $117 تا 127 | [WI Automation / PLC Direct](https://plc-direct.com/products/dvp16sp11t) | $26 تا 43 |
| Closed-loop driver | Leadshine CL57 | 2 | $54 تا 68 | $108 تا 136 | [Cloudray / AliExpress](https://www.cloudraylaser.com/products/cloudray-cl57-24-48vdc-3-6a-leadshine-closed-loop-stepper-motor-driver) | $35 تا 61 |
| Closed-loop motor NEMA24 4Nm | 60HSE4N | 2 | $44 | $88 | [Oyostepper 24HS40-5004D-E1000](https://www.oyostepper.com/goods-1263-S-Series-Nema-24-Closed-Loop-Stepper-Motor-18-Deg-40-Nm56645ozin-50A-2-Phase-with-Optical-Incremental-Encoder.html) | $26 تا 43 |
| Planetary gearbox 1:3 (X) | PLF60-3 | 1 | $60 تا 120 | $60 تا 120 | *یافت نشد* (برآورد) | $30 تا 52 |
| PSU 48V 10A | MeanWell NDR-480-48 / SE-600-48 | 1 | $106 | $106 | [DigiKey NDR-480-48](https://www.digikey.com/en/products/detail/mean-well-usa-inc/NDR-480-48/7705225) | $26 تا 43 |
| PSU 24V 6.5A | MeanWell LRS-150-24 | 1 | $18 | $18 | [DigiKey LRS-150-24](https://www.digikey.com/en/products/detail/mean-well-usa-inc/LRS-150-24/7705015) | $6 تا 11 |
| Guided cylinder (current) | SMC MGPM25-200 | 1 | $178 تا 332 | $178 تا 332 | [eBay / MROSupply / RS](https://us.rs-online.com/product/smc-corporation/mgpm25-200z/70605821/) | $65 تا 108 |
| 5/2 double solenoid valve | SMC SY5220 (Airtac 4V220 1-2) | 1 | $70 تا 97 | $70 تا 97 | [MISUMI / MROSupply / Southern Controls](https://www.mrosupply.com/hydraulics-and-pneumatics/6430742_sy5220-5dz-01_smc/) | $17 تا 30 |
| Speed controller meter-out | SMC AS2201F | 2 | $11 تا 15 | $22 تا 30 | [Automation Distribution](https://automationdistribution.com/as2201f-01-06s/) | $3 تا 5 |
| Hydraulic shock absorber | SMC RB1412 | 2 | $29 تا 43 | $58 تا 86 | [Mechatalk / MISUMI](https://us.misumi-ec.com/vona2/detail/221006500174/?HissuCode=RB1412) | $9 تا 17 |
| Reed/solid-state switch | SMC D-M9N | 3 | $29 تا 36 | $87 تا 108 | [Automation Distribution / MROSupply](https://automationdistribution.com/d-m9n/) | $6 تا 13 |
| FRL + pressure switch | SMC AC20 + ISE20 | 1 | $110 تا 130 | $110 تا 130 | [AW20 ($42.65) + ISE20 ($67–87)](https://automationdistribution.com/smc-aw20-02bg/) | $17 تا 35 |
| Pilot check valve (recommended) | SMC XT34 / AS-R | 1 | $42 | $42 | [SMC ASP430F (Automation Distribution)](https://automationdistribution.com/asp430f-02-08s/) | $9 تا 17 |
| Fittings + PU tube | - | 1 | $20 تا 40 | $20 تا 40 | *–* (برآورد) | $6 تا 13 |
| Inductive NPN M18 | Autonics PR18-8DN | 2 | $26 تا 28 | $52 تا 56 | [Wolf Automation / QF Automation](https://www.wolfautomation.com/sensor-inductive-proximity-o18mm-8mm-range-24707) | $7 تا 14 |
| Over-travel limit switch | Omron/Autonics | 4 | $26 تا 44 | $104 تا 176 | [Omron D4N (Hartfiel / MISUMI)](https://shop.hartfiel.com/products/D4N-1A31) | $2 تا 6 |
| Safety relay | Pilz PNOZ s4 + s7.1 | 1 | $348 تا 604 | $348 تا 604 | [PNOZ s4 ($133–364) + s7.1 ($215–240)](https://shop.powermation.com/products/PILZ-750104) | $87 تا 195 |
| E-stop 2NC | Schneider XB5AS8442 | 2 | $24 تا 29 | $48 تا 58 | [TME / Kempston / Tameson](https://www.tme.com/us/en-us/details/xb5as8442/panel-mount-switches-standard-22mm/schneider-electric/) | $4 تا 11 |
| Light curtain type 4 | Chinese brand (Sick/Omron 60-150) | 1 | $492 تا 602 | $492 تا 602 | [AutomationDirect (Contrinex / Datasensing)](https://library.automationdirect.com/datasensing-sh4-light-curtain/) | $65 تا 130 |
| DC contactor 48V | KM1 | 1 | $30 تا 80 | $30 تا 80 | *–* (برآورد) | $13 تا 26 |
| Linear rail HGR15 (Y) per m | HIWIN/HQM | 1 | $31 تا 60 | $31 تا 60 | [Motion Constrained (از $30.72)](https://motionconstrained.com/store/hiwin-linear-guides/hiwin-hg-series-linear-guides/hg-rails-only/hiwin-hgr15r-linear-guideway-rail/) | $11 تا 22 |
| Carriage HGH15CA | HIWIN/HQM | 2 | $29 تا 53 | $58 تا 106 | [PicClick / eBay](https://www.ebay.com/itm/184611756265) | $4 تا 23 |
| Timing belt HTD5M 15mm open PU steel (m) | - | 3 | $8 تا 20 | $24 تا 60 | *قیمت در نتایج نبود* (برآورد) | $4 تا 11 |
| Timing pulley 24T HTD5M-15 (drive+idler) | - | 4 | $5 تا 20 | $20 تا 80 | [BEP Ltd (از $4.80)](https://bepltd.com/products/24-5m-15-htd-pilot-bore-5m-timing-belt-pulley-24-tooth-x-15mm-wide) | $2 تا 6 |
| Enclosure 60x80 + mounting plate | - | 1 | $80 تا 200 | $80 تا 200 | *–* (برآورد) | $35 تا 65 |
| MCB/fuse/terminal/relay/duct/EMI filter | - | 1 | $200 تا 450 | $200 تا 450 | *–* (برآورد) | $87 تا 173 |
| Shielded cables + drag chain + EMC glands | - | 1 | $100 تا 250 | $100 تا 250 | *–* (برآورد) | $43 تا 87 |
| Tower lamp + pedal + push buttons | - | 1 | $50 تا 120 | $50 تا 120 | *–* (برآورد) | $22 تا 39 |
| **جمع کل** | | | | **$3,039 تا $4,861** | | **$1,026 تا $1,796** |

## اثر پیشنهادهای بخش ۱ روی هزینه

| تغییر پیشنهادی | اثر تقریبی (میلیون تومان) |
|---|---:|
| جک MGPM50 به‌جای MGPM25 | **15+ تا 25+** (قیمت جهانی MGPM50-100: [$378 تا $436](https://us.misumi-ec.com/vona2/detail/221006298493/?HissuCode=MGPM50-100Z)) |
| گیربکس ۱:۳ روی X | 7+ تا 12+ (در جدول بالا حساب شده) |
| پاور 36V به‌جای 48V | تقریباً بی‌اثر |
| شیر تک‌بوبین به‌جای دوبوبین | 0 تا 1− |
| پرده‌ی نوری و رله‌ی ایمنی | ۳۵ تا ۷۵ (در جدول حساب شده، **حذف نشود**) |

## راه‌های کاهش هزینه (بدون قربانی کردن ایمنی)

1. **پنوماتیک:** SMC اصل فقط برای جک Z و سنسورهای D-M9N. برای شیر، فلوکنترل و FRL از **Airtac** استفاده کنید. حدود ۱۰ تا ۱۵ میلیون صرفه‌جویی.
2. **ریل و واگن:** برای محور Y، برند **HQM یا چینی درجه‌یک** کافی است، چون بار کم است. HIWIN را برای محور X نگه دارید.
3. **درایور و موتور:** مجموعه‌ی کلوزلوپ **Rtelligent** یا **Leadshine نسخه‌ی اقتصادی** (مثل CS-D508 به همراه موتور مربوط) معمولاً ۳۰ تا ۴۰٪ ارزان‌تر است. فقط تطابق ورودی پالس ۲۴ ولت و خروجی ALM را چک کنید.
4. **رله‌ی ایمنی:** به‌جای ترکیب PNOZ s4 و s7.1، یک رله‌ی ایمنی با **خروجی تأخیری داخلی** (مثل PNOZ X2.8P یا معادل Omron G9SE) انتخاب کنید.
5. **از خرید PLC و HMI با قیمت بالای بازه خودداری کنید.** اختلاف فروشنده‌ها در ترب برای همین مدل تا دو برابر است. کالای **نو با گارانتی نمایندگی** را با کالای استوک یا کارکرده مقایسه نکنید.

## منابع جستجو

* [ترب: PLC دلتا DVP28SV11T2](https://torob.com/p/b2c942d9-1ee2-4880-8eed-1a58b3dac1ea/plc-%D8%AF%D9%84%D8%AA%D8%A7-%D9%85%D8%AF%D9%84-dvp28sv11t2/)
* [ترب: درایور کلوزلوپ HBS57](https://torob.com/p/41aff8d5-269a-4f77-beca-6a30a560e92d/)
* [ترب: منبع تغذیه‌ی 48V/10A](https://torob.com/p/c3d43b1a-18f7-4af6-9045-be6917785a17/)
* [emalls: MeanWell LRS-150-24](https://emalls.ir/%D9%85%D8%B4%D8%AE%D8%B5%D8%A7%D8%AA_%D9%85%D9%86%D8%A8%D8%B9-%D8%AA%D8%BA%D8%B0%DB%8C%D9%87-%D8%B3%D9%88%D8%A6%DB%8C%DA%86%DB%8C%D9%86%DA%AF-24-%D9%88%D9%84%D8%AA-6-5-%D8%A2%D9%85%D9%BE%D8%B1-%D9%85%D8%AF%D9%84-LRS-150-24-%D8%A8%D8%B1%D9%86%D8%AF-%D9%85%DB%8C%D9%86%D9%88%D9%84-(MEAN-WELL)~id~4165346)
* [ترب: واگن HGH15CA هایوین](https://torob.com/p/c16d2cb1-a908-4995-86b9-72f34a093e34/)
* [cncyadak: ریل HGR15 مدل HQM](https://cncyadak.com/product/%D8%B1%DB%8C%D9%84-%D8%B9%D8%B1%D8%B6-15-%D9%85%DB%8C%D9%84%DB%8C%D9%85%D8%AA%D8%B1-%D9%85%D8%AF%D9%84-hgr15-%D8%A8%D8%B1%D9%86%D8%AF-%D8%A7%DA%86-%DA%A9%DB%8C%D9%88-%D8%A7%D9%85-hqm-%D8%B3%D8%A7/)
* [دیجی‌کالا: سنسور Autonics PRL18-8DN](https://www.digikala.com/product/dkp-4277126/)
* [پارتینه: گیربکس خورشیدی](https://partineh.com/category/planetary-gearbox)
* [نرخ دلار آزاد، ۳۰ شهریور ۱۴۰۵ (اقتصادنیوز)](https://www.eghtesadnews.com/%D8%A8%D8%AE%D8%B4-%D8%A7%D8%AE%D8%A8%D8%A7%D8%B1-%D8%B7%D9%84%D8%A7-%D8%A7%D8%B1%D8%B2-40/808013-%D9%82%DB%8C%D9%85%D8%AA-%D8%AF%D9%84%D8%A7%D8%B1-%D8%A2%D8%B2%D8%A7%D8%AF-%D9%87%D8%B2%D8%A7%D8%B1-%D8%AA%D9%88%D9%85%D8%A7%D9%86-%D8%B4%D8%AF)
* [مرکز برق: جک SMC MGPM](https://www.markazbargh.com/product/smc-three-shaft-pneumatic-mgpm/)
