# ۱۱. گزارش تست نقطه‌به‌نقطه‌ی برنامه‌ی PLC

> این فایل را `python3 tools/test_suite.py` خودکار می‌سازد. هر سناریو برنامه‌ی واقعی `plc/TampoPrinter_SV2.il` را اسکن‌به‌اسکن (هر ۵ ms) روی مدل دستگاه اجرا می‌کند، خطا تزریق می‌کند و نتیجه را بررسی می‌کند. در هر اسکن، مدل دستگاه قانون‌های ایمنی را هم کنترل می‌کند: حرکت X با پد پایین، پد روی سطح حین حرکت، و حرکت کاپ زیر پد.

## خلاصه

| مورد | نتیجه |
|---|---|
| سناریوها | **54 از 54** قبول |
| بررسی‌ها | **276 از 276** قبول |
| دستورهای خروجی اجراشده (پوشش کد) | **619 از 626** (99٪) |
| مرحله‌های اتومات دیده‌شده | S0, S5, S10, S20, S50, S60, S70, S80, S90, S100, S110 (S5، S40 و S120 در همان اسکن تمام می‌شوند و با پوشش کد تأیید می‌شوند) |
| مرحله‌های جوهرزنی / هومینگ | D1: [0, 10, 20] · D2: [0, 10, 30, 40] · D3: [0, 15, 20, 25] |
| آلارم‌های آزموده‌شده | A01, A02, A03, A04, A05, A06, A07, A08, A09, A10, A11, A12, A13, A14, A15, A16, A17, A18, A19, A20, A21 (21 از 21) |

## سناریوها

### ✅ S01: Auto cycle, serial inking, 1 pedal = 1 print

- ✅ homing
- ✅ auto started
- ✅ 3 prints
- ✅ no alarm, no collision
- ✅ every held auto step visited

### ✅ S02: Auto cycle, parallel inking

- ✅ homing
- ✅ 3 prints
- ✅ ink sub-sequence visited
- ✅ no alarm, no collision

### ✅ S03: Early Z descent 5 mm

- ✅ homing
- ✅ 3 prints
- ✅ no alarm, no collision

### ✅ S04: Pre-pick + early Z + parallel inking

- ✅ homing
- ✅ 3 prints
- ✅ pad loaded and waiting for pedal
- ✅ pad re-picks after max wait (D552)
- ✅ no alarm, no collision

### ✅ S05: Mode 1: one pedal = N prints

- ✅ homing
- ✅ 6 prints
- ✅ 2 pedals for 6 prints
- ✅ no alarm, no collision

### ✅ S06: Mode 2: continuous

- ✅ homing
- ✅ 4 prints without pedal
- ✅ no alarm, no collision

### ✅ S07: Stop at end of cycle

- ✅ homing
- ✅ auto stops by itself
- ✅ stopped at S0, pad up
- ✅ no alarm

### ✅ S08: Batch target reached

- ✅ homing
- ✅ exactly 3 prints then stop
- ✅ batch done flag
- ✅ start refused until batch reset
- ✅ batch reset clears flag

### ✅ S09: Homing starting on the X home sensor (back-off)

- ✅ homing
- ✅ back-off step used
- ✅ no alarm

### ✅ S10: Homing: X sensor stuck ON -> A11

- ✅ A11 raised
- ✅ not homed

### ✅ S11: Homing: X sensor never seen -> A11 by timeout

- ✅ A11 raised by timeout

### ✅ S12: Manual jog X homed (soft limits, hold-to-run)

- ✅ homing
- ✅ jog+ stops at soft max 1010 mm
- ✅ release stops jog-
- ✅ no alarm

### ✅ S13: Manual jog X not homed: max 50 mm per press

- ✅ moved 50 mm at most

### ✅ S14: Manual go-to and Y test stroke

- ✅ homing
- ✅ X at print
- ✅ X at pick
- ✅ Y at end
- ✅ Y at park
- ✅ Y test stroke done, image inked
- ✅ no alarm

### ✅ S15: Manual Z only at pick (cup parked) or print

