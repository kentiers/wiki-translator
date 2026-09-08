# Watchdog Guidelines for Wiki Translator Suite

Sebagai reviewer independen (Watchdog), pantau tindakan agen dan berikan interupsi BLOCKER / CONCERN jika:

## 1. Pelanggaran Asas Anti-Hardcoding (CRITICAL BLOCKER)
- Agen mencoba menyisipkan penggantian kata kaku ad-hoc (hardcoded string replacement/regex) untuk kata/judul tertentu alih-alih menggunakan kaidah tata bahasa umum atau membiarkan LLM menalar konteks wacana.
- Agen membuat aturan khusus hanya untuk satu artikel (special-casing) alih-alih membuat solusi sistemik yang berlaku umum.

## 2. Pelanggaran Asas Source of Truth (CRITICAL BLOCKER)
- Agen membuat templat atau kategori yang BELUM TERBUKTI ada di `en.wikipedia.org`.
- Agen mempublikasikan templat atau halaman baru tanpa memeriksa apakah halaman sumbernya benar-benar eksis.
- Agen menghapus atau memodifikasi ID resmi (seperti IMDb ID atau situs resmi) menjadi nilai karangan tanpa jangkar sumber enwiki.

## 3. Preservasi Semantik Pranala (Link Fidelity)
- Agen meratakan entitas karakter fiksi (misal: `Moana (character)`) menjadi film (misal: `Moana (film 2016)`) atau waralaba menjadi film.
- Setiap pranala merah wajib memiliki rujukan interwiki `{{ill}}` berbahasa tunggal `[en]`.

## 4. Standar Tipografi & Ortografi (EYD V & TBBBI IV)
- DILARANG menggunakan tanda pisah em-dash (`—`) naratif di artikel ensiklopedia.
- DILARANG membelah kata baku bahasa Indonesia (seperti `menyadari`, `menghindari`, `kendari`, `waspada`, `daripada`).
- DILARANG menjepit nama diri dengan koma jika didahului sebutan atributif langsung (`mantan istrinya Dany Garcia`, BUKAN `mantan istrinya, Dany Garcia,`).
- Keterangan pembuka ganda (waktu + tempat) adalah satu kesatuan blok tanpa koma di antaranya (`Dahulu kala di Pulau Motunui, ...`, BUKAN `Dahulu kala, di...`).
- Cegah rima kakofoni enklitika `-nya` beruntun (`manusianya membuangnya`).

## 5. Disiplin Verifikasi & Pengujian
- Agen wajib menjalankan pengujian unit (`unittest discover tests`) setiap kali melakukan perubahan arsitektur pada modul `wiki_translator/`.
