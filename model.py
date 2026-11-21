"""Model System Dynamics bulanan: Ketersediaan Beras Provinsi Jawa Barat.

Stock : Populasi P, Konsumsi per kapita k, Level produksi Q (ton/thn),
        Stok surplus S, Produksi kumulatif Cp, Konsumsi kumulatif Cc
Flow  : laju tumbuh P, k, Q (kontinu); produksi musiman; konsumsi; impor
Solver: Euler dan Runge-Kutta 4 (dibandingkan untuk uji teori)

dP/dt = r_p P          dk/dt = r_k k          dQ/dt = r_q Q
dS/dt = 12*share_m*Q + impor - P*k/1000      (ton/tahun, t dalam tahun)

Hanya pustaka standar Python (ringan untuk Vercel).
"""
import csv
import math
import os

NAMA_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ---------------------------------------------------------------- data
def load_data(folder):
    """Baca produksi_bulanan.csv dan data_tahunan.csv."""
    bulanan = []
    with open(os.path.join(folder, "produksi_bulanan.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bulanan.append((int(r["tahun"]), int(r["bulan"]), float(r["produksi_beras_ton"])))
    tahunan = {}
    with open(os.path.join(folder, "data_tahunan.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tahunan[int(r["tahun"])] = {
                "populasi": float(r["populasi"]),
                "konsumsi_kg": float(r["konsumsi_beras_kg_kapita"]) if r["konsumsi_beras_kg_kapita"] else None,
            }
    return {"bulanan": bulanan, "tahunan": tahunan}


def produksi_tahunan(bulanan):
    out = {}
    for t, _, v in bulanan:
        out[t] = out.get(t, 0.0) + v
    return out


# ------------------------------------------------------------ estimasi
def fit_exp(ts, nilai):
    """Regresi log-linear ln(x)=a+b*t. Kembalikan (a, b); b = laju kontinu/tahun."""
    n = len(ts)
    ys = [math.log(v) for v in nilai]
    mt, my = sum(ts) / n, sum(ys) / n
    b = sum((t - mt) * (y - my) for t, y in zip(ts, ys)) / sum((t - mt) ** 2 for t in ts)
    return my - b * mt, b


def estimasi(data, tahun_terakhir):
    """Estimasi parameter memakai data sampai tahun_terakhir (inklusif)."""
    prod = produksi_tahunan([x for x in data["bulanan"] if x[0] <= tahun_terakhir])
    ys = sorted(prod)
    aq, bq = fit_exp([y + 0.5 for y in ys], [prod[y] for y in ys])      # produksi (ton/thn)
    pp = [(y, d["populasi"]) for y, d in sorted(data["tahunan"].items()) if y <= tahun_terakhir]
    ap, bp = fit_exp([y + 0.5 for y, _ in pp], [v for _, v in pp])
    kk = [(y, d["konsumsi_kg"]) for y, d in sorted(data["tahunan"].items())
          if y <= tahun_terakhir and d["konsumsi_kg"]]
    ak, bk = fit_exp([y + 0.5 for y, _ in kk], [v for _, v in kk])
    # pola musiman: rata-rata porsi bulanan per tahun
    share = [0.0] * 12
    for y in ys:
        tot = prod[y]
        for t, m, v in data["bulanan"]:
            if t == y:
                share[m - 1] += v / tot / len(ys)
    return {
        "a_q": aq, "r_q": bq, "a_p": ap, "r_p": bp, "a_k": ak, "r_k": bk,
        "share": share,
        "tahun_latih": (ys[0], ys[-1]),
        "n_tahun_latih": len(ys),
        "n_tahun_konsumsi": len(kk),
    }


def parameter_awal(est, tahun_mulai):
    """Kondisi awal pada 1 Januari tahun_mulai dari garis regresi."""
    t0 = float(tahun_mulai)
    return {
        "P0": math.exp(est["a_p"] + est["r_p"] * t0),
        "k0": math.exp(est["a_k"] + est["r_k"] * t0),
        "Q0": math.exp(est["a_q"] + est["r_q"] * t0),
    }


# --------------------------------------------------------------- model
def turunan(s, p, m):
    """Turunan state s=[P,k,Q,S,Cp,Cc] pada bulan ke-m (0..11)."""
    P, k, Q, S, Cp, Cc = s
    produksi = 12.0 * p["share"][m] * Q          # ton/thn (laju sesaat)
    konsumsi = P * k / 1000.0                     # ton/thn
    return [p["r_p"] * P, p["r_k"] * k, p["r_q"] * Q,
            produksi + p["impor"] - konsumsi, produksi, konsumsi]


def _euler(s, p, h, m):
    d = turunan(s, p, m)
    return [x + h * dx for x, dx in zip(s, d)]


def _rk4(s, p, h, m):
    k1 = turunan(s, p, m)
    k2 = turunan([x + h / 2 * a for x, a in zip(s, k1)], p, m)
    k3 = turunan([x + h / 2 * a for x, a in zip(s, k2)], p, m)
    k4 = turunan([x + h * a for x, a in zip(s, k3)], p, m)
    return [x + h / 6 * (a + 2 * b + 2 * c + d)
            for x, a, b, c, d in zip(s, k1, k2, k3, k4)]


def simulasi(p, tahun_mulai, n_bulan, metode="euler", sub=1):
    """Simulasi bulanan mulai 1 Jan tahun_mulai. Kembalikan daftar hasil per bulan."""
    step = _rk4 if metode == "rk4" else _euler
    sub = max(1, int(sub))
    h = (1.0 / 12.0) / sub
    s = [p["P0"], p["k0"], p["Q0"], p["S0"], 0.0, 0.0]
    hasil = []
    for i in range(n_bulan):
        m = i % 12
        awal = (s[4], s[5])
        for _ in range(sub):
            s = step(s, p, h, m)
        hasil.append({
            "tahun": tahun_mulai + i // 12, "bulan": m + 1,
            "populasi": s[0], "konsumsi_kg_kapita": s[1],
            "produksi_ton": s[4] - awal[0], "konsumsi_ton": s[5] - awal[1],
            "stok_ton": s[3],
        })
    return hasil


def ringkas_tahunan(hasil_bulanan):
    out = {}
    for r in hasil_bulanan:
        a = out.setdefault(r["tahun"], {"tahun": r["tahun"], "produksi_ton": 0.0,
                                        "konsumsi_ton": 0.0})
        a["produksi_ton"] += r["produksi_ton"]
        a["konsumsi_ton"] += r["konsumsi_ton"]
        a["stok_akhir_ton"] = r["stok_ton"]
        a["populasi"] = r["populasi"]
        a["konsumsi_kg_kapita"] = r["konsumsi_kg_kapita"]
    for a in out.values():
        a["rasio_ketersediaan"] = (a["produksi_ton"] / a["konsumsi_ton"]
                                   if a["konsumsi_ton"] else None)
    return [out[t] for t in sorted(out)]


# ------------------------------------------------------------ validasi
def mape(aktual, prediksi):
    return 100.0 * sum(abs(a - f) / abs(a) for a, f in zip(aktual, prediksi)) / len(aktual)


def rmse(aktual, prediksi):
    return math.sqrt(sum((a - f) ** 2 for a, f in zip(aktual, prediksi)) / len(aktual))


def validasi(data, impor=0.0, metode="euler", sub=1, tahun_uji=None):
    """Latih sampai tahun_uji-1, simulasi dari 2020, bandingkan dengan tahun_uji."""
    tahun_uji = tahun_uji or max(t for t, _, _ in data["bulanan"])
    est = estimasi(data, tahun_uji - 1)
    t_awal = min(t for t, _, _ in data["bulanan"])
    p = dict(est)
    p.update(parameter_awal(est, t_awal))
    p.update(impor=impor, S0=0.0)
    n = (tahun_uji - t_awal + 1) * 12
    sim = simulasi(p, t_awal, n, metode, sub)

    uji_sim = [r for r in sim if r["tahun"] == tahun_uji]
    uji_obs = [v for t, _, v in data["bulanan"] if t == tahun_uji]
    prod_s = [r["produksi_ton"] for r in uji_sim]
    out = {
        "tahun_uji": tahun_uji,
        "tahun_latih": est["tahun_latih"],
        "produksi_bulanan": {"mape_persen": mape(uji_obs, prod_s), "rmse_ton": rmse(uji_obs, prod_s)},
        "bulanan_uji": {"bulan": NAMA_BULAN, "aktual": uji_obs, "simulasi": prod_s},
    }
    pa, ps = sum(uji_obs), sum(prod_s)
    out["produksi_tahunan"] = {"aktual_ton": pa, "simulasi_ton": ps,
                               "galat_persen": 100.0 * (ps - pa) / pa}
    d = data["tahunan"].get(tahun_uji, {})
    if d.get("populasi"):
        pop_s = uji_sim[5]["populasi"]
        out["populasi"] = {"aktual": d["populasi"], "simulasi": pop_s,
                           "galat_persen": 100.0 * (pop_s - d["populasi"]) / d["populasi"]}
    if d.get("konsumsi_kg"):
        ks = sum(r["konsumsi_kg_kapita"] for r in uji_sim) / 12
        out["konsumsi_kapita"] = {"aktual": d["konsumsi_kg"], "simulasi": ks,
                                  "galat_persen": 100.0 * (ks - d["konsumsi_kg"]) / d["konsumsi_kg"]}
    return out
