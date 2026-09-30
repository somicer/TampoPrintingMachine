// =====================================================================
//  Large-Format Closed-Cup Pad Printer  -  Delta DVP-28SV11T2 (SV2)
//  Instruction List (WPLSoft / ISPSoft IL mnemonic)
// ---------------------------------------------------------------------
//  Rev   : 2.0  (redesign from field data, docs/08 + docs/09)
//  Axes  : X = pad carriage  - closed-loop NEMA24 4 N.m + gearbox 1:3 +
//              HTD5M 24T pulley  -> 40 mm/motor rev, 4000 p/rev = 100 p/mm
//              (Y0 PUL / Y1 DIR, home DOG X0), stroke 620 mm
//          Y = ink cup       - same motor, direct, 24T 5 mm pitch pulley
//              -> 120 mm/rev = 33.333 p/mm (Y2 PUL / Y3 DIR, DOG X1),
//              stroke 370 mm
//          Z = pneumatic SC63x100 (Y4 SOL-DOWN / Y5 SOL-UP)
//              X2 = UP, X20 = SAFE HEIGHT, X3 = DOWN (X17 = DOWN-2 opt.)
//  Units : positions 0.1 mm (32-bit), speeds mm/s, times 10 ms
//
//  New in Rev 2.0:
//    * Z "above safe height" flag (M26) from the X20 zone sensor
//      (Rev 2.2: inductive M12 over a steel flag whose length is the
//      whole safe zone, so X20 is ON from fully up down to safe height):
//      X may move as soon as the pad is above the safe height (not only
//      fully up)                                   -> motion overlap
//    * Early Z descent when X is within D550 of the pick / print target
//      (option M507). The pad must NOT pass the safe height while X still
//      moves: that trips A10 (immediate stop) - the safety net.
//    * Landing while X still moving -> A17 (immediate stop)
//    * Parallel inking (M500, default ON)
//    * Pre-pick (M506): after each print the pad picks the next image
//      and waits over the cliche; the pedal then only triggers
//      X->print + print. Max wait D552, then the pad re-picks.
//    * Pedal is latched (M94) during the pick phase
//
//  NOTE  : Lines starting with "//" are comments for the reader. WPLSoft
//          IL mode does not accept them - enter each network as ladder
//          (or strip comments) and put the comments in the device
//          comment table. Special device numbers (D1030, D1336, M1029,
//          M1030, M1078, M1104, M1336, M1337, D1343, D1353, D1340,
//          D1352) are taken from the DVP-ES2/EX2/SS2/SA2/SX2/SE/SV2
//          programming manual - VERIFY them against the manual revision
//          matching your PLC firmware before commissioning.
//          X20..X27 / Y20..Y27 = first right-side expansion (DVP16SP11T).
//
//  Program structure (order matters - see docs/04_plc_program.md):
//    N00  Init / default parameters
//    N01  Parameter clamping & validation
//    N02  Alarm reset, alarm detection, alarm reaction
//    N03  Position calculation & position/zone flags
//    N04  Interlocks (permits)
//    N05  Mode, start / stop, pedal latch, homing request
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
LD      M1002
MOV     K200        D1340           // CH0 (Y0) start/end freq (Hz)
MOV     K200        D1352           // CH1 (Y2) start/end freq (Hz)
SET     M505                        // HMI watchdog enabled at power-up

// Load default parameters on a blank PLC (scale = 0), or on the HMI
// "restore defaults" command (M140, only while stopped)
DLD=    D518        K0
CALL    P9
LD      M140
ANI     M90
CALL    P9


// =====================================================================
// N01  PARAMETER CLAMPING & VALIDATION
// =====================================================================
LD<     D540        K20
MOV     K20         D540
LD>     D540        K100
MOV     K100        D540
LD<     D541        K20
MOV     K20         D541
LD>     D541        K100
MOV     K100        D541
LD>     D522        K900            // X speed hard cap 900 mm/s
MOV     K900        D522
LD>     D527        K600            // Y speed hard cap 600 mm/s
MOV     K600        D527
LD>     D528        K600
MOV     K600        D528
LD<     D526        K100            // accel min 100 ms
MOV     K100        D526
LD<     D532        K100
MOV     K100        D532
LD>     D552        K1000           // pre-pick wait max 10 s
MOV     K1000       D552
LD<     D554        K0              // print mode 0..2
MOV     K0          D554
LD>     D554        K2
MOV     K0          D554
LD<     D555        K1              // multi-hit N 1..9
MOV     K1          D555
LD>     D555        K9
MOV     K9          D555

