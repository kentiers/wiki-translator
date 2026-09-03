# Wiki Translator Suite

**Wiki Translator Suite** adalah kakas penerjemah artikel semi-otomatis berstandar ensiklopedia (**Grade A++**) dari Wikipedia bahasa Inggris (`en.wikipedia.org`) ke Wikipedia bahasa Indonesia (`id.wikipedia.org`).

Sistem ini dirancang khusus untuk menghasilkan terjemahan bermutu tinggi yang memenuhi kaidah ensiklopedis: bahasa Indonesia alami dan bernas (KBBI VI, EYD V), sintaks wikitext yang presisi, perlindungan integritas rujukan, penyesuaian templat lintas-wiki, hingga alur kerja penerbitan terstruktur langsung ke ruang nama pengguna (bak pasir).

---

## Daftar Isi

1. [Fitur-Fitur Utama](#fitur-fitur-utama)
2. [Arsitektur & Komponen Sistem](#arsitektur--komponen-sistem)
3. [Kebutuhan Sistem & Instalasi](#kebutuhan-sistem--instalasi)
4. [Konfigurasi & Variabel Lingkungan](#konfigurasi--variabel-lingkungan)
5. [Cara Menjalankan](#cara-menjalankan)
6. [Opsi & Argumen CLI](#opsi--argumen-cli)
7. [Panduan Mode Review Interaktif](#panduan-mode-review-interaktif)
8. [Pengujian (Testing)](#pengujian-testing)

---

## Fitur-Fitur Utama

### 1. Anti-AI-Slop Linter & Rekonstruksi Sintaksis Alami (KBBI VI, EYD V)
Mencegah terjemahan berbau mesin (*AI slop*), kalk gramatikal (*grammatical calque*), dan frasa kaku yang kerap dihasilkan model bahasa besar (LLM).
- **Deteksi Kalk & Frasa Mesin:** Menemukan dan memperbaiki pola seperti:
  - `"yang berbasis di"` $\rightarrow$ `"di [kota/negara]"`, `"berpusat di"`, `"berkantor di"`
  - `"dalam upaya untuk"` $\rightarrow$ `"demi"`, `"untuk"`
  - `"memainkan peran kunci / penting"` $\rightarrow$ `"berperan kunci"`, `"berperan penting"`
  - `"menghasilkan dampak yang signifikan"` $\rightarrow$ `"berdampak besar"`, `"berpengaruh nyata"`
  - `"berfungsi sebagai"` $\rightarrow$ `"menjadi"`, `"berperan sebagai"`
  - `"membuat debutnya"` $\rightarrow$ `"memulai debut"`, `"tampil perdana"`
  - `"merupakan sebuah / adalah sebuah"` $\rightarrow$ `"merupakan [nomina]"`, `"adalah [nomina]"`
  - Relatif tidak baku `"di mana"` $\rightarrow$ `"tempat"`, `"saat"`, `"ketika"`, `"yang"`
- **Penilaian Kelancaran (Naturalness Score):** Menghitung skor kelancaran (0–100) per bagian untuk menjaga standar jurnalisme dan ensiklopedia.
- **Standarisasi Tipografi & Tanggal Rujukan:** Mengonversi tanda petik lengkung/lurus, tanda hubung rentang tahun (*en-dash* `–`), format tanggal rujukan (*access-date* / *archive-date*) ke format baku bahasa Indonesia (contoh: `12 September 2026`).

### 2. Wikitext Syntax Balancer & Missing Template Safeguard
- **Syntax Balancer & Auto-Repair:** Memeriksa dan memperbaiki markup wikitext yang tidak seimbang atau rusak selama proses inferensi LLM:
  - Tautan internal: `[[ ... ]]`
  - Templat & parameter: `{{ ... }}`
  - Tag rujukan: `<ref> ... </ref>`, `<ref name="..." />`
  - Tabel wikitext: `{| ... |}`
  - Tag pemformatan: `'''` (tebal), `''` (miring), `<code>`, `<blockquote>`, `<nowiki>`
- **Missing Template Safeguard:**
  - Memetakan templat standar en.wiki ke id.wiki (misal: `{{Main}}` $\rightarrow$ `{{Utama}}`, `{{See also}}` $\rightarrow$ `{{Lihat pula}}`, `{{Reflist}}` $\rightarrow$ `{{Daftar rujukan}}`, `{{Citation needed}}` $\rightarrow$ `{{Butuh rujukan}}`).
  - Memeriksa ketersediaan templat navigasi (*navbox*) di id.wikipedia.org via Action API dan basis data lokal SQLite (`.cache/wiki_templates_cache.db`).
  - Mengamankan templat asing yang belum ada di Wikipedia Indonesia ke dalam komentar HTML aman:
    ```html
    <!-- Templat belum tersedia di id.wiki: {{Navbox_Name|...}} -->
    ```

### 3. Pemetaan Parameter Infobox Konservatif & Konversi Unit/Mata Uang
- **Pemetaan Infobox Konservatif:** Menerjemahkan parameter infobox umum (seperti `Infobox film`, `Infobox person`, `Infobox television`, dll.) hanya jika padanannya di Wikipedia bahasa Indonesia sudah mapan dan terverifikasi. Parameter yang tidak dikenal dipertahankan secara utuh agar infobox tidak rusak (*fail-safe*).
- **Konversi Mata Uang:**
  - `$50 million` / `$50M` $\rightarrow$ `US$50 juta`
  - `$50 billion` / `$50B` $\rightarrow$ `US$50 miliar`
  - `$50 thousand` / `$50K` $\rightarrow$ `US$50 ribu`
  - `£10 million` $\rightarrow$ `£10 juta`
  - `€5 million` $\rightarrow$ `€5 juta`
  - `¥100 billion` $\rightarrow$ `¥100 miliar`
- **Konversi Satuan Ukuran:**
  - `50 miles` / `50 mi` $\rightarrow$ `50 mil`
  - `50 feet` / `50 ft` $\rightarrow$ `50 kaki`
  - `50 inches` / `50 in` $\rightarrow$ `50 inci`
  - `50 pounds` / `50 lbs` $\rightarrow$ `50 pon`
  - `50 square miles` $\rightarrow$ `50 mil persegi`
  - Perlindungan ketat agar tautan, nama berkas, tag `<ref>`, dan blok kode tidak diubah secara keliru.

### 4. Pratinjau Visual HTML Luring (Vector 2022)
- Mengompilasi wikitext hasil terjemahan langsung ke berkas HTML mandiri di folder keluaran.
- Meniru tata letak visual tema **Vector 2022** Wikipedia bahasa Indonesia (font Libertine/Sans-serif, kotak info/infobox bergaya kartu modern, banner peringatan draf, dan daftar referensi dua kolom).
- Dapat langsung dibuka di peramban bawaan sistem tanpa memerlukan instalasi server web lokal.

### 5. Generator Atribusi CC-BY-SA Halaman Pembicaraan
- Menghasilkan wikitext kepatuhan lisensi resmi sesuai *Wikimedia Foundation Terms of Use*:
  ```wikitext
  {{Diterjemahkan dari|en|Judul_Sumber|version=123456789}}
  ```
- Mengintegrasikan banner ProyekWiki terkait secara otomatis sesuai topik artikel:
  - `film` / `cinema` $\rightarrow$ `{{ProyekWiki Film}}`
  - `tv_series` / `television` $\rightarrow$ `{{ProyekWiki Televisi}}`
  - `computing_science` $\rightarrow$ `{{ProyekWiki Komputasi}}` & `{{ProyekWiki Sains}}`
  - `physics_mathematics` $\rightarrow$ `{{ProyekWiki Fisika}}`, `{{ProyekWiki Matematika}}`, & `{{ProyekWiki Sains}}`
  - `medical_biology` $\rightarrow$ `{{ProyekWiki Biologi}}`, `{{ProyekWiki Kedokteran}}`, & `{{ProyekWiki Sains}}`
  - `history_social` $\rightarrow$ `{{ProyekWiki Sejarah}}`
- Menyertakan catatan audit penerjemahan bertanda waktu (*timestamp* UTC).

### 6. Penerbitan Terstruktur ke Bak Pasir Pengguna
Menerbitkan artikel draf dan atribusi pembicaraan ke hierarki ruang nama pengguna yang rapi:
- **Halaman Draf Utama:**
  `Pengguna:<Akun>/Bak_pasir/<project_slug>/<YYYY-MM>/<Judul_Artikel>`
  *(Bawaan: `Pengguna:<Akun>/Bak_pasir/Draf/YYYY-MM/<Judul_Artikel>`)*
- **Halaman Pembicaraan Draf:**
  `Pembicaraan_Pengguna:<Akun>/Bak_pasir/<project_slug>/<YYYY-MM>/<Judul_Artikel>`
- Menggunakan protokol MediaWiki Action API berbasis *Bot Password* dengan penanganan *CSRF login token* yang aman.

### 7. Semantic Cache & Kompresi Token Rujukan
- **Semantic SQLite Cache (`.cache/wiki_translation_cache.db`):** Menyimpan pasangan terjemahan berdasarkan *hash* teks sumber. Menghemat pemanggilan API jika menerjemahkan ulang atau melanjutkan sesi sebelumnya.

### 8. Perangkat Ekosistem Ensiklopedia Lengkap (Ecosystem Tools)
Memaksimalkan keterhubungan, penemuan, dan kelengkapan ensiklopedia id.wikipedia:
- **Generator Pengalihan (Redirect Generator):**
  - Secara otomatis menghasilkan wikitext `#ALIH [[...]]` beserta templat pengalihan resmi (misal: `{{Pengalihan dari nama bahasa Inggris}}`, `{{Pengalihan dari tanda baca lain}}`, `{{Pengalihan tanpa pembeda}}`).
  - Disimpan ke `output/redirects/<Judul>.wikitext`.
- **Generator Rintisan Berkualitas Tinggi (Stub Generator - WP:KELAYAKAN & KPC A1):**
  - Memindai tag pranala merah `{{ill|...}}` bernilai tinggi dan merumuskan rintisan 2–3 paragraf dalam bahasa Indonesia alami.
  - Disimpan ke `output/stubs/<Judul>.wikitext`.
- **Generator & Konverter Kotak Navigasi (Navbox Generator):**
  - Mengambil templat navigasi dari en.wikipedia dan mengonversinya ke sintaks `{{Kotak navigasi}}` id.wikipedia.
  - Disimpan ke `output/templates/<NamaTemplat>.wikitext`.
- **Auditor Dokumentasi Templat (Template Doc Auditor):**
  - Memeriksa ketersediaan subhalaman dokumentasi `Templat:<Nama>/doc` di id.wikipedia dan menyusun dokumentasi baku.
  - Disimpan ke `output/templates/<NamaTemplat>_doc.wikitext`.
- **Kurator Kategori (Category Curator - WP:PEDKAT):**
  - Mengaudit kategori artikel terhadap pedoman WP:PEDKAT (mencegah kategori sebatang kara).

### 9. Fitur Produksi Tambahan (Batch, Media, Arsip, & Memori Bersama)
- **Batch Runner Otomatis (`--batch`):**
  - Menerjemahkan antrean artikel dari berkas teks secara berurutan dengan *rate-limit pacing* otomatis (jeda default 3 detik).
  - Menghasilkan ringkasan statistik batch: total artikel, berhasil, gagal, token yang dihemat, dan waktu eksekusi.
- **Media Manager & Fair Use Rationale (`--check-media` & `--upload-media`):**
  - Mengaudit berkas gambar/poster di kotak info (`| image = ...`) dan pranala berkas (`[[File:...]]`).
  - Memeriksa ketersediaan berkas di Wikimedia Commons dan id.wikipedia.org.
  - Jika berkas merupakan materi non-bebas lokal di en.wiki (seperti poster film atau sampul album), sistem secara otomatis menghasilkan wikitext alasan penggunaan non-bebas berbahasa Indonesia baku (`{{Alasan penggunaan nonbebas}}` + `{{Poster film}}` / `{{Sampul album}}`).
  - Mendukung pengunduhan berkas dan pengunggahan otomatis ke `id.wikipedia.org` menggunakan *Bot Password*.
- **Normalisasi Metrik-Pertama (Metric-First - WP:GAYA):**
  - Memprioritaskan satuan metrik SI di atas satuan imperial sesuai pedoman gaya Wikipedia bahasa Indonesia (WP:GAYA).
  - Membalikkan pola seperti `100 miles (160 km)` $\rightarrow$ `160 km (100 mil)` dan `5 ft 10 in (178 cm)` $\rightarrow$ `178 cm (5 kaki 10 inci)`.
  - Aktif secara bawaan (*enabled by default*), dapat dimatikan via `--no-metric-first`.
- **Reference Checker & Injeksi Wayback Machine (`--enrich-archives`):**
  - Memindai templat sitasi (`{{cite web}}`, dll.) yang memiliki `url=` namun belum memiliki salinan arsip `archive-url=`.
  - Mengueri Wayback Machine Availability API (timeout 5 detik) dengan caching SQLite lokal (`.cache/wayback_cache.db`).
  - Menginjeksi `|archive-url=... |archive-date=... |url-status=live` secara otomatis untuk melindungi artikel dari tautan mati (*link rot*).
- **Shared Workspace Memory (Konsistensi Terminologi Lintas-Artikel):**
  - Basis data SQLite terpusat (`.cache/workspace_glossary.db`) untuk merekam dan mengingat istilah terjemahan yang disetujui.
  - Secara otomatis menginjeksikan istilah yang telah disetujui sebelumnya ke dalam glosarium terjemahan interaktif untuk artikel berikutnya dalam topik yang sama.
---

## Arsitektur & Komponen Sistem

```
wiki_translator/
├── cli.py                     # Antarmuka CLI utama, alur kerja interaktif, dan orkestrasi
├── gemini.py                  # Klien LLM (Antigravity & Google AI Studio fallback)
├── prompts.py                 # System instruction Grade A++ & panduan gaya selaras EYD V
├── slop_linter.py             # Anti-AI-Slop Linter & detektor kalk bahasa
├── syntax_balancer.py         # Penyeimbang & pemulihan markup wikitext otomatis
├── template_mapper.py         # Pemetaan templat lintas-wiki & safeguard navbox hilang
├── infobox_mapper.py          # Pemetaan parameter infobox konservatif
├── unit_converter.py          # Lokalisasi mata uang, satuan ukuran, & normalisasi metrik-pertama
├── wiki_client.py             # Klien MediaWiki en.wiki & id.wiki (fetch wikitext & metadata)
├── wiki_link_mapper.py        # Validator & pemeta pranala merah/biru serta kategori
├── glossary_resolver.py       # Resolusi glosarium istilah teknis & eksonim dinamis
├── attribution_generator.py   # Pembuat atribusi CC-BY-SA dan spanduk ProyekWiki
├── html_preview.py            # Generator pratinjau HTML luring tema Vector 2022
├── sandbox_publisher.py       # Modul penerbit draf terstruktur ke bak pasir pengguna
├── redirect_generator.py      # Generator wikitext pengalihan resmi (#ALIH)
├── stub_generator.py          # Generator rintisan kepatuhan WP:KELAYAKAN & KPC A1
├── navbox_generator.py        # Pembuat templat navigasi {{Kotak navigasi}}
├── template_doc_auditor.py    # Auditor & pembuat subhalaman dokumentasi /doc
├── category_curator.py        # Kurator kategori kepatuhan WP:PEDKAT
├── media_manager.py           # Audit gambar/poster, fair use rationale, & pengunggah berkas
├── reference_checker.py       # Pengecek rujukan & injeksi otomatis arsip Wayback Machine
├── shared_memory.py           # Memori terminologi bersama lintas-artikel SQLite
└── batch_runner.py            # Eksekutor batch antrean artikel dengan rate limiting

---

## Kebutuhan Sistem & Instalasi

Proyek ini dikelola menggunakan manajer paket modern **uv** (disarankan) atau lingkungan Python 3.10+.

### Menggunakan `uv` (Direkomendasikan)
1. Pasang `uv` jika belum tersedia:
   ```bash
   # Windows (PowerShell)
   irm https://astral.sh/uv/install.ps1 | iex
   ```
2. Dependensi akan diisolasi dan dijalankan secara otomatis saat memanggil `uv run`.

---

## Konfigurasi & Variabel Lingkungan

Atur variabel lingkungan berikut sesuai kebutuhan:

| Variabel Lingkungan | Wajib? | Keterangan |
|---------------------|:------:|------------|
| `GEMINI_API_KEY` | Opsional* | Kunci API Google AI Studio untuk inferensi LLM. *(Otomatis menjadi fallback jika kredensial internal Antigravity tidak tersedia).* |
| `WIKI_USERNAME` / `MEDIAWIKI_USERNAME` | Opsional | Nama akun bot atau pengguna di `id.wikipedia.org` untuk penerbitan dan pengunggahan berkas. |
| `WIKI_BOT_PASSWORD` / `MEDIAWIKI_BOT_PASSWORD` | Opsional | Kata sandi bot MediaWiki pengguna (*Bot Password*) untuk penerbitan ke bak pasir atau pengunggahan berkas non-bebas ke id.wikipedia.org. |

> **Petunjuk Hak Akses Bot Password di Wikipedia:**
> Buka **Preferensi $\rightarrow$ Kata sandi bot** di akun `id.wikipedia.org` Anda, buat nama bot baru dengan hak akses:
> 1. *Sunting halaman yang ada*
> 2. *Buat, pindahkan, dan sunting halaman baru*
> 3. *Unggah berkas baru* (wajib diaktifkan jika menggunakan fitur `--upload-media`)
> 4. *Unggah, ganti, dan bersihkan berkas*
---

## Cara Menjalankan

Anda dapat menjalankan Wiki Translator melalui *launcher script* atau langsung via CLI.

### 1. Menggunakan Windows Batch Script (`run.bat`)
```cmd
run.bat "Oppenheimer (film)" --topic film --preview
```

### 2. Menggunakan PowerShell Script (`run.ps1`)
```powershell
.\run.ps1 "Quantum computing" --topic computing_science --preview
```

### 3. Menggunakan `uv run`
```bash
uv run python main.py "Interstellar (film)" --topic film --preview
```

---

## Opsi & Argumen CLI

Ringkasan opsi CLI yang paling sering digunakan:

```
uv run python main.py [title] [opsi...]
```

| Opsi / Argumen | Keterangan |
|---|---|
| `title` | Judul artikel en.wikipedia.org (contoh: `"Dune (2021 film)"`, `"Quantum computing"`). Jika dikosongkan, CLI akan meminta judul secara interaktif. |
| `--topic <kategori>` | Memilih glosarium domain spesifik: `film`, `cinema`, `tv_series`, `television`, `entertainment`, `media`, `computing_science`, `physics_mathematics`, `medical_biology`, `history_social`. |
| `--preview` | Langsung membuat dan membuka pratinjau HTML Vector 2022 di peramban bawaan saat proses terjemahan selesai. |
| `--publish-sandbox <Akun>` | Nama pengguna Wikipedia bahasa Indonesia untuk menerbitkan draf artikel dan halaman pembicaraan ke bak pasir pengguna. |
| `--project-slug <folder>` | Nama folder proyek dalam hierarki bak pasir (bawaan: `Draf`). |
| `--sandbox-slug <slug>` | Menimpa struktur slug bak pasir secara penuh (bawaan: `<project-slug>/YYYY-MM`). |
| `--auto-approve` | Menyetujui semua bagian secara otomatis tanpa jeda interaktif per bagian. |
| `--polish` / `--humanize` | Mengaktifkan mode perbaikan 2-pass (*Humanize Polish*) untuk alur kalimat jurnalistik yang lebih luwes. |
| `--output-dir <folder>` | Folder untuk menyimpan berkas wikitext dan HTML (bawaan: `output/`). |
| `--no-cache` | Menonaktifkan pembacaan/penyimpanan ke semantic cache SQLite. |
| `--no-compression` | Menonaktifkan kompresi token tag sitasi/rujukan `<ref>`. |
| `--no-slop-linter` | Menonaktifkan pengecekan Anti-AI-Slop Linter. |
| `--no-syntax-balancer` | Menonaktifkan perbaikan otomatis penyeimbang sintaks wikitext. |
| `--no-template-mapper` | Menonaktifkan pemetaan templat lintas-wiki dan safeguard templat hilang. |
| `--create-stubs` | Menghasilkan rintisan berkualitas tinggi untuk pranala merah bernilai tinggi (`{{ill}}`) ke `output/stubs/`. |
| `--audit-navboxes` | Mengaudit templat navigasi bawah dan menghasilkan draf navigasi & dokumentasi di `output/templates/` untuk templat yang belum ada di id.wiki. |
| `--curate-categories` | Mengaudit kategori artikel terhadap panduan WP:PEDKAT id.wikipedia dan menampilkan laporannya. |
| `--generate-redirects` | Menghasilkan wikitext pengalihan resmi (#ALIH) di `output/redirects/` (bawaan: nonaktif). |
| `--batch <file.txt>` | Menjalankan penerjemahan beruntun dari berkas antrean berisi daftar judul artikel (satu per baris, baris kosong dan komentar `#` diabaikan). |
| `--check-media` | Mengaudit berkas gambar/poster artikel terhadap Wikimedia Commons dan id.wikipedia.org serta membuat alasan penggunaan non-bebas. |
| `--upload-media` | Mengunduh berkas non-bebas dari en.wiki dan mengunggahnya langsung ke id.wikipedia.org dengan wikitext alasan fair-use. |
| `--enrich-archives` | Memindai rujukan web dan menambahkan tautan arsip Wayback Machine (`|archive-url=...`) secara otomatis. |
| `--no-metric-first` | Menonaktifkan penataan metrik-pertama (bawaan: aktif sesuai WP:GAYA). |
### Contoh Penggunaan Nyata

1. **Menerjemahkan artikel film dengan glosarium topik dan pratinjau langsung:**
   ```bash
   uv run python main.py "Parasite (2019 film)" --topic film --preview
   ```

2. **Menerjemahkan dan menerbitkan ke bak pasir proyek tertentu:**
   ```bash
   uv run python main.py "Ada Lovelace" --topic computing_science --publish-sandbox "NamaPengguna" --project-slug "TokohIlmuwan" --preview
   ```
   *Halaman hasil:* `Pengguna:NamaPengguna/Bak_pasir/TokohIlmuwan/2026-09/Ada_Lovelace`

3. **Mode non-interaktif (otomatis penuh):**
   ```bash
   uv run python main.py "Black hole" --topic physics_mathematics --auto-approve --output-dir "dist"
   ```

---

## Panduan Mode Review Interaktif

Pada mode semi-otomatis, CLI menyajikan terjemahan per bagian artikel dan menampilkan menu review interaktif. Gunakan pintasan tombol berikut:

```
[?] Review Section Translation:
  [A] Approve & Continue
  [D] Diff / Side-by-side comparison (Source EN vs Draft ID)
  [V] View in Browser (HTML Preview)
  [F] Auto-fix Slop & Syntax Balancer
  [P] Polish / Humanize (Redaktur 2nd Pass)
  [R] Retry / Regenerate
  [E] Add Context Note / Glossary & Retry
  [S] Skip / Keep Original Wikitext
  [Q] Quit & Save Draft
Select action [A/v/d/f/p/r/e/s/q] (default: A):
```

| Tombol | Aksi | Penjelasan Detail |
|:------:|------|-------------------|
| **`[A]`** | **Approve & Continue** | Menyetujui draf bagian saat ini (opsi default) dan melanjutkan ke bagian berikutnya. Cukup tekan tombol `Enter`. |
| **`[D]`** | **Diff / Comparison** | Menampilkan perbandingan berdampingan (*side-by-side*) antara teks asli en.wiki dan draf terjemahan id.wiki di terminal. |
| **`[V]`** | **View in Browser** | Mengompilasi draf bagian ini ke berkas HTML Vector 2022 dan langsung membukanya di peramban web untuk pengecekan visual. |
| **`[F]`** | **Auto-fix Slop & Syntax** | Menjalankan Anti-AI-Slop Linter auto-fix (menghapus kalk frasa kaku) dan Wikitext Syntax Balancer (menutup tag/kurung kurawal yang timpang), lalu memperbarui draf aktif. |
| **`[P]`** | **Polish / Humanize** | Menjalankan *2nd Pass Redaktur* menggunakan LLM dengan teknik streaming untuk merapikan irama bahasa (*cadence*) agar bernas, elegan, dan lepas dari gaya terjemahan harfiah. |
| **`[R]`** | **Retry / Regenerate** | Mengulang kembali proses terjemahan bagian ini dari awal melalui LLM. |
| **`[E]`** | **Add Note & Retry** | Memasukkan catatan konteks tambahan atau instruksi glosarium khusus secara bebas dari pengguna, lalu menerjemahkan ulang bagian ini dengan mempertimbangkan catatan tersebut. |
| **`[S]`** | **Skip Section** | Melewati bagian ini dan mempertahankan teks sumber asli (wikitext bahasa Inggris). |
| **`[Q]`** | **Quit & Save Draft** | Menghentikan sesi penerjemahan saat ini dan segera menyimpan seluruh bagian yang telah diselesaikan ke berkas keluaran agar progres kerja tidak hilang. |

---

## Pengujian (Testing)

Suite pengujian unit mencakup seluruh komponen inti (atribusi, linter, infobox, konversi unit, sandbox publisher, sintaks balancer, dsb). Jalankan pengujian kapan saja dengan perintah:

```bash
uv run python -m unittest discover tests
```
Semua modul pengujian dirancang mandiri (*self-contained*) dan mendukung simulasi *dry-run* tanpa melakukan suntingan jaringan nyata ke Wikipedia.
