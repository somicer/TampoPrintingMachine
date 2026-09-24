// =====================================================================
//  Large-Format Closed-Cup Pad Printer  -  Delta DVP-28SV211T (SV2)
//  Instruction List (WPLSoft / ISPSoft IL mnemonic)
// ---------------------------------------------------------------------
//  Rev   : 1.0
//  Axes  : X = pad carriage   (Y0 PUL / Y1 DIR, home DOG X0)
//          Y = closed ink cup (Y2 PUL / Y3 DIR, home DOG X1)
//          Z = pneumatic pad lift (Y4 SOL-DOWN / Y5 SOL-UP, X2 UP / X3 DOWN)
//  Units : positions 0.1 mm (32-bit), speeds mm/s, times 10 ms
//
//  NOTE  : Lines starting with "//" are comments for the reader. WPLSoft
//          IL mode does not accept them - enter each network as ladder
//          (or strip comments) and put the comments in the device
//          comment table. Special device numbers (D1030, D1336, M1029,
//          M1030, M1078, M1104, M1336, M1337, D1343, D1353, D1340,
//          D1352) are taken from the DVP-ES2/EX2/SS2/SA2/SX2/SE/SV2
//          programming manual - VERIFY them against the manual revision
//          matching your PLC firmware before commissioning.
//
//  Program structure (order matters - see docs/04_plc_program.md):
//    N00  Init / default parameters
//    N01  Parameter clamping & validation
//    N02  Alarm reset, alarm detection, alarm reaction
//    N03  Position calculation & position/zone flags
//    N04  Interlocks (permits)
//    N05  Mode, start / stop, homing request
//    N06  Homing master sequence (D2) + axis sub-sequences (D3, D4)
//    N07  Auto sequence (D0)
//    N08  Ink (closed-cup) sub-sequence (D1)
//    N09  Manual: jog, go-to, Z
//    N10  Motion execution block (MUST stay after all sequences)
//    N11  Z valve outputs
//    N12  Counters, cycle time, lamps, HMI command clearing
// =====================================================================


// =====================================================================
// N00  INIT
// =====================================================================
// Start/end frequency of pulse channels (Hz)
LD      M1002
MOV     K200        D1340           // CH0 (Y0) start/end freq
MOV     K200        D1352           // CH1 (Y2) start/end freq
SET     M505                        // HMI watchdog enabled by default

// Load default parameters on a blank PLC (scale = 0)
DLD=    D518        K0
DMOV    K33333      D518            // X pulses per 1000 mm (4000 p/rev, 24T HTD5M)
DMOV    K33333      D520            // Y pulses per 1000 mm
DMOV    K1500       D500            // X pick-up pos   150.0 mm
DMOV    K6000       D502            // X print pos     600.0 mm
DMOV    K1500       D504            // X ready pos     = pick-up
DMOV    K6950       D506            // X soft max      695.0 mm
DMOV    K500        D508            // X cliche zone min  50.0 mm
DMOV    K2600       D510            // X cliche zone max 260.0 mm
DMOV    K50         D512            // Y park pos        5.0 mm
DMOV    K3500       D514            // Y end pos       350.0 mm
DMOV    K3950       D516            // Y soft max      395.0 mm
MOV     K600        D522            // X auto speed    mm/s
MOV     K100        D523            // X jog / manual  mm/s
MOV     K80         D524            // X home speed    mm/s
MOV     K10         D525            // X creep speed   mm/s
MOV     K400        D526            // X accel/decel   ms
MOV     K350        D527            // Y out speed     mm/s
MOV     K350        D528            // Y return speed  mm/s
MOV     K80         D529            // Y jog           mm/s
MOV     K60         D530            // Y home          mm/s
MOV     K8          D531            // Y creep         mm/s
MOV     K400        D532            // Y accel/decel   ms
MOV     K40         D540            // Dwell-1 pick    0.40 s
MOV     K50         D541            // Dwell-2 print   0.50 s
MOV     K0          D542            // Flash-off delay 0.00 s
MOV     K150        D543            // Z down timeout  1.50 s
MOV     K150        D544            // Z up timeout    1.50 s
MOV     K10         D545            // Z settle after UP 0.10 s
MOV     K50         D546            // Auto-repeat pause 0.50 s
MOV     K300        D547            // Homing timeout 30.0 s (100 ms units)
DMOV    K5          D548            // In-position tolerance 0.5 mm
DMOV    K0          D564            // Batch target (0 = off)


