#!/usr/bin/env python3
"""ERP gateway for the pad printer (Modbus TCP -> ERP).

Runs on any PC / mini-PC in the plant network. It polls the Delta
DVP-28SV2 through its Ethernet module (DVPEN01-SL, Modbus TCP server,
port 502) and:

  * posts a live status snapshot every POLL_S seconds (best effort)
  * reads new work-session records from the PLC ring buffer (64 records)
    exactly once each, using their sequence numbers
  * sends everything to the ERP as JSON over HTTP(S)
  * keeps session records in an append-only local journal (JSON lines)
    so nothing is lost
    while the ERP or the network is down; unsent lines are retried
  * optional: pushes the operator registry (40 codes) and the clock to
    the PLC

Configuration: environment variables (see CONFIG below) or edit here.
Dependencies:  pip install pymodbus==3.6.9 requests

Delta DVP Modbus addressing (verify with the DVPEN01-SL manual):
    D0..D4095  -> holding registers 0x1000 + n   (4096 + n)
    M0..M1535  -> coils            0x0800 + n   (2048 + n)
"""
import json
import os
import sys
import time
from datetime import datetime

CONFIG = {
    "PLC_HOST": os.environ.get("PLC_HOST", "192.168.1.50"),
    "PLC_PORT": int(os.environ.get("PLC_PORT", "502")),
    "PLC_UNIT": int(os.environ.get("PLC_UNIT", "1")),
    "MACHINE_ID": os.environ.get("MACHINE_ID", "TAMPO-01"),
    "ERP_URL": os.environ.get("ERP_URL", ""),          # e.g. https://erp.local/api/pad-printer
    "ERP_TOKEN": os.environ.get("ERP_TOKEN", ""),
    "JOURNAL": os.environ.get("JOURNAL", "tampo_journal.jsonl"),
    "SENT_MARK": os.environ.get("SENT_MARK", "tampo_journal.sent"),
    "POLL_S": float(os.environ.get("POLL_S", "5")),
}

D_BASE = 0x1000
LIVE = 3080          # D3080..D3095
RING = 3100          # D3100..D3739, 64 x 10 words
RING_N, REC_W = 64, 10
REGISTRY = 3000      # D3000..D3039
STATE = {0: "not_homed", 1: "homing", 2: "ready", 3: "auto", 4: "stopping", 5: "alarm"}
MODE = {0: "1_pedal_1_print", 1: "1_pedal_N_prints", 2: "continuous"}


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def u32(lo, hi):
    return (hi << 16) | lo


def decode_live(r):
    """r = 16 registers read from D3080."""
    return {
        "state": STATE.get(r[0], r[0]),
        "operator": r[1] or None,
        "shift": r[2],
        "session_prints": u32(r[3], r[4]),
        "shift_prints": u32(r[5], r[6]),
        "total_prints": u32(r[7], r[8]),
        "prints_per_hour": r[9],
        "alarm_word1": r[10],
        "alarm_word2": r[11],
        "alarms": [f"A{i + 1:02d}" for i in range(16) if r[10] >> i & 1]
                  + (["A17"] if r[11] & 1 else []),
        "print_mode": MODE.get(r[12], r[12]),
        "last_seq": r[13],
        "next_slot": r[14],
        "operator_shift_prints": r[15],
    }


def decode_record(w):
    """w = 10 registers of one session record."""
    mmdd, yy = w[2], w[3]
    return {
        "operator": w[0],
        "shift": w[1],
        "date": f"20{yy:02d}-{mmdd // 100:02d}-{mmdd % 100:02d}",
        "start": f"{w[4] // 100:02d}:{w[4] % 100:02d}",
        "end": f"{w[5] // 100:02d}:{w[5] % 100:02d}",
        "prints": u32(w[6], w[7]),
        "seq": w[8],
    }