// Pick / print positions are adjusted by operators on the main screen:
// clamp them into 0..soft max instead of raising A15 mid-production.
DLD>    D500        D506
DMOV    D506        D500
DLD<    D500        K0
DMOV    K0          D500
DLD>    D502        D506
DMOV    D506        D502
DLD<    D502        K0
DMOV    K0          D502
// Stall back-off distance: 0 .. 20.0 mm
DLD>    D690        K200
DMOV    K200        D690
DLD<    D690        K0
DMOV    K0          D690
DLD>    D692        K200
DMOV    K200        D692
DLD<    D692        K0
DMOV    K0          D692

// A15 - parameter invalid
DLD>    D504        D506
DOR>    D508        D510
DOR>    D514        D516
DOR>=   D512        D514
DOR<=   D518        K0
DOR<=   D520        K0
DOR<    D550        K0
OR>=    D603        D604            // shift starts (16-bit)
OR>=    D604        D605
SET     M214


// =====================================================================
// N02  ALARMS
// =====================================================================
// --- Reset (panel X14 or HMI M102) --------------------------------
LDP     X14
ORP     M102
SET     M36                         // ENA pulse -> clears drive alarm
ZRST    M200        M220
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
// Stall capture (Rev 2.3): a closed-loop driver ALM while its axis runs a
// DDRVA move = jammed axis. The driver cuts motor current itself (motor
// goes limp, no more force); remember the axis and direction so the
// reset can back off D690 / D692 the other way.
LDI     X4
ANI     M36
AND     M50
SET     M180                        // X stalled
LDP     M180
DAND>   D200        D30
SET     M181                        // ...while moving +
LDP     M180
DAND<=  D200        D30
RST     M181
LDI     X5
ANI     M36
AND     M52
SET     M182                        // Y stalled
LDP     M182
DAND>   D204        D34
SET     M183                        // ...while moving +
LDP     M182
DAND<=  D204        D34
RST     M183
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
// A09 Z sensor plausibility (UP with DOWN, SAFE with DOWN, UP without SAFE)
LD      X2
AND     X3
LD      X2
AND     X17
ORB
LD      X20
AND     X3
ORB
LD      X2                          // UP but not in the SAFE zone:
ANI     X20                         // X20 sensor / steel flag lost
ORB
TMR     T6          K3
LD      T6
SET     M208
// A10 pad below safe height while an axis moves or WANTS to move.
//     The move request (M50/M52) is checked too: when M26 drops, M40/M42
//     cut the pulse contact at once, so the busy flag alone is too late.
LD      M1336
OR      M50
ANI     M26
LD      M1337
OR      M52
ANI     M26
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
// A16 sequence step timeout (auto, not while waiting for the pedal)
LD      M90
AND<>   D0          K10
AND=    D0          D98
TMR     T8          K150            // 15 s in one step
LD      T8
SET     M215
LD      M1000
MOV     D0          D98
// A17 pad landed while X was still moving (early-descent lead too long)
LD      M62
LD      M1336
OR      M50
ANB
SET     M216

// A20 PLC operation error (e.g. index out of range): M1067 / D1067 /
//     D1068 in the SV2 manual - VERIFY. Error code and step are kept
//     for the HMI debug screen.
LD      M1067
SET     M219
MOV     D1067       D683
MOV     D1068       D684
// A21 corrupted / impossible step register -> repaired (see N02b)
// (set below by the state sanity checks)

// --- Alarm words for HMI ------------------------------------------
LD      M1000
MOV     K4M200      D50
MOV     K4M216      D51
LD<>    D50         K0
OR<>    D51         K0
OUT     M21                         // any alarm

// --- Stop classes -------------------------------------------------
// M28 : position may be lost -> immediate stop + unhome
LD      M200
OR      M201
OR      M202
OR      M203
OR      M204
OR      M209
OR      M216
OUT     M28
// M29 : immediate pulse stop
LD      M28
OR      M212
OR      M213
OR      M218                        // axis inside a forbidden zone
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

// --- Black box: log the first alarm with the step it happened in --
LDP     M21
CALL    P11