// =====================================================================
// N01  PARAMETER CLAMPING & VALIDATION
// =====================================================================
LD<     D540        K20
MOV     K20         D540
LD>     D540        K60
MOV     K60         D540
LD<     D541        K30
MOV     K30         D541
LD>     D541        K80
MOV     K80         D541
LD>     D522        K800            // X speed hard cap 800 mm/s
MOV     K800        D522
LD>     D527        K600            // Y speed hard cap 600 mm/s
MOV     K600        D527
LD>     D528        K600
MOV     K600        D528
LD<     D526        K100            // accel min 100 ms
MOV     K100        D526
LD<     D532        K100
MOV     K100        D532

// A15 - parameter invalid (positions outside soft limits / bad scale)
DLD>    D500        D506
DOR>    D502        D506
DOR>    D504        D506
DOR>    D508        D510
DOR>    D514        D516
DOR>=   D512        D514
DOR<=   D518        K0
DOR<=   D520        K0
SET     M214


// =====================================================================
// N02  ALARMS
// =====================================================================
// --- Reset (panel X14 or HMI M102) --------------------------------
LDP     X14
ORP     M102
SET     M36                         // ENA pulse -> clears CL57 alarm
ZRST    M200        M215
RST     M95

LD      M36
TMR     T7          K3              // ENA off for 300 ms
LD      T7
RST     M36

// --- Alarm detection (latched) ------------------------------------
LDI     X10
SET     M200                        // A01 E-STOP
LDI     X4
ANI     M36
SET     M201                        // A02 X drive alarm
LDI     X5
ANI     M36
SET     M202                        // A03 Y drive alarm
LDI     X6
SET     M203                        // A04 X over-travel
LDI     X7
SET     M204                        // A05 Y over-travel
LDI     X15
TMR     T2          K5              // 0.5 s debounce
LD      T2
SET     M205                        // A06 low air pressure

// A07 Z down timeout
LD      Y4
ANI     M62
TMR     T203        D543
LD      T203
SET     M206
// A08 Z up timeout (only with E-stop OK and air OK)
LDI     Y4
ANI     X2
AND     X10
AND     X15
TMR     T204        D544
LD      T204
SET     M207
// A09 Z sensor plausibility (UP and DOWN at the same time)
LD      X2
AND     X3
LD      X2
AND     X17
ORB
TMR     T6          K3
LD      T6
SET     M208
// A10 Z left UP position while an axis is moving over the cliche
LD      M1336
ANI     X2
LD      M1337
ANI     X2
AND     M30
ORB
SET     M209
// A11 / A12 homing timeout
LD>     D3          K0
TMR     T0          D547
LD      T0
SET     M210
LD>     D4          K0
TMR     T1          D547
LD      T1
SET     M211
// A13 guard / light curtain opened during hazardous motion
LDI     X16
LD      Y4
OR      M1336
OR      M1337
ANB
SET     M212
// A14 HMI heartbeat lost (HMI cycle macro increments D60 every 0.5 s)
LD<>    D60         D61
OUT     M37
MOV     D60         D61
LDI     M37
AND     M505
TMR     T3          K20             // 2.0 s without heartbeat
LD      T3
SET     M213
ZRST    M100        M119            // drop every HMI command / jog bit
// A16 sequence step timeout (auto)
LD      M90
AND<>   D0          K10
AND=    D0          D98
TMR     T8          K150            // 15 s in one step
LD      T8
SET     M215
LD      M1000
MOV     D0          D98

// --- Alarm words for HMI ------------------------------------------
LD      M1000
MOV     K4M200      D50
LD<>    D50         K0
OUT     M21                         // any alarm

// --- Stop classes -------------------------------------------------
// M28 : position may be lost -> immediate stop + unhome
LD      M200
OR      M201
OR      M202
OR      M203
OR      M204
OR      M209
OUT     M28
// M29 : immediate pulse stop
LD      M28
OR      M212
OR      M213
OUT     M29

LD      M28
RST     M22
RST     M23

LD      M29
SET     M1078                       // CH0 pulse pause (immediate)
SET     M1104                       // CH1 pulse pause (immediate)
RST     M46
RST     M48
LDI     M29
ANI     M50
ANI     M52
ANI     M54
ANI     M55
RST     M1078
RST     M1104

// --- Any alarm: abort all sequences, pad up, drop move requests --
LD      M21
RST     M90
RST     M91
RST     M92
RST     M60
RST     M61
RST     M45
RST     M47
RST     M54
RST     M55
ZRST    D0          D4

