import os

from flask import Flask, jsonify, render_template, request

import model

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

app = Flask(__name__, template_folder=os.path.join(BASE, "templates"))


def _float(d, k, default):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    data = model.load_data(DATA_DIR)
    est = model.estimasi(data, max(t for t, _, _ in data["bulanan"]))
    return jsonify({
        "produksi_tahunan": model.produksi_tahunan(data["bulanan"]),
        "tahunan": data["tahunan"],
        "estimasi": {k: est[k] for k in ("r_p", "r_k", "r_q", "share")},
    })


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(silent=True) or {}
    data = model.load_data(DATA_DIR)
    tahun_akhir_data = max(t for t, _, _ in data["bulanan"])
    est = model.estimasi(data, tahun_akhir_data)

    horizon = int(min(max(_float(body, "horizon", 10), 1), 30))
    metode = body.get("metode", "euler")
    metode = metode if metode in ("euler", "rk4") else "euler"
    sub = int(min(max(_float(body, "sub", 1), 1), 30))
    impor = _float(body, "impor", 0.0)

    # skenario: penyesuaian (poin persen per tahun) terhadap laju hasil estimasi
    p = dict(est)
    p.update(model.parameter_awal(est, tahun_akhir_data + 1))
    p.update(
        r_p=est["r_p"] + _float(body, "delta_pop", 0.0) / 100,
        r_k=est["r_k"] + _float(body, "delta_kons", 0.0) / 100,
        r_q=est["r_q"] + _float(body, "delta_prod", 0.0) / 100,
        impor=impor,
        S0=_float(body, "S0", 0.0),
    )
    n = horizon * 12
    bulanan = model.simulasi(p, tahun_akhir_data + 1, n, metode, sub)
    lain = "rk4" if metode == "euler" else "euler"
    pembanding = model.simulasi(p, tahun_akhir_data + 1, n, lain, sub)
    selisih = max(abs(a["stok_ton"] - b["stok_ton"]) for a, b in zip(bulanan, pembanding))

    return jsonify({
        "tahunan": model.ringkas_tahunan(bulanan),
        "metode": metode,
        "estimasi": {k: p[k] for k in ("r_p", "r_k", "r_q")},
        "perbandingan_solver": {"metode_lain": lain, "selisih_stok_maks_ton": selisih},
        "validasi": model.validasi(data, impor, metode, sub),
    })


if __name__ == "__main__":
    app.run(debug=True)
