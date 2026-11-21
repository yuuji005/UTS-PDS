"""Menyiapkan data model dari berkas mentah (BPS Jabar, Open Data, konsumsi pangan)."""
import csv, glob, math, re, sys, collections

PROD_DIR = "/mnt/user-data/uploads"
POP_TXT = "/tmp/bps_in/pop.txt"
KONS_CSV = "/tmp/kons_in/k.csv"
OUT = "/home/claude/simdin-beras/data"

# 1) produksi beras bulanan provinsi (ton)
bulan = []
for f in sorted(glob.glob(f"{PROD_DIR}/*Produksi_Beras_Kabupaten_Kota_menurut_Bulan*_20??.csv")):
    tahun = int(re.search(r"_(20\d\d)\.csv$", f).group(1))
    for r in csv.reader(open(f, encoding="utf-8-sig")):
        if r and r[0].strip() == "Jawa Barat Province":
            vals = [float(x) for x in r[1:13]]
            assert abs(sum(vals) - float(r[13])) < 1.0, (tahun, sum(vals), r[13])
            for m, v in enumerate(vals, 1):
                bulan.append((tahun, m, v))
with open(f"{OUT}/produksi_bulanan.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["tahun", "bulan", "produksi_beras_ton"])
    w.writerows(bulan)

# 2) populasi kab/kota 2020 & 2025 (ribu) dari BPS
pop = {}
lines = open(POP_TXT, encoding="utf-8").read().splitlines()
for ln in lines[893:930]:
    m = re.match(r"^(Kabupaten|Kota) (.+?) ([\d ]+,\d+) ([\d ]+,\d+) ([\d ]+,\d+) ([\d ]+,\d+)$", ln)
    if m:
        f = lambda s: float(s.replace(" ", "").replace(",", "."))
        nama = m.group(2) if m.group(1) == "Kabupaten" else "Kota " + m.group(2)
        pop[nama] = (f(m.group(3)), f(m.group(4)))
prov = re.search(r"^Provinsi Jawa Barat ([\d ]+,\d+) ([\d ]+,\d+)", "\n".join(lines[893:960]), re.M)
p20, p25 = (float(prov.group(i).replace(" ", "").replace(",", ".")) * 1000 for i in (1, 2))

def pop_wil(nama, t):
    a, b = pop[nama]
    return a * (b / a) ** ((t - 2020) / 5)

# 3) konsumsi beras per kapita (kg/kapita/tahun), rata-rata tertimbang populasi
kons = collections.defaultdict(dict)
for r in csv.DictReader(open(KONS_CSV, encoding="utf-8-sig")):
    if not r.get("Tahun") or r["Provinsi"].strip().lower() != "jawa barat":
        continue
    if r["Komoditas"].strip().lower() != "beras":
        continue
    nama = r["Kabupaten_Kota"].strip()
    if nama not in pop:       # buang baris salah wilayah (mis. Kota Adm. Jakarta Utara)
        continue
    kons[int(r["Tahun"])][nama] = float(r["Konsumsi_Pangan"])

tahunan = []
for t in range(2020, 2026):
    populasi = p20 * (p25 / p20) ** ((t - 2020) / 5)
    if t in kons:
        w = {n: pop_wil(n, t) for n in kons[t]}
        k = sum(w[n] * kons[t][n] for n in w) / sum(w.values())
        n_wil = len(kons[t])
    else:
        k, n_wil = "", 0
    tahunan.append((t, round(populasi), k if k == "" else round(k, 3), n_wil))
with open(f"{OUT}/data_tahunan.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["tahun", "populasi", "konsumsi_beras_kg_kapita", "n_wilayah"])
    w.writerows(tahunan)
print(len(bulan), "baris bulanan"); print(*tahunan, sep="\n")
print("wilayah tak cocok:", {t: sorted(set(pop) - set(kons[t])) for t in kons})