def new_records(ring, last_seq):
    """ring = 640 registers. Returns records with seq after last_seq
    (16-bit wrap-around aware), oldest first."""
    recs = []
    for i in range(RING_N):
        w = ring[i * REC_W:(i + 1) * REC_W]
        seq = w[8]
        if seq == 0 and w[0] == 0:
            continue
        if last_seq is None or 0 < (seq - last_seq) % 65536 < 32768:
            recs.append(decode_record(w))
    return sorted(recs, key=lambda r: (r["seq"] - (last_seq or 0)) % 65536)


class Journal:
    """Append-only JSON-lines file + byte offset of what the ERP accepted."""

    def __init__(self, path, mark):
        self.path, self.mark = path, mark

    def append(self, obj):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def pending(self):
        off = int(open(self.mark).read() or 0) if os.path.exists(self.mark) else 0
        if not os.path.exists(self.path):
            return off, []
        with open(self.path, encoding="utf-8") as f:
            f.seek(off)
            lines = f.readlines()
        return off, lines

    def commit(self, off):
        with open(self.mark, "w") as f:
            f.write(str(off))


def post_erp(payload):
    if not CONFIG["ERP_URL"]:
        return True                       # journal-only mode
    import requests
    h = {"Content-Type": "application/json"}
    if CONFIG["ERP_TOKEN"]:
        h["Authorization"] = "Bearer " + CONFIG["ERP_TOKEN"]
    r = requests.post(CONFIG["ERP_URL"], data=json.dumps(payload, ensure_ascii=False).encode(),
                      headers=h, timeout=5)
    return 200 <= r.status_code < 300


def flush(journal):
    off, lines = journal.pending()
    for line in lines:
        try:
            ok = post_erp(json.loads(line))
        except Exception as e:           # network down: retry next poll
            print("ERP unreachable:", e)
            return
        if not ok:
            print("ERP rejected a record; will retry")
            return
        off += len(line.encode("utf-8"))
        journal.commit(off)


def read_d(client, d, count):
    out = []
    while count:
        n = min(count, 120)
        rr = client.read_holding_registers(D_BASE + d, n, slave=CONFIG["PLC_UNIT"])
        if rr.isError():
            raise IOError(rr)
        out += rr.registers
        d += n
        count -= n
    return out


def push_registry(client, codes):
    """Write up to 40 operator codes (last 4 digits of national ID)."""
    codes = (list(codes) + [0] * 40)[:40]
    client.write_registers(D_BASE + REGISTRY, codes, slave=CONFIG["PLC_UNIT"])


def main():
    from pymodbus.client import ModbusTcpClient
    journal = Journal(CONFIG["JOURNAL"], CONFIG["SENT_MARK"])
    state_file = CONFIG["JOURNAL"] + ".seq"
    last_seq = int(open(state_file).read()) if os.path.exists(state_file) else None
    client = ModbusTcpClient(CONFIG["PLC_HOST"], port=CONFIG["PLC_PORT"], timeout=3)
    if len(sys.argv) > 2 and sys.argv[1] == "--registry":
        client.connect()
        push_registry(client, [int(c) for c in sys.argv[2].split(",")])
        print("registry written")
        return
    while True:
        try:
            if not client.connected:
                client.connect()
            live = decode_live(read_d(client, LIVE, 16))
            now = datetime.now().isoformat(timespec="seconds")
            try:                          # live status: best effort, not journaled
                post_erp({"type": "status", "machine": CONFIG["MACHINE_ID"], "time": now, **live})
            except Exception as e:
                print("ERP status not sent:", e)
            if last_seq is None or live["last_seq"] != last_seq:
                ring = read_d(client, RING, RING_N * REC_W)
                for rec in new_records(ring, last_seq):
                    journal.append({"type": "session", "machine": CONFIG["MACHINE_ID"],
                                    "received": now, **rec})
                    last_seq = rec["seq"]
                open(state_file, "w").write(str(last_seq))
        except Exception as e:
            print("PLC read failed:", e)
            client.close()
        flush(journal)
        time.sleep(CONFIG["POLL_S"])


if __name__ == "__main__":
    main()
