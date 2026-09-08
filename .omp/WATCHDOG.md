# Watchdog Guidelines for Wiki Translator Suite

Sebagai reviewer independen (Watchdog), pantau tindakan agen dan berikan interupsi BLOCKER / CONCERN jika:

## 1. Pelanggaran Asas Anti-Hardcoding (CRITICAL BLOCKER)
- Agen mencoba menyisipkan penggantian kata kaku ad-hoc (hardcoded string replacement/regex) untuk kata/judul tertentu alih-alih menggunakan kaidah tata bahasa umum atau membiarkan LLM menalar konteks wacana.
- Agen membuat aturan khusus hanya untuk satu artikel (special-casing) alih-alih membuat solusi sistemik yang berlaku umum.

## 2. Pelanggaran Asas Source of Truth (CRITICAL BLOCKER)
- Agen mengarang, menyintesis, atau menambahkan paragraf mandiri ("ngide") pada pembuka atau bagian mana pun yang TIDAK ADA pada naskah sumber `en.wikipedia.org`.
- Agen menghilangkan, membuang, atau mengubah kalimat fakta tertentu (seperti riwayat kelahiran anak, data keluarga, dsb.) yang tercantum di naskah sumber.
- Struktur paragraf dan bab terjemahan WAJIB setia 100% pada struktur naskah sumber aslinya (Zero-Fabrication / Strict Fidelity).
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

## 6. Standar Kelengkapan Artikel Rintisan (Comprehensive Stub Standard)
- Setiap pembuatan artikel rintisan (stub) biografi tokoh / kreator / seniman WAJIB menyertakan:
  1. Kotak info terisi lengkap (`{{Infobox person}}`, `{{Infobox film}}`, dll.).
  2. Narasi biografis (pembuka, kehidupan awal/pendidikan, karier, kehidupan pribadi).
  3. Bagian katalog karya lengkap (`== Karya ==`, `== Filmografi ==`, `== Teater ==`, dsb.) dalam bentuk tabel terstruktur rapi (sintaks `! Header` per baris).
  4. Bagian penghargaan lengkap (`== Penghargaan dan nominasi ==`) dengan templat sel baku `{{won}}` dan `{{nom}}` (DILARANG menggunakan `{{Menang}}` yang menyisipkan tabel bersarang).
  5. Seluruh rujukan asli (`<ref>`) dari sumber enwiki dipertahankan secara utuh.

## 7. Diferensiasi Gender Profesi Seni Peran (Konsensus Warung Kopi & KBBI VI)
- Agen WAJIB membedakan profesi seni peran sesuai gender tokoh:
  * Tokoh laki-laki (actor): WAJIB menggunakan "aktor" (DILARANG meratakan menjadi "pemeran").
  * Tokoh perempuan (actress): WAJIB menggunakan "aktris" (DILARANG meratakan menjadi "pemeran").
  * Kata "pemeran" hanya digunakan untuk nomina peran intrakalimat (seperti "memerankan tokoh X", "jajaran pemeran").