// --- Any alarm: abort all sequences, pad up, drop move requests --
LD      M21
RST     M90
RST     M91
RST     M92
RST     M93
RST     M94
RST     M60
RST     M61
RST     M45
RST     M47
RST     M54
RST     M55
ZRST    D0          D4

// --- N02b State sanity: impossible step values are repaired ------
LD=     D0          K0
OR=     D0          K5
OR=     D0          K10
OR=     D0          K20
OR=     D0          K40
OR=     D0          K50
OR=     D0          K60
OR=     D0          K70
OR=     D0          K80
OR=     D0          K90
OR=     D0          K100
OR=     D0          K110
OR=     D0          K120
LD=     D1          K0
OR=     D1          K10
OR=     D1          K20
ANB
LD=     D2          K0
OR=     D2          K10
OR=     D2          K20
OR=     D2          K30
OR=     D2          K40
ANB
LD=     D3          K0
OR=     D3          K10
OR=     D3          K15
OR=     D3          K20
OR=     D3          K25
ANB
LD=     D4          K0
OR=     D4          K10
OR=     D4          K15
OR=     D4          K20
OR=     D4          K25
ANB
OUT     M170                        // all step registers valid
LDI     M170
SET     M220                        // A21 (alarm reaction resets steps)
ZRST    D0          D4

// --- Software safe reset (HMI M141): recover without power cycle ---
//     stops motion, drops every request and sequence, pad up, clears
//     alarms and the PLC error flag. Homing is kept unless lost.
LD      M141
RST     M90
RST     M91
RST     M92
RST     M93
RST     M94
RST     M60
RST     M61
RST     M45
RST     M46
RST     M47
RST     M48
RST     M54
RST     M55
ZRST    D0          D4
ZRST    M200        M220
RST     M1067
SET     M36                         // drive ENA pulse too

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
DZCP    D78         D80         D30     M76     // M77 = X at park
DZCP    D508        D510        D30     M79     // M80 = X in cliche zone
DSUB    D512        D548        D82
DADD    D512        D548        D84
DZCP    D82         D84         D34     M82     // M83 = Y at park
DSUB    D514        D548        D86
DADD    D514        D548        D88
DZCP    D86         D88         D34     M85     // M86 = Y at end

// Distance-to-go of X (0.1 mm) and current X target
DSUB    D200        D30         D90
DABS    D90                             // D90/D91 = |target - pos|
DLD=    D200        D500
OUT     M96                             // X target = pick
DLD=    D200        D502
OUT     M97                             // X target = print

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
OUT     M34                         // X AT PARK (stopped)
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
// Z fully UP confirmed (used for homing / start)
LD      X2
ANI     X3
ANI     X17
ANI     Y4
TMR     T205        D545
LD      T205
OUT     M25

// Z ABOVE SAFE HEIGHT (M26): X20 is a ZONE sensor (steel flag from
// fully up to safe height), so M26 follows it directly. A broken wire
// or a lost flag gives OFF = "not safe" -> X cannot move (fail-safe).
LD      X20
ANI     X3
ANI     X17
OUT     M26

// Z confirmed DOWN (pad compressed)
LD      X3
LD      X17
AND     M501
ORB
OUT     M62

// X may move only while the pad is above the safe height
LD      M26
ANI     X3
ANI     X17
AND     M20
OUT     M40
// Y may move if pad above safe height OR pad outside the cliche zone
LD      M26
ORI     M30
AND     M20
OUT     M42

// Early descent windows (option M507): X heading to the target and
// within D550 of it (also true once X has arrived there).
LD      M507
AND     M96
DAND<=  D90         D550
AND     M92                         // cliche inked
OUT     M63                         // early window: pick
LD      M507
AND     M97
DAND<=  D90         D550
OUT     M64                         // early window: print

// Forbidden Z-drop zones on X (P8 -> M67)
LD      M22
CALL    P8
LDI     M22
RST     M67

// Z may go down: (pick or early-pick) with cup parked,
//                or (print or early-print) with light curtain clear
LD      M31
OR      M63
AND     M33
LD      M32
OR      M64
AND     X16
ORB
AND     M24
AND     M20
ANI     M67                         // never in a no-drop zone
OUT     M41
LDI     M41
RST     M60                         // permit lost -> never re-descend later
RST     M61


// =====================================================================
// N05  MODE, START / STOP, PEDAL LATCH, HOMING REQUEST
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
LD      M132                        // operator logged in
ORI     M508                        // (or login not required)
ANB
ANI     M95                         // batch done: reset the batch first
SET     M90
RST     M91
RST     M94
MOV     K5          D0