- ✅ homing
- ✅ Z down at pick
- ✅ Z refused between stations
- ✅ no alarm

### ✅ S16: A01 E-stop during auto

- ✅ homing
- ✅ A01 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ homing lost (class A)
- ✅ re-home
- ✅ production resumes

### ✅ S17: A02 / A03 drive faults

- ✅ homing
- ✅ A02 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ homing lost (class A)
- ✅ re-home
- ✅ production resumes

### ✅ S17b: A03 Y drive fault

- ✅ homing
- ✅ A03 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ homing lost (class A)
- ✅ re-home
- ✅ production resumes

### ✅ S18: A04 X over-travel

- ✅ homing
- ✅ A04 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ homing lost (class A)
- ✅ re-home
- ✅ production resumes

### ✅ S18b: A05 Y over-travel

- ✅ homing
- ✅ A05 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ homing lost (class A)
- ✅ re-home
- ✅ production resumes

### ✅ S19: A06 air pressure low

- ✅ homing
- ✅ A06 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ production resumes

### ✅ S20: A07 Z does not come down

- ✅ homing
- ✅ A07 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ production resumes

### ✅ S21: A08 Z does not go up

- ✅ homing
- ✅ A08 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ production resumes

### ✅ S22: A09 Z sensors UP and DOWN together

- ✅ homing
- ✅ A09 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ re-home after secondary alarm
- ✅ production resumes

### ✅ S23: A10 pad drops while X moves

- ✅ homing
- ✅ X moving
- ✅ A10 raised
- ✅ X stopped at once
- ✅ no further X travel after the fault
- ✅ recovers after reset + homing

### ✅ S24: A13 light curtain during motion

- ✅ homing
- ✅ A13 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ production resumes

### ✅ S25: A14 HMI communication lost

- ✅ homing
- ✅ A14 raised
- ✅ held jog bit cleared
- ✅ X stopped
- ✅ alarm clears when comms return

### ✅ S26: A15 invalid parameter

- ✅ homing
- ✅ A15 raised
- ✅ start refused
- ✅ clears after correction

### ✅ S27: A16 step timeout (cup axis stalls)

- ✅ homing
- ✅ A16 raised
- ✅ auto aborted
- ✅ safe reset recovers

### ✅ S28: A17 pad reported down while X moves

- ✅ homing
- ✅ A17 raised
- ✅ X stopped

### ✅ S29: A18 X path through a forbidden zone

- ✅ homing
- ✅ A18 raised
- ✅ X never entered the zone
- ✅ D680 shows path blocked

### ✅ S30: A18 Y path through a forbidden zone

- ✅ homing
- ✅ A18 raised
- ✅ Y never entered the zone

### ✅ S31: Jog stops before a zone (margin 2 mm)

- ✅ homing
- ✅ stopped at 398 mm
- ✅ cannot jog further
- ✅ no alarm

### ✅ S32: No-drop zone at the print station

- ✅ homing
- ✅ A18 raised at the pad-down step
- ✅ pad never came down in the zone

### ✅ S33: A19 axis already inside a zone, then jog out

- ✅ homing
- ✅ A19 raised
- ✅ reset accepted
- ✅ jogged out of the zone

### ✅ S34: A20 PLC operation error + safe reset

- ✅ homing
- ✅ A20 raised with code/step kept
- ✅ D680 shows PLC error
- ✅ safe reset clears flag and alarm

### ✅ S35: A21 corrupted step register repaired

- ✅ homing
- ✅ A21 raised
- ✅ sequence stopped safely, pad up
- ✅ no collision
- ✅ production resumes

### ✅ S36: Software safe reset during motion

- ✅ homing
- ✅ everything stopped, pad up
- ✅ no alarm, homing kept
- ✅ restart works

### ✅ S37: Restore default parameters

- ✅ print position back to 495.0
- ✅ zones cleared

### ✅ S38: Black box records the first alarm

- ✅ homing
- ✅ one black-box entry
- ✅ entry code = A13
- ✅ entry keeps the step it happened in

### ✅ S39: Diagnostics: why won't it run (D680)