// --- Safe-to-run summary ------------------------------------------
LD      X10
AND     X15
AND     X4
AND     X5
AND     X6
AND     X7
ANI     M21
OUT     M20


// =====================================================================
// N03  POSITIONS (0.1 mm) AND POSITION FLAGS
// =====================================================================
DLD>    D518        K0
DMUL    D1030       K10000      D40
DDIV    D40         D518        D30     // D30/D31 = X position 0.1 mm
DLD>    D520        K0
DMUL    D1336       K10000      D40
DDIV    D40         D520        D34     // D34/D35 = Y position 0.1 mm

LD      M1000
DSUB    D500        D548        D70     // pick  lo
DADD    D500        D548        D72     // pick  hi
DZCP    D70         D72         D30     M70     // M71 = X at pick
DSUB    D502        D548        D74
DADD    D502        D548        D76
DZCP    D74         D76         D30     M73     // M74 = X at print
DSUB    D504        D548        D78
DADD    D504        D548        D80
DZCP    D78         D80         D30     M76     // M77 = X at ready
DZCP    D508        D510        D30     M79     // M80 = X in cliche zone
DSUB    D512        D548        D82
DADD    D512        D548        D84
DZCP    D82         D84         D34     M82     // M83 = Y at park
DSUB    D514        D548        D86
DADD    D514        D548        D88
DZCP    D86         D88         D34     M85     // M86 = Y at end

LD      M22
AND     M23
OUT     M24                         // all axes homed
LD      M71
ANI     M1336
AND     M22
OUT     M31                         // X AT PICK (stopped)
LD      M74
ANI     M1336
AND     M22
OUT     M32                         // X AT PRINT (stopped)
LD      M77
ANI     M1336
AND     M22
OUT     M34                         // X AT READY (stopped)
LD      M80
ORI     M22                         // not homed -> assume inside zone
OUT     M30                         // X IN CLICHE ZONE
LD      M83
ANI     M1337
AND     M23
OUT     M33                         // Y AT PARK (stopped)
LD      M86
ANI     M1337
AND     M23
OUT     M35                         // Y AT END (stopped)


// =====================================================================
// N04  INTERLOCKS
// =====================================================================
// Z confirmed UP: UP sensor, no DOWN sensor, no DOWN command, settled
LD      X2
ANI     X3
ANI     X17
ANI     Y4
TMR     T205        D545
LD      T205
OUT     M25

// Z confirmed DOWN (pad compressed)
LD      X3
LD      X17
AND     M501
ORB
OUT     M62

// X may move only with Z up
LD      M25
AND     M20
OUT     M40
// Y may move if Z up OR pad is outside the cliche zone
LD      M25
ORI     M30
AND     M20
OUT     M42
// Z may go down only: (X at pick AND cup parked) OR X at print
LD      M31
AND     M33
OR      M32
AND     M24
AND     M20
ANI     M1336
OUT     M41
LDI     M41
RST     M60                         // permit lost -> never re-descend later
RST     M61


// =====================================================================
// N05  MODE, START / STOP, HOMING REQUEST
// =====================================================================
// Auto start (panel X12 or HMI M100)
LD      X12
OR      M100
AND     M120                        // auto mode selected
AND     M24
AND     M20
AND     X16
ANI     M90
AND=    D2          K0
SET     M90
RST     M91
RST     M95
MOV     K5          D0

// Stop at end of cycle (NC stop PB, HMI stop, or leaving auto mode)
LDI     X13
OR      M101
ORI     M120
AND     M90
SET     M91

// Homing request (HMI M103) - not while running
LD      M103
ANI     M90
AND=    D2          K0
AND     M20
MOV     K10         D2

// Manual enable
LDI     M120
ANI     M90
AND=    D2          K0
AND=    D1          K0
AND     M20
OUT     M38


// =====================================================================
// N06  HOMING
// =====================================================================
// H10 : drop Z commands, forget home, wait Z up
LD=     D2          K10
RST     M60
RST     M61
RST     M22
RST     M23
LD=     D2          K10
AND     M25
MOV     K20         D2
// H20 : start both axis sub-sequences (parallel)
LD=     D2          K20
MOV     K10         D3
MOV     K10         D4
MOV     K30         D2
// H30 : wait both homed
LD=     D2          K30
AND=    D3          K0
AND=    D4          K0
AND     M24
MOV     K40         D2
// H40 : X -> ready, Y -> park
LD=     D2          K40
ANI     M34
ANI     M45
AND     M58
AND     M40
DMOV    D504        D200
MOV     D523        D202
SET     M45
LD=     D2          K40
ANI     M33
ANI     M47
AND     M59
AND     M42
DMOV    D512        D204
MOV     D529        D206
SET     M47
LD=     D2          K40
AND     M34
AND     M33
MOV     K0          D2