// Start pressed without login -> HMI message "log in first"
LD      M100
ANI     M132
AND     M508
SET     M137
LD      M132
RST     M137

// Stop at end of cycle (NC stop PB, HMI stop, or leaving auto mode)
LDI     X13
OR      M101
ORI     M120
AND     M90
SET     M91

// Pedal latch: accepted while waiting (S10) and during the pick phase
LDP     X11
AND     M90
AND     X16
AND<=   D0          K70
SET     M94

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
// H10 : drop Z commands, forget home, wait Z fully up
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
// H40 : X -> park, Y -> park
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
// Print mode (HMI D554): 0 = 1 pedal : 1 print
//                        1 = 1 pedal : N prints (N = D555, multi-hit)
//                        2 = continuous, no pedal (pause D546)
LD=     D554        K2
OUT     M502
// S5  : go to start position (X pick, Y park)
LD=     D0          K5
ANI     M31
ANI     M45
AND     M58
AND     M40
DMOV    D500        D200
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
AND     M31
AND     M33
MOV     K10         D0

// S10 : decision point
//  - stop request                         -> idle
//  - pre-pick and pad empty               -> S20 (pick, no pedal)
//  - pre-pick, pad loaded, pedal/continuous -> S80 (print)
//  - normal, pedal/continuous             -> S20
LD=     D0          K10
AND     M91
RST     M90
RST     M91
RST     M93                         // a waiting pad is discarded (dries)
RST     M94
MOV     K0          D556
MOV     K0          D0
LD=     D0          K10
AND     M502
TMR     T206        D546
LD=     D0          K10
AND     M93
TMR     T207        D552            // pre-pick: pad waiting too long
LD      T207
RST     M93                         // ink on the pad is too dry -> re-pick
LD=     D0          K10
ANI     M91
AND     M506
ANI     M93
AND     M20
MOV     K20         D0
LD=     D0          K10
ANI     M91
AND     M506
AND     M93
AND     X16
AND     M20
LD      M94
OR      T206
ANB
RST     M94
MOV     K80         D0
LD=     D0          K10
ANI     M91
ANI     M506
AND     X16
AND     M20
LD      M94
OR      T206
ANB
RST     M94
MOV     K20         D0

// S20 : X -> pick (if not there / not moving) + ink stroke (if needed)
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
AND     M92
AND     M33
LD      M31
OR      M63                         // early descent at pick
ANB
MOV     K40         D0

// S40 : flash-off delay (ink tack build-up)
LD=     D0          K40
TMR     T202        D542
LD=     D0          K40
AND     T202
MOV     K50         D0

// S50 : Z down on cliche (skipped in dry-run); dwell starts only with
//       the pad down AND X stopped at pick
LD=     D0          K50
ANI     M503
AND     M41
SET     M60
LD=     D0          K50
LD      M62
OR      M503
ANB
AND     M31
MOV     K60         D0

// S60 : dwell-1, then Z up; pad now loaded
LD=     D0          K60
TMR     T200        D540
LD=     D0          K60
AND     T200
RST     M60
RST     M92                         // image consumed
SET     M93                         // pad loaded
MOV     K70         D0

// S70 : pad above safe height -> re-ink in parallel, then go on
LD=     D0          K70
AND     M26
AND     M500
AND=    D1          K0
MOV     K10         D1
LD=     D0          K70
AND     M26
AND     M506
MOV     K10         D0              // pre-pick: wait for the pedal
LD=     D0          K70
AND     M26
ANI     M506
MOV     K80         D0

// S80 : X -> print (Z may start down early inside the D550 window)
LD=     D0          K80
ANI     M32
ANI     M45
AND     M58
AND     M40
DMOV    D502        D200
MOV     D522        D202
SET     M45
LD=     D0          K80
LD      M32
OR      M64
ANB
MOV     K90         D0

// Pad-down step inside a no-drop zone: alarm at once (A18), do not wait
LD=     D0          K50
OR=     D0          K90
AND     M67
SET     M217

// S90 : Z down on part; dwell starts only with pad down AND X stopped
LD=     D0          K90
ANI     M503
AND     M41
SET     M60
LD=     D0          K90
LD      M62
OR      M503
ANB
AND     M32
MOV     K100        D0

