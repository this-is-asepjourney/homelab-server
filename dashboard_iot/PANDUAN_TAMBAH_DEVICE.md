# Panduan Menambahkan Device Baru ke Dashboard

Dokumen ini menjelaskan langkah-langkah yang diperlukan untuk menambahkan perangkat (device) IoT baru agar datanya dapat masuk ke dalam sistem dan terdisplay di Grafana.

Karena arsitektur sistem ini sangat modular, penambahan device baru seringkali **tidak memerlukan perubahan kode pada server** (Telegraf/Prometheus) jika device tersebut menggunakan format dan topik MQTT yang sama dengan device-device sebelumnya. 

Berikut adalah panduan langkah demi langkahnya:

## 1. Konfigurasi pada Sisi Device IoT (Misal: ESP32/NodeMCU)

Pastikan program pada device baru Anda dikonfigurasi untuk terhubung dan mengirimkan data dengan standar yang sesuai dengan sistem ini:

- **Alamat MQTT Broker**: Arahkan *publisher* device ke IP broker MQTT eksisting (saat ini `10.109.25.97` pada port `1883`).
- **Pola Topik MQTT**: Sistem saat ini (via Telegraf) menangkap topik dengan format `<ID_DEVICE_ATAU_MAC>/<Topik_Spesifik>`. Pastikan Anda mem-*publish* data ke topik berikut agar otomatis tertangkap oleh sistem:
  - `<MAC>/SysCtrl`
  - `<MAC>/Event/Cnt`
  - `<MAC>/Event/Handling`
  - `<MAC>/Event/Mchn_time`
  - `<MAC>/Heatpress`
  
  *(Catatan: Ganti `<MAC>` dengan identifier unik device Anda, misalnya MAC address `AA:BB:CC:DD:EE:FF` atau nama spesifik `Mesin-02`).*

- **Format Payload JSON**: Pastikan payload yang dikirim berbentuk JSON dan memiliki key yang diharapkan (seperti `MAC`, `MCID`, `STS`, `VER`). 
  Contoh payload JSON yang dikirimkan ke topik `Mesin-02/SysCtrl`:
  ```json
  {
    "MAC": "Mesin-02",
    "MCID": "Heatpress-Gedung-B",
    "model": "HPM-55",
    "STS": "ON",
    "VER": "1.0.0"
  }
  ```

## 2. Pembaruan pada Telegraf (Jika Diperlukan)

**Anda TIDAK PERLU mengubah konfigurasi Telegraf** jika device baru Anda:
- Menggunakan pola topik MQTT yang sudah ada (karena Telegraf menggunakan *wildcard* `+` seperti `+/SysCtrl`, yang akan otomatis menangkap device dengan prefix nama apapun).
- Menggunakan parameter/key JSON yang sama dengan yang sudah ada.

**Kapan Anda harus mengedit `telegraf/telegraf.conf`?**
Jika device baru Anda mengirimkan **nilai/parameter JSON baru** atau Anda membuat **Topik MQTT baru** yang belum disubscribe.
1. Buka file `telegraf/telegraf.conf`.
2. Cari bagian `[[inputs.mqtt_consumer]]` yang relevan atau buat blok baru.
3. Tambahkan key JSON baru tersebut ke dalam list array `json_string_fields` dan/atau `tag_keys`.
   - *Catatan: Masukkan ke `tag_keys` jika data tersebut merupakan "label/kategori" (seperti MAC, nama mesin). Nilai bacaan sensor atau angka dinamis tidak perlu dimasukkan ke `tag_keys`.*
4. Simpan file, lalu restart container Telegraf agar konfigurasi baru terbaca:
   ```bash
   docker-compose restart telegraf
   ```

## 3. Pembaruan pada Prometheus

**Tidak ada perubahan yang diperlukan pada sisi Prometheus.**
Prometheus secara otomatis akan menarik (*scrape*) semua metrik device baru yang sudah diekspos oleh Telegraf setiap 5 detik.

## 4. Menampilkan Data di Grafana

Setelah device menyala dan berhasil mem-*publish* data, langkah terakhir adalah menampilkannya di dashboard Grafana:

1. **Buka Grafana**: 
   - Jika menggunakan **Grafana Eksisting Homelab**: Akses `http://<IP_SERVER>:3001` (misal `http://100.106.63.90:3001` atau `http://192.168.25.101:3001`).
   - Jika menggunakan **Dedicated IoT Grafana**: Akses langsung di `http://localhost:3003` atau tertanam di Web Dashboard `http://localhost:8088/grafana/`.
2. **Cek Ketersediaan Data (Explore)**: Masuk ke menu **Explore** (ikon kompas di menu bar samping). Gunakan kueri untuk memastikan data device baru sudah masuk. Contohnya, cari nama metrik: `sysctrl` atau `sysctrl_STS`. Anda bisa mengecek pada kolom *Label Filters* apakah `mac` atau `mcid` dari device baru Anda sudah terdeteksi.
3. **Tampilkan ke Dashboard**:
   - Jika dashboard Anda sudah menggunakan **Variabel Dashboard** (menu *dropdown* di atas dashboard untuk memilih device/MAC), device baru Anda **akan otomatis muncul di *dropdown* tersebut** (jika query variabel dibuat dinamis mengambil semua mac address).
   - Jika tidak menggunakan variabel dinamis atau Anda ingin membuat grafik khusus device tersebut:
     - Buka Dashboard Anda.
     - Klik **Add panel** (Tambah panel baru).
     - Pilih *Data Source* **Prometheus**.
     - Masukkan *Query* PromQL yang melakukan filter spesifik untuk device Anda, contohnya:
       ```promql
       sysctrl_STS{mac="Mesin-02"}
       ```
     - Sesuaikan model visualisasi (Time series chart, Gauge, Stat, dll.) di tab sebelah kanan layar.
     - Klik **Apply** dan simpan (Save) perubahan dashboard Anda.