// ---- X axis homing sub-sequence (D3) -----------------------------
// X10 : if already on the DOG, back off +30 mm at creep speed first
LD=     D3          K10
AND     M58
AND     M40
MPS
AND     X0
DMOV    K0          D1030
DMOV    K300        D200
MOV     D525        D202
SET     M45
MOV     K15         D3
MPP
ANI     X0
MOV     K20         D3
// X15 : wait back-off done
LD=     D3          K15
ANI     M45
AND     M58
MOV     K20         D3
// X20 : DOG still active after back-off -> sensor stuck
LD=     D3          K20
AND     M58
AND     X0
SET     M210
// X20 : start DZRN
LD=     D3          K20
AND     M58
ANI     X0
SET     M54
MOV     K25         D3
// X25 : DZRN done
LD=     D3          K25
AND     M57
RST     M57
DMOV    K0          D1030
SET     M22
MOV     K0          D3

// ---- Y axis homing sub-sequence (D4) -----------------------------
LD=     D4          K10
AND     M59
AND     M40
MPS
AND     X1
DMOV    K0          D1336
DMOV    K300        D204
MOV     D531        D206
SET     M47
MOV     K15         D4
MPP
ANI     X1
MOV     K20         D4
LD=     D4          K15
ANI     M47
AND     M59
MOV     K20         D4
LD=     D4          K20
AND     M59
AND     X1
SET     M211
LD=     D4          K20
AND     M59
ANI     X1
SET     M55
MOV     K25         D4
LD=     D4          K25
AND     M56
RST     M56
DMOV    K0          D1336
SET     M23
MOV     K0          D4


// =====================================================================
// N07  AUTO SEQUENCE (D0)
// =====================================================================
// S5  : go to start position (X ready, Y park)
LD=     D0          K5
ANI     M34
ANI     M45
AND     M58
AND     M40
DMOV    D504        D200
MOV     D522        D202
SET     M45
LD=     D0          K5
ANI     M33
ANI     M47
AND     M59
AND     M42
DMOV    D512        D204
MOV     D528        D206
SET     M47
LD=     D0          K5
AND     M34
AND     M33
MOV     K10         D0

// S10 : wait pedal (or auto-repeat pause); stop request ends auto here
LD=     D0          K10
AND     M91
RST     M90
RST     M91
MOV     K0          D0
LD=     D0          K10
AND     M502
TMR     T206        D546
LD=     D0          K10
ANI     M91
AND     X16
AND     M20
LDP     X11
OR      T206
ANB
MOV     K20         D0

// S20 : X -> pick (if not there) + ink stroke (if image not inked)
LD=     D0          K20
ANI     M31
ANI     M45
AND     M58
AND     M40
DMOV    D500        D200
MOV     D522        D202
SET     M45
LD=     D0          K20
ANI     M92
AND=    D1          K0
MOV     K10         D1
LD=     D0          K20
AND     M31
AND     M92
MOV     K40         D0

// S40 : flash-off delay (ink tack build-up)
LD=     D0          K40
TMR     T202        D542
LD=     D0          K40
AND     T202
MOV     K50         D0

// S50 : Z down on cliche (skipped in dry-run)
LD=     D0          K50
ANI     M503
AND     M41
SET     M60
LD=     D0          K50
LD      M62
OR      M503
ANB
MOV     K60         D0

// S60 : dwell-1 (timed from Z-DOWN confirmation), then Z up
LD=     D0          K60
TMR     T200        D540
LD=     D0          K60
AND     T200
RST     M60
RST     M92                         // image consumed
MOV     K70         D0

// S70 : wait Z up; overlap option re-inks while pad travels
LD=     D0          K70
AND     M25
AND     M500
AND=    D1          K0
MOV     K10         D1
LD=     D0          K70
AND     M25
MOV     K80         D0

// S80 : X -> print
LD=     D0          K80
ANI     M32
ANI     M45
AND     M58
AND     M40
DMOV    D502        D200
MOV     D522        D202
SET     M45
LD=     D0          K80
AND     M32
MOV     K90         D0

// S90 : Z down on part
LD=     D0          K90
ANI     M503
AND     M41
SET     M60
LD=     D0          K90
LD      M62
OR      M503
ANB
MOV     K100        D0