// S100 : dwell-2, then Z up; count the print
LD=     D0          K100
TMR     T201        D541
LD=     D0          K100
AND     T201
RST     M60
RST     M93
DINC    D560
DINC    D562
MOV     T210        D566            // time between prints (10 ms)
MOV     K0          D567
SET     M99                         // restart print-interval timer
INC     D556                        // prints in this burst
MOV     K110        D0

// Multi-hit: request the next print by itself until N prints are done
LD      M99
AND=    D554        K1
AND<    D556        D555
ANI     M91
SET     M94
LD      M99                         // burst finished -> reset counter
LD<>    D554        K1
OR>=    D556        D555
OR      M91
ANB
MOV     K0          D556

// S110 : pad above safe height -> X may leave
LD=     D0          K110
AND     M26
MOV     K120        D0

// S120 : X -> pick, do not wait for arrival (S20 / S10 handle it)
LD=     D0          K120
ANI     M31
ANI     M45
AND     M58
AND     M40
DMOV    D500        D200
MOV     D522        D202
SET     M45
MOV     K10         D0
LD=     D0          K120
AND     M31
MOV     K10         D0

// Parts per hour from the last print interval
LD      M99
AND>    D566        K0
DDIV    K360000     D566        D570
MOV     D570        D568

// Batch complete -> stop at end of cycle
LD      M504
DAND>=  D562        D564
DAND>   D564        K0
SET     M95
SET     M91

// Per-operator / per-shift counting (N13 keeps E1 = operator index)
LD      M99
AND     M132
DINC    D606                        // this session
INC     D3040E1                     // this operator, this shift
LD      M99
DINC    D611                        // machine, this shift

// Print-interval timer (10 ms base), restarted by M99
LD      M90
ANI     M99
TMR     T210        K32767
LD      M99
RST     M99


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
CALL    P2                          // ...but stop before a forbidden zone
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
CALL    P3
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
CALL    P6
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
CALL    P7
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
// ---- Stall back-off (Rev 2.3): after the reset that clears A02/A03,
//      move the jammed axis back D690 / D692 at creep speed, once. The
//      axis stays unhomed (class A); re-home after removing the obstacle.
LDP     X14
ORP     M102
AND     M180
SET     M184                        // X back-off armed
LDP     X14
ORP     M102
AND     M182
SET     M185                        // Y back-off armed
LD      M184
ANI     M36
AND     X4
AND     M58
AND     M40
ANI     M45
AND     M181
DSUB    D30         D690        D200    // stalled going + -> back to -
LD      M184
ANI     M36
AND     X4
AND     M58
AND     M40
ANI     M45
ANI     M181
DADD    D30         D690        D200    // stalled going - -> back to +
LD      M184
ANI     M36
AND     X4
AND     M58
AND     M40
ANI     M45
MOV     D525        D202
SET     M45
RST     M184
RST     M180
LD      M185
ANI     M36
AND     X5
AND     M59
AND     M42
ANI     M47
AND     M183
DSUB    D34         D692        D204
LD      M185
ANI     M36
AND     X5
AND     M59
AND     M42
ANI     M47
ANI     M183
DADD    D34         D692        D204
LD      M185
ANI     M36
AND     X5
AND     M59
AND     M42
ANI     M47
MOV     D531        D206
SET     M47
RST     M185
RST     M182

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

// ---- Manual Z (only with X stopped at pick or print) --------------
LD      M108
AND     M38
AND     M41
ANI     M1336
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

// ---- Forbidden zones: path checks (only meaningful when homed) ----
LD      M22
CALL    P4
LDI     M22
RST     M68
RST     M66
LD      M23
CALL    P5
LDI     M23
RST     M69
RST     M65
LD      M45                         // positioning move through a zone
AND     M68
SET     M217                        // A18: move rejected
RST     M45
LD      M47
AND     M69
SET     M217
RST     M47
LDP     M66                         // entered a zone anyway
AND     M22
LDP     M65
AND     M23
ORB
SET     M218                        // A19: immediate stop

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
// N11  Z VALVE (bistable 5/2, 3/8) - coils mutually exclusive, held
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

