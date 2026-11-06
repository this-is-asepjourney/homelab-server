# Blueprint: Dashboard Monitoring MQTT → Grafana (Auto Device Discovery)

## 1. Tujuan
Membuat sistem monitoring berbasis Grafana yang:
- Mengambil data real-time dari MQTT broker lokal (`10.109.25.97:1883`)
- Menampilkan data ke dashboard tanpa perlu edit konfigurasi tiap kali ada device baru
- Device baru cukup "plug and publish" → otomatis muncul di dropdown/dashboard

Ini juga bisa jadi fondasi untuk proyek [[heat-press-iot]] (HPM-55, HPM-340, dll) yang sudah pakai topik `/SysCtrl`, `/Event/Cnt`, `/Event/Handling`, `/Event/Mchn_time`, `/Heatpress`.

---

## 2. Arsitektur Umum

```
[Device IoT/ESP32] --MQTT--> [Mosquitto Broker: 10.109.25.97:1883]
                                        |
                                        v
                              [Telegraf: mqtt_consumer]
                                        |
                                        v
                              [InfluxDB (time-series DB)]
                                        |
                                        v
                                  [Grafana]
                                        ^
                                        |
                        [Laravel App: Device Registry (opsional)]
                                        |
                                     [MySQL]
```

**Kenapa Telegraf + InfluxDB, bukan langsung Grafana ke MQTT?**
Grafana punya plugin MQTT datasource, tapi terbatas (tidak historis, tidak agregasi, tidak query-friendly). Kombinasi Telegraf → InfluxDB → Grafana adalah pola standar industri untuk data time-series dari sensor/IoT: histori tersimpan, bisa query per rentang waktu, retensi data bisa diatur, dan Grafana templating-nya jauh lebih powerful.

---

## 3. Komponen & Peran

| Komponen | Peran | Catatan |
|---|---|---|
| Mosquitto | Broker MQTT | Sudah jalan di `10.109.25.97:1883` |
| Telegraf | Subscriber MQTT → penulis ke InfluxDB | Parsing JSON payload otomatis |
| InfluxDB v2 | Database time-series | Menyimpan semua metric dengan tag (mac, model, dll) |
| Grafana | Visualisasi & dashboard | Template variable untuk device list otomatis |
| Laravel + MySQL (opsional) | Device registry / friendly name | Supaya dashboard tampil "Mesin Press Line 3" bukan cuma MAC address |

---

## 4. Kunci "Auto Menampilkan Device Baru"

Ini bagian paling penting. Triknya **bukan** mendaftarkan device satu-satu di config, tapi:

### a. Subscribe topik dengan wildcard
Telegraf subscribe ke pola topik, bukan topik spesifik per device:
```
+/SysCtrl
+/Event/Cnt
+/Event/Handling
+/Event/Mchn_time
+/Heatpress
```
Atau kalau struktur topik kamu `IOT/<MAC>/SysCtrl`, subscribe `IOT/+/SysCtrl`.

### b. Ekstrak identitas device jadi TAG, bukan bagian dari nama measurement
Field seperti `IOT_MAC`, `MAC`, `MCID`, `IOT_MODEL` harus di-set sebagai **tag** InfluxDB (bukan field biasa). InfluxDB otomatis membuat "seri data" baru tiap ada tag value baru — tidak perlu restart atau config ulang.

### c. Grafana Template Variable berbasis query
Buat variable `device` di dashboard dengan query:
```sql
SHOW TAG VALUES FROM "heatpress" WITH KEY = "mac"
```
(atau versi Flux untuk InfluxDB v2). Dropdown ini otomatis refresh dan menampilkan MAC/device baru begitu ada data masuk — **inilah mekanisme "otomatis muncul" yang kamu mau.**

### d. (Opsional) Friendly name via Laravel + MySQL
Tag MAC address kurang enak dibaca. Solusi:
1. Buat tabel `devices` di MySQL (mac, model, nama_mesin, lokasi, line)
2. Buat halaman admin sederhana di Laravel untuk daftarkan device baru (mapping MAC → nama)
3. Di Grafana, gunakan **MySQL sebagai datasource kedua**, join manual lewat panel "Table" atau pakai Grafana's mixed datasource, atau lookup via Telegraf `processors.enum`/`lookup` sebelum masuk InfluxDB.

Kalau device belum didaftarkan di Laravel, dashboard tetap tampilkan data pakai MAC address apa adanya (fallback), jadi tidak ada device yang "hilang" hanya karena belum diberi nama.

---