- ✅ not homed shown
- ✅ login missing shown
- ✅ homing
- ✅ not-homed bit clears
- ✅ air low shown

### ✅ S40: Operators, shifts, session log

- ✅ homing
- ✅ start refused without login
- ✅ unknown code rejected
- ✅ 1234 logged in
- ✅ 3 prints
- ✅ 1234 shift count = 3
- ✅ session record for 1234
- ✅ 2 more prints on 5678
- ✅ shift change closes 5678 session
- ✅ shift 2, counters cleared
- ✅ logout
- ✅ no alarm, no collision

### ✅ S41: Power cycle keeps parameters, comes up safe

- ✅ homing
- ✅ not homed, not running
- ✅ pad goes up
- ✅ parameter kept
- ✅ home + print after power-up

### ✅ S42: Random fuzz #1

- ✅ no collision in 160 random actions
- ✅ recovers: safe reset, home, print

### ✅ S43: Random fuzz #2

- ✅ no collision in 160 random actions
- ✅ recovers: safe reset, home, print

### ✅ S44: Random fuzz #3

- ✅ no collision in 160 random actions
- ✅ recovers: safe reset, home, print

### ✅ S45: Out-of-range parameters are clamped

- ✅ D540 5 -> 20
- ✅ D541 5 -> 20
- ✅ D522 2000 -> 900
- ✅ D527 900 -> 600
- ✅ D528 900 -> 600
- ✅ D526 10 -> 100
- ✅ D532 10 -> 100
- ✅ D552 5000 -> 1000
- ✅ D554 5 -> 0
- ✅ D555 0 -> 1
- ✅ D540 500 -> 100
- ✅ D541 500 -> 100
- ✅ D554 -1 -> 0
- ✅ D555 20 -> 9
- ✅ D500 20000 -> 10100
- ✅ D500 -50 -> 0
- ✅ D502 20000 -> 10100
- ✅ D502 -50 -> 0

### ✅ S46: Homing: Y sensor stuck ON -> A12

- ✅ A12 raised

### ✅ S47: Y jog with zones and without homing

- ✅ unhomed Y jog+ max 50 mm
- ✅ unhomed Y jog- max 50 mm
- ✅ homing
- ✅ Y jog+ stops at 198 mm
- ✅ Y jog- stops at 32 mm
- ✅ no alarm

### ✅ S48: X jog- with a zone behind, unhomed X jog-

- ✅ unhomed X jog- max 50 mm
- ✅ homing
- ✅ X jog- stops at 22 mm
- ✅ jog+ away from the zone works

### ✅ S49: Ring buffers wrap: 70 sessions, 18 black-box entries

- ✅ 70 records written
- ✅ session slot wrapped (70 mod 64 = 6)
- ✅ 18 black-box entries
- ✅ black-box slot wrapped (18 mod 16 = 2)

### ✅ S50: Login message timeout, total reset, auto start off-station

- ✅ unknown code message shown
- ✅ message clears after 3 s
- ✅ total counter reset
- ✅ homing
- ✅ start from the print station
- ✅ no alarm

### ✅ S51: Inductive Z sensors: X20 wire break / lost steel flag during auto

- ✅ homing
- ✅ A09 raised
- ✅ auto aborted, motion stopped
- ✅ pad up
- ✅ no collision
- ✅ alarm clears after reset
- ✅ re-home after secondary alarm
- ✅ production resumes

### ✅ S52: Inductive Z sensors: without X20 the X axis stays locked (fail-safe)

- ✅ homing
- ✅ A09 raised (UP without SAFE)
- ✅ X did not move
- ✅ no collision
- ✅ alarm clears after reset
- ✅ X moves again with a healthy sensor

## خط‌های اجرانشده

دستورهای خروجی که در هیچ سناریویی اجرا نشدند (شماره‌ی خط در فایل IL):

```
  214  SET     M211
  933  MOV     K10         D0
 1529  DMOV    D30         D200
 1550  DMOV    D30         D200
 1599  SET     M65
 1623  DMOV    D34         D204
 1644  DMOV    D34         D204
```