// Why won't it run? (D680 bits, shown as text on the HMI debug page)
LDI     M24
OUT     M150                        // b0 not homed
LD      M21
OUT     M151                        // b1 alarm active
LDI     M120
OUT     M152                        // b2 manual mode selected
LDI     X16
OUT     M153                        // b3 light curtain / guard
LDI     X15
OUT     M154                        // b4 air pressure low
LDI     X10
OUT     M155                        // b5 E-stop
LD      M508
ANI     M132
OUT     M156                        // b6 operator not logged in
LDI     M26
OUT     M157                        // b7 pad not above safe height
LD>     D2          K0
OUT     M158                        // b8 homing running
LD      M68
OUT     M159                        // b9 X path through a forbidden zone
LD      M69
OUT     M160                        // b10 Y path through a forbidden zone
LD      M67
OUT     M161                        // b11 X is in a no-drop zone
LD      M219
OUT     M162                        // b12 PLC operation error
LD      M1000
MOV     K4M150      D680

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
RST     M140
RST     M141

// =====================================================================
// N13  OPERATORS, SHIFTS, SESSION LOG, ERP LIVE BLOCK
//      Operator = last 4 digits of the national ID (1..9999).
//      Registry D3000..D3039 (40 operators, written from HMI or ERP).
//      Per-operator count this shift D3040..D3079 (same index).
//      Session log ring D3100..D3739: 64 records x 10 words.
//      Live block for ERP D3080..D3095 (one Modbus read).
//      RTC registers D1314 min, D1315 hour, D1316 day, D1317 month,
//      D1319 year (00-99): VERIFY with the SV2 manual.
// =====================================================================
LD      M1000
MOV     D626        E1              // current operator index
MUL     D1315       K100        D620
ADD     D620        D1314       D620    // D620 = now hhmm
MUL     D1317       K100        D630
ADD     D630        D1316       D623    // D623 = today MMDD

// Shift from clock: 1 = [D603,D604), 2 = [D604,D605), 3 = otherwise
MOV     K3          D622
LD>=    D620        D603
AND<    D620        D604
MOV     K1          D622
LD>=    D620        D604
AND<    D620        D605
MOV     K2          D622

// Shift change: close the running session, clear shift counters,
// and open a new session for the same operator
LD<>    D622        D602
OUT     M134
LD      M134
AND     M132
CALL    P1
LD      M134
ZRST    D3040       D3079
DMOV    K0          D611
MOV     D622        D602
DMOV    K0          D606
MOV     D620        D608
MOV     D623        D609
MOV     D1319       D610

// ---- Login (HMI writes the 4 digits to D600, then pulses M130) ----
LDP     M130
OUT     M135
LDI     M135
CJ      P10
LD      M1000                       // new rung: reset search result
MOV     K-1         D625
MOV     K0          E0
FOR     K40
LD=     D3000E0     D600
AND>    D600        K0
MOV     E0          D625
LD      M1000
INC     E0
NEXT
P10
LD      M135
AND>=   D625        K0
OUT     M136                        // code found in the registry
LD      M135
AND<    D625        K0
SET     M133                        // code not found
LD      M133
TMR     T208        K300            // message for 3 s
LD      T208
RST     M133
LD      M136
AND     M132
CALL    P1                          // close the previous operator
LD      M136
RST     M133
SET     M132
MOV     D600        D601
MOV     D625        D626
MOV     D625        E1
DMOV    K0          D606
MOV     D620        D608
MOV     D623        D609
MOV     D1319       D610
MOV     K0          D600

// ---- Logout (HMI M131) ---------------------------------------------
LDP     M131
AND     M132
CALL    P1
LDP     M131
RST     M132
MOV     K0          D601
LD      M1000                       // HMI Set-ON commands handled
RST     M130
RST     M131

// ---- Display and ERP live block ------------------------------------
LD      M132
MOV     D3040E1     D616            // this operator's prints this shift
LDI     M132
MOV     K0          D616
LD      M1000
MOV     D9          D3080           // machine state
MOV     D601        D3081           // operator code
MOV     D602        D3082           // shift
DMOV    D606        D3083           // session prints
DMOV    D611        D3085           // machine prints this shift
DMOV    D560        D3087           // total counter
MOV     D568        D3089           // prints per hour
MOV     D50         D3090           // alarm word 1
MOV     D51         D3091           // alarm word 2
MOV     D554        D3092           // print mode
MOV     D3097       D3093           // last record sequence number
MOV     D627        D3094           // next record slot
MOV     D616        D3095           // operator prints this shift

FEND