## 5. Contoh Konfigurasi Telegraf

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://10.109.25.97:1883"]
  topics = [
    "+/SysCtrl",
    "+/Event/Cnt",
    "+/Event/Handling",
    "+/Event/Mchn_time",
    "+/Heatpress",
  ]
  data_format = "json"
  json_string_fields = ["MAC", "IOT_MAC", "MCID", "IOT_MODEL"]
  tag_keys = ["MAC", "IOT_MAC", "MCID"]

[[outputs.influxdb_v2]]
  urls = ["http://localhost:8086"]
  token = "$INFLUX_TOKEN"
  organization = "myorg"
  bucket = "iot_mqtt"
```

Catatan: karena payload topikmu berbeda-beda struktur (`/SysCtrl` vs `/Event/Cnt` vs `/Heatpress`), sebaiknya pakai **beberapa blok `[[inputs.mqtt_consumer]]`** — satu per grup topik dengan `name_override` berbeda, supaya measurement di InfluxDB terpisah rapi (mis. `sysctrl`, `event_cnt`, `machine_time`, `heatpress`).

---

## 6. Struktur Data di InfluxDB (Skema Measurement)

| Measurement | Tags | Fields |
|---|---|---|
| `sysctrl` | mac, model, mcid | sts, ver |
| `event_cnt` | mac, process_id | data, cur_cycle, sum_cycle |
| `event_handling` | mac, process_id | handling_time |
| `machine_time` | mac | pow_time, moto_time, act_time, sum_sti |
| `heatpress` | mac | pv (temp aktual), sv (temp setpoint) |

Ini selaras dengan topik yang sudah kamu tetapkan di project heat press (`/SysCtrl`, `/Event/Cnt`, `/Event/Handling`, `/Event/Mchn_time`, `/Heatpress`).

---

## 7. Struktur Dashboard Grafana

1. **Variable**: `$device` (query dari tag `mac`, multi-select opsional)
2. **Panel Status** — Stat panel: online/offline berdasarkan `sysctrl` heartbeat terakhir (pakai threshold "last seen > 90 detik = offline")
3. **Panel Temperature** — Time series dari `heatpress.pv` vs `heatpress.sv`, filter `WHERE mac = $device`
4. **Panel Counter/Output** — Time series atau Bar gauge dari `event_cnt.cur_cycle` / `sum_cycle`
5. **Panel Machine Time** — Time series `moto_time`, `act_time`
6. **Table Ringkasan Semua Device** — 1 tabel menampilkan semua device (tanpa filter `$device`), kolom: nama/MAC, status, temp terakhir, cycle terakhir → ini panel yang otomatis nambah baris kalau ada device baru publish data

---

## 8. Alur Penambahan Device Baru (End State)

1. Device baru di-flash firmware, MAC address unik otomatis ada di payload
2. Device connect ke `10.109.25.97:1883`, publish ke topik yang sudah didefinisikan
3. Telegraf (subscribe wildcard) langsung tangkap data, InfluxDB otomatis buat seri baru
4. Grafana variable `$device` otomatis include MAC baru di dropdown
5. (Opsional) Kamu buka halaman Laravel admin, daftarkan MAC → nama mesin biar enak dibaca

**Tidak ada langkah "edit config Telegraf/Grafana" untuk device baru** — itu inti dari desain wildcard + tag-based ini.

---

## 9. Rekomendasi Urutan Implementasi

1. Install Telegraf + InfluxDB v2 di server yang sama/dekat broker
2. Konfigurasi 1 blok `mqtt_consumer` dulu untuk topik `/SysCtrl` saja → validasi data masuk ke InfluxDB
3. Tambah blok untuk topik lain satu per satu
4. Setup Grafana datasource ke InfluxDB
5. Buat dashboard dasar (1 device dulu, hardcode filter) → pastikan panel benar
6. Ganti filter jadi `$device` template variable → tes dengan 2+ device
7. (Opsional, belakangan) Bangun Laravel device registry untuk friendly name

---

## 10. Yang Perlu Dipastikan/Diputuskan
- InfluxDB v1 (query language: InfluxQL) atau v2 (Flux)? — pengaruh ke syntax query Grafana
- Server untuk Telegraf+InfluxDB+Grafana: taruh di server mana? (bisa 1 server yang sama)
- Apakah perlu retensi data jangka panjang (berapa bulan/tahun) untuk kapasitas storage
- Apakah device registry (Laravel+MySQL) mau dibangun sekarang atau nanti (dashboard tetap jalan tanpa ini)