// S100 : dwell-2, then Z up
LD=     D0          K100
TMR     T201        D541
LD=     D0          K100
AND     T201
RST     M60
MOV     K110        D0

// S110 : wait Z up
LD=     D0          K110
AND     M25
MOV     K120        D0

// S120 : X -> ready
LD=     D0          K120
ANI     M34
ANI     M45
AND     M58
AND     M40
DMOV    D504        D200
MOV     D522        D202
SET     M45
LD=     D0          K120
AND     M34
MOV     K130        D0

// S130 : cycle complete - counters, cycle time
LD=     D0          K130
DINC    D560
DINC    D562
MOV     T210        D566
MOV     K0          D567
DDIV    K360000     D566        D570
MOV     D570        D568
MOV     K10         D0

// Batch complete -> stop at end of cycle
LD      M504
DAND>=  D562        D564
DAND>   D564        K0
SET     M95
SET     M91

// Cycle timer (10 ms base)
LD      M90
AND>=   D0          K20
TMR     T210        K32767


// =====================================================================
// N08  INK SUB-SEQUENCE (D1): cup out over the etch, then back to park
// =====================================================================
LD=     D1          K10
ANI     M35
ANI     M47
AND     M59
AND     M42
DMOV    D514        D204
MOV     D527        D206
SET     M47
LD=     D1          K10
AND     M35
MOV     K20         D1
LD=     D1          K20
ANI     M33
ANI     M47
AND     M59
AND     M42
DMOV    D512        D204
MOV     D528        D206
SET     M47
LD=     D1          K20
AND     M33
SET     M92                         // image inked & doctored
MOV     K0          D1


// =====================================================================
// N09  MANUAL
// =====================================================================
// ---- X jog + / - (hold-to-run, HMI momentary M104 / M105) --------
LDP     M104
AND     M38
AND     M58
AND     M40
AND     M22
DMOV    D506        D200            // homed: jog up to soft max
MOV     D523        D202
SET     M46
LDP     M104
AND     M38
AND     M58
AND     M40
ANI     M22
DADD    D30         K500        D200    // not homed: max 50 mm per press
MOV     D525        D202                // at creep speed
SET     M46
LDP     M105
AND     M38
AND     M58
AND     M40
AND     M22
DMOV    K0          D200
MOV     D523        D202
SET     M46
LDP     M105
AND     M38
AND     M58
AND     M40
ANI     M22
DSUB    D30         K500        D200
MOV     D525        D202
SET     M46
LDI     M104
ANI     M105
ORI     M38
RST     M46

// ---- Y jog + / - (M106 / M107) -----------------------------------
LDP     M106
AND     M38
AND     M59
AND     M42
AND     M23
DMOV    D516        D204
MOV     D529        D206
SET     M48
LDP     M106
AND     M38
AND     M59
AND     M42
ANI     M23
DADD    D34         K500        D204
MOV     D531        D206
SET     M48
LDP     M107
AND     M38
AND     M59
AND     M42
AND     M23
DMOV    K0          D204
MOV     D529        D206
SET     M48
LDP     M107
AND     M38
AND     M59
AND     M42
ANI     M23
DSUB    D34         K500        D204
MOV     D531        D206
SET     M48
LDI     M106
ANI     M107
ORI     M38
RST     M48

// ---- Go-to buttons (manual speed) --------------------------------
LD      M110                        // X -> pick
AND     M38
AND     M24
AND     M58
AND     M40
ANI     M45
DMOV    D500        D200
MOV     D523        D202
SET     M45
LD      M111                        // X -> print
AND     M38
AND     M24
AND     M58
AND     M40
ANI     M45
DMOV    D502        D200
MOV     D523        D202
SET     M45
LD      M112                        // Y -> park
AND     M38
AND     M24
AND     M59
AND     M42
ANI     M47
DMOV    D512        D204
MOV     D529        D206
SET     M47
LD      M113                        // Y -> end
AND     M38
AND     M24
AND     M59
AND     M42
ANI     M47
DMOV    D514        D204
MOV     D529        D206
SET     M47
LD      M117                        // Y test ink stroke (out + back)
AND     M38
AND     M24
AND=    D1          K0
MOV     K10         D1

// ---- Manual Z -----------------------------------------------------
LD      M108
AND     M38
AND     M41
SET     M61
LD      M109
ORI     M38
RST     M61