// =====================================================================
// P1  Close session: write one record into the ring buffer
//     [0] operator  [1] shift  [2] start MMDD  [3] start year
//     [4] start hhmm  [5] end hhmm  [6..7] prints (DW)  [8] seq  [9] 0
// =====================================================================
P1
LD      M1000
MUL     D627        K10         D628
MOV     D628        E2
MOV     D601        D3100E2
MOV     D602        D3101E2
MOV     D609        D3102E2
MOV     D610        D3103E2
MOV     D608        D3104E2
MOV     D620        D3105E2
DMOV    D606        D3106E2
INC     D3097
MOV     D3097       D3108E2
MOV     K0          D3109E2
INC     D627
LD>=    D627        K64
MOV     K0          D627
SRET

// =====================================================================
// FORBIDDEN ZONES (HMI screen 10). A zone is enabled when hi > lo.
//   X zones: 4 x [lo DW, hi DW] at D640 + 4k   (k = 0..3)
//   Y zones: 2 x [lo DW, hi DW] at D656 + 4k
//   Z no-drop zones on X: 2 x [lo, hi] at D664 + 4k
//   D672 = margin kept from a zone edge when jogging (0.1 mm)
// =====================================================================

// P2  X jog+ : lower D200 to the first zone edge ahead (minus margin)
P2
LD      M1000
MOV     K0          E3
FOR     K4
LD      M1000
RST     M171
DLD>    D642E3      D640E3
DAND>   D640E3      D30
SET     M171
DSUB    D640E3      D672        D678
LD      M171
DAND<   D678        D200
DMOV    D678        D200
LD      M1000
ADD     E3          K4          E3
NEXT
DLD<    D200        D30
DMOV    D30         D200
SRET

// P3  X jog- : raise D200 to the first zone edge behind (plus margin)
P3
LD      M1000
MOV     K0          E3
FOR     K4
LD      M1000
RST     M171
DLD>    D642E3      D640E3
DAND<   D642E3      D30
SET     M171
DADD    D642E3      D672        D678
LD      M171
DAND>   D678        D200
DMOV    D678        D200
LD      M1000
ADD     E3          K4          E3
NEXT
DLD>    D200        D30
DMOV    D30         D200
SRET

// P4  X path check: M68 = path D30..D200 touches a zone, M66 = inside
P4
LD      M1000
RST     M68
RST     M66
DMOV    D30         D674
DMOV    D200        D676
DLD<    D30         D200
DMOV    D200        D674
DMOV    D30         D676
LD      M1000
MOV     K0          E3
FOR     K4
DLD>    D642E3      D640E3
DAND>=  D674        D640E3
DAND<=  D676        D642E3
SET     M68
DLD>    D642E3      D640E3
DAND>=  D30         D640E3
DAND<=  D30         D642E3
SET     M66
LD      M1000
ADD     E3          K4          E3
NEXT
SRET

// P5  Y path check: M69 = path D34..D204 touches a zone, M65 = inside
P5
LD      M1000
RST     M69
RST     M65
DMOV    D34         D674
DMOV    D204        D676
DLD<    D34         D204
DMOV    D204        D674
DMOV    D34         D676
LD      M1000
MOV     K0          E3
FOR     K2
DLD>    D658E3      D656E3
DAND>=  D674        D656E3
DAND<=  D676        D658E3
SET     M69
DLD>    D658E3      D656E3
DAND>=  D34         D656E3
DAND<=  D34         D658E3
SET     M65
LD      M1000
ADD     E3          K4          E3
NEXT
SRET

// P6  Y jog+ clamp
P6
LD      M1000
MOV     K0          E3
FOR     K2
LD      M1000
RST     M171
DLD>    D658E3      D656E3
DAND>   D656E3      D34
SET     M171
DSUB    D656E3      D672        D678
LD      M171
DAND<   D678        D204
DMOV    D678        D204
LD      M1000
ADD     E3          K4          E3
NEXT
DLD<    D204        D34
DMOV    D34         D204
SRET

// P7  Y jog- clamp
P7
LD      M1000
MOV     K0          E3
FOR     K2
LD      M1000
RST     M171
DLD>    D658E3      D656E3
DAND<   D658E3      D34
SET     M171
DADD    D658E3      D672        D678
LD      M171
DAND>   D678        D204
DMOV    D678        D204
LD      M1000
ADD     E3          K4          E3
NEXT
DLD>    D204        D34
DMOV    D34         D204
SRET