// =====================================================================
// N10  MOTION EXECUTION  (keep AFTER all sequence logic)
// =====================================================================
LD      M45
OR      M46
OUT     M50                         // X DDRVA active request
LD      M47
OR      M48
OUT     M52                         // Y DDRVA active request

// ---- X scaling: target pulses & frequencies ----------------------
LD      M1000
DMUL    D200        D518        D40
DDIV    D40         K10000      D44
DMOV    D44         D10             // X target (pulses)
MOV     D202        D48
MOV     K0          D49
DMUL    D48         D518        D40
DDIV    D40         K1000       D44
DMOV    D44         D12             // X frequency (Hz)
MOV     D524        D48
DMUL    D48         D518        D40
DDIV    D40         K1000       D44
DMOV    D44         D18             // X home speed (Hz)
MOV     D525        D48
DMUL    D48         D518        D40
DDIV    D40         K1000       D44
DMOV    D44         D20             // X creep speed (Hz)
MOV     D526        D1343           // X accel/decel time

// ---- Y scaling ---------------------------------------------------
DMUL    D204        D520        D40
DDIV    D40         K10000      D44
DMOV    D44         D14
MOV     D206        D48
DMUL    D48         D520        D40
DDIV    D40         K1000       D44
DMOV    D44         D16
MOV     D530        D48
DMUL    D48         D520        D40
DDIV    D40         K1000       D44
DMOV    D44         D22
MOV     D531        D48
DMUL    D48         D520        D40
DDIV    D40         K1000       D44
DMOV    D44         D24
MOV     D532        D1353           // Y accel/decel time

// ---- X channel (Y0/Y1): one DDRVA + one DZRN, mutually exclusive --
LD      M50
AND     M40
ANI     M54
ANI     M29
DDRVA   D10         D12         Y0      Y1
LD      M54
AND     M40
ANI     M50
ANI     M29
DZRN    D18         D20         X0      Y0
LDI     M50
ANI     M54
ANI     M1336
OUT     M58                         // X channel idle for >= 1 scan
LD      M1029
MPS
AND     M54
RST     M54
SET     M57                         // X home done
MRD
AND     M50
RST     M45
MPP
RST     M1029

// ---- Y channel (Y2/Y3) -------------------------------------------
LD      M52
AND     M42
ANI     M55
ANI     M29
DDRVA   D14         D16         Y2      Y3
LD      M55
AND     M40
ANI     M52
ANI     M29
DZRN    D22         D24         X1      Y2
LDI     M52
ANI     M55
ANI     M1337
OUT     M59
LD      M1030
MPS
AND     M55
RST     M55
SET     M56                         // Y home done
MRD
AND     M52
RST     M47
MPP
RST     M1030


// =====================================================================
// N11  Z VALVE (bistable 5/2) - coils mutually exclusive, held
//      Y4 coil is ALSO powered through the safety relay (hardware).
// =====================================================================
LD      M60
OR      M61
AND     M41
OUT     Y4                          // SOL-A : pad DOWN
LDI     Y4
OUT     Y5                          // SOL-B : pad UP


// =====================================================================
// N12  DRIVE ENABLE, LAMPS, AIR, HMI STATUS, COMMAND CLEAR
// =====================================================================
LD      X10
ANI     M36
OUT     Y6                          // X drive enable (via relay KA6)
OUT     Y7                          // Y drive enable (via relay KA7)

LD      M90
LD      M24
ANI     M90
AND     M1013                       // 1 s blink = ready
ORB
ANI     M21
OUT     Y10                         // green
LDI     M24
OR      M95
ORI     M120
ANI     M21
OUT     Y11                         // amber
LD      M21
OUT     Y12                         // red + buzzer
LDI     M119
OUT     Y13                         // main air soft-start valve

// Machine state for HMI (D9): 0 not homed,1 homing,2 ready,3 auto,4 stopping,5 alarm
LD      M1000
MOV     K0          D9
LD      M24
MOV     K2          D9
LD>     D2          K0
MOV     K1          D9
LD      M90
MOV     K3          D9
LD      M91
MOV     K4          D9
LD      M21
MOV     K5          D9

// Counter resets (password-protected on HMI)
LD      M115
DMOV    K0          D560
LD      M116
DMOV    K0          D562
RST     M95

// Clear one-shot HMI command bits (NOT the momentary jog bits M104-M107)
LD      M1000
RST     M100
RST     M101
RST     M102
RST     M103
RST     M108
RST     M109
RST     M110
RST     M111
RST     M112
RST     M113
RST     M115
RST     M116
RST     M117

END