// P8  Z no-drop zones on X: M67 = X inside one
P8
LD      M1000
RST     M67
MOV     K0          E3
FOR     K2
DLD>    D666E3      D664E3
DAND>=  D30         D664E3
DAND<=  D30         D666E3
SET     M67
LD      M1000
ADD     E3          K4          E3
NEXT
SRET

// =====================================================================
// P11  Black box: 16 x 8 words at D3750, next slot D681, count D682
//      [0] first alarm code (1 = A01 ...) [1] D0 [2] D1 [3] D2
//      [4] time hhmm [5] date MMDD [6] X pos (0.1 mm) [7] D680 reasons
// =====================================================================
P11
LD      M1000
MOV     K0          D685
MOV     K0          E4
FOR     K21
LD      M200E4
AND=    D685        K0
MOV     E4          D685
INC     D685
LD      M1000
INC     E4
NEXT
LD      M1000
MUL     D681        K8          D686
MOV     D686        E5
MOV     D685        D3750E5
MOV     D0          D3751E5
MOV     D1          D3752E5
MOV     D2          D3753E5
MOV     D620        D3754E5
MOV     D623        D3755E5
MOV     D30         D3756E5
MOV     D680        D3757E5
INC     D682
INC     D681
LD>=    D681        K16
MOV     K0          D681
SRET

// =====================================================================
// P9  Default parameters
// =====================================================================
P9
LD      M1000
DMOV    K100000     D518            // X pulses / 1000 mm (100 p/mm)
DMOV    K33333      D520            // Y pulses / 1000 mm
DMOV    K500        D500            // X pick-up pos    50.0 mm
DMOV    K4950       D502            // X print pos     495.0 mm (disc Ø1000, r 375)
DMOV    K500        D504            // X park (homing) pos = pick
DMOV    K7500       D506            // X soft max      750.0 mm (X travel 75 cm)
DMOV    K0          D508            // X cliche zone min   0.0 mm
DMOV    K2000       D510            // X cliche zone max 200.0 mm
DMOV    K50         D512            // Y park pos        5.0 mm
DMOV    K3500       D514            // Y end pos       350.0 mm
DMOV    K3750       D516            // Y soft max      375.0 mm
DMOV    K50         D690            // X back-off after a stall  5.0 mm
DMOV    K50         D692            // Y back-off after a stall  5.0 mm
MOV     K800        D522            // X auto speed    mm/s
MOV     K100        D523            // X jog / manual  mm/s
MOV     K60         D524            // X home speed    mm/s
MOV     K8          D525            // X creep speed   mm/s
MOV     K300        D526            // X accel/decel   ms
MOV     K400        D527            // Y out speed     mm/s
MOV     K400        D528            // Y return speed  mm/s
MOV     K80         D529            // Y jog           mm/s
MOV     K60         D530            // Y home          mm/s
MOV     K8          D531            // Y creep         mm/s
MOV     K300        D532            // Y accel/decel   ms
MOV     K50         D540            // Dwell-1 pick    0.50 s
MOV     K50         D541            // Dwell-2 print   0.50 s
MOV     K0          D542            // Flash-off delay 0.00 s
MOV     K150        D543            // Z down timeout  1.50 s
MOV     K150        D544            // Z up timeout    1.50 s
MOV     K10         D545            // Z settle after UP 0.10 s
MOV     K50         D546            // Continuous pause 0.50 s
MOV     K0          D554            // Print mode 0 = 1 pedal : 1 print
MOV     K2          D555            // Multi-hit count N
MOV     K600        D603            // Shift 1 start 06:00
MOV     K1400       D604            // Shift 2 start 14:00
MOV     K2200       D605            // Shift 3 start 22:00 (ends 06:00)
SET     M508                        // login required to start
MOV     K300        D547            // Homing timeout 30.0 s (100 ms units)
DMOV    K5          D548            // In-position tolerance 0.5 mm
DMOV    K50         D550            // Early Z descent lead 5.0 mm
MOV     K300        D552            // Pre-pick max wait 3.00 s
DMOV    K0          D564            // Batch target (0 = off)
SET     M500                        // parallel inking ON
RST     M506                        // pre-pick OFF until commissioned
RST     M507                        // early Z descent OFF until tuned
DMOV    K0          D640            // forbidden zones: all disabled
ZRST    D640        D671
DMOV    K20         D672            // zone safety margin 2.0 mm
SRET

END
