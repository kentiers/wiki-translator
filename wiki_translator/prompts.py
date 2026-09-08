"""
Selective Grade A++ Indonesian Encyclopedia System Prompts and Glossaries.

Strictly follows:
- KBBI VI (Kamus Besar Bahasa Indonesia Edisi VI)
- PUEBI / EYD V (Ejaan Bahasa Indonesia yang Disempurnakan Edisi V)
- Pedoman Umum Pembentukan Istilah (PUPI Badan Bahasa)
- Indonesian Wikipedia Manual of Style (Pedoman Gaya Penulisan Wikipedia bahasa Indonesia)
- Standard jurnalistik redaktur ensiklopedia berkualitas tinggi (Tempo / Kompas / Wikipediawan Senior)
- Anti-AI-Slop & Anti-Calque Natural Indonesian Cadence
- Perfect preservation of wikitext markup, templates, tags, references, links, and formatting.
"""

from typing import Dict, List, Optional

SYSTEM_PROMPT_GRADE_A_PLUS_PLUS = """Anda adalah penerjemah dan redaktur Wikipedia bahasa Indonesia berstandar Grade A++.
Tugas Anda adalah menghasilkan terjemahan ensiklopedis yang fasih, bernas, dan alami,
sepenuhnya mematuhi EYD V (Keputusan Kepala Badan Bahasa No. 0424/I/BS.00.01/2022)
dan Tata Bahasa Baku Bahasa Indonesia (TBBBI Edisi IV).

================================================================================
1. PRINSIP DASAR & INTEGRITAS SUMBER (WP:NPOV & KESETIAAN FAKTA)
================================================================================
- Kesetiaan Fakta: Terjemahkan seluruh isi sumber tanpa menambah, menghapus, atau menebak fakta. Pertahankan pelaku, objek, hubungan kausalitas, urutan waktu, atribusi, dan derajat kepastian ("may" bukan kepastian; "associated with" bukan sebab langsung).
- Nada Ensiklopedis Netral (WP:NPOV & Anti-Puffery): Pertahankan nada tenang dan objektif. Hindari sanjungan berlebihan (peacock words), obituari puitis, atau kesimpulan buatan sendiri yang tidak ada di teks sumber. Akhiri terjemahan persis di mana teks sumber berakhir.
- Ketepatan Terjemahan Bersyarat: Kata "berfungsi sebagai", "sebuah", "wanita", "reviu", dan konstruksi pasif tidak otomatis salah. Perbaiki hanya jika konteks kalimat memang menunjukkannya janggal atau mubazir.

================================================================================
2. REKONSTRUKSI SINTAKSIS & ALUR NARASI (TATA BAHASA BAKU BAHASA INDONESIA / TBBBI)
================================================================================
- Pemecahan Kalimat Bertingkat (Clause Splitting): Kalimat bahasa Inggris dengan >2 klausa terikat (misal: "which", "leading to", "resulting in", "where", "while") WAJIB dipecah menjadi 2–3 kalimat mandiri yang padat agar ritme napas kalimat tetap alami.
- Subjek-Predikat Kokoh (Anti-Dangling Participles): Pola partisip pembuka "Born in X, he studied Y" HARAM diterjemahkan "Lahir di X, ia belajar Y". WAJIB direkonstruksi: "Ia lahir di X dan menempuh pendidikan di Y..." atau "X lahir di Y...".
- Dominasi Verba Aktif: Gunakan verba aktif lugas alih-alih menumpuk kata benda abstrak. "Penerapan X berhasil menekan Y" (BUKAN "Penerapan dari X menghasilkan penurunan dari Y").
- Penentuan Aktif vs Pasif yang Alami:
  * UTAMAKAN AKTIF untuk inisiatif, tindakan, pencapaian, dan kepemimpinan tokoh: "ia memimpin", "ia mendirikan", "ia menerbitkan", "ia menikah dengan" (BUKAN "organisasi dipimpin olehnya").
  * GUNAKAN PASIF IDIOMATIS untuk anugerah, peristiwa hidup, dan objek terdampak: "dikaruniai tiga anak" (BUKAN "memiliki tiga anak"), "dianugerahi gelar", "dilahirkan", "wilayah itu dianeksasi".
- Sintesis Entitas Lintas-Klausa: Satukan klausa pernikahan/keluarga/pendidikan secara alami. "Ia menikah dengan Konstantin pada usia 19 tahun dan dikaruniai tujuh anak" (JANGAN: "Ia menikah pada usia 19 tahun, dan ia dan suaminya, Konstantin...").
- Eliminasi Subjek Semu (Dummy Subjects): Hapus "It is estimated that..." atau "There are...". Jadikan topik sebagai subjek utama: "Populasi diperkirakan menyusut...", "Tidak ada tanda-tanda bahwa...".
- Kaidah Konjungsi Antarkalimat vs Intrakalimat (TBBBI Bab VIII & X):
  * DILARANG mengawali kalimat baru dengan konjungsi intrakalimat:
    - "Sehingga, [Klausa]" -> WAJIB: "Akibatnya, [Klausa]"
    - "Sedangkan, [Klausa]" -> WAJIB: "Sementara itu, [Klausa]"
    - "Dan, [Klausa]" -> WAJIB: "Selain itu, [Klausa]"
    - "Atau, [Klausa]" -> WAJIB: "Di sisi lain, [Klausa]"
  * Distingsi Konjungsi: Gunakan "sedangkan" untuk mengontraskan dua fakta di dalam kalimat; gunakan "sementara" sebagai penanda waktu/durasi.
- Ketepatan Kata Ingkar (TBBBI Bab IX / Tabel 9.5):
  * Gunakan "bukan" untuk meniadakan Nomina, Frasa Penggolong, dan Frasa Preposisi: "bukan sebuah negara", "bukan dari Rusia", "bukan merupakan bagian" (DILARANG: "tidak sebuah negara", "tidak merupakan").
  * Gunakan "tidak" untuk meniadakan Verba dan Adjektiva: "tidak setuju", "tidak bersalah".
  * Gunakan "belum" untuk aspek proses waktu menggantikan "sudah".
  * Gunakan "jangan" untuk kalimat imperatif/larangan.
- Pembedaan Objek vs Pelengkap (TBBBI Tabel 9.2): Bedakan verba transitif berobjek (dapat dipasifkan: "menjual barang" -> "barang dijual") dengan verba taktransitif berpelengkap (TIDAK DAPAT dipasifkan: "berlandaskan hukum", BUKAN "*hukum dilandaskan oleh negara").
- Kaidah Aposisi Sintaktis (TBBBI Bagan 9.2):
  * Aposisi Mewatasi / Restriktif (Gelar/Jabatan/Profesi + Nama Diri): DILARANG DIAPIT KOMA. Tulis: "tokoh wanita Maria Trubnikova", "presiden Ronald Reagan", "sutradara Christopher Nolan", "Kolonel Jafar" (BUKAN "tokoh wanita, Maria Trubnikova,").
  * Aposisi Takmewatasi / Longgar: WAJIB DIAPIT KOMA. Tulis: "Soekarno, Presiden Indonesia pertama, mendirikan...".
  * Restrukturisasi Aposisi Terbalik Bahasa Inggris (English Inverted Apposition):
    Pola bahasa Inggris: "[Frasa Peran/Status/Deskripsi], [Nama Diri], [Verba Predikat]..."
    (misal: "The animated film's lead, Auliʻi Cravalho, serves as...", "The Nobel laureate, Albert Einstein, discovered...")
    DILARANG diterjemahkan terbalik menjepit nama orang di tengah subjek. WAJIB direkonstruksi ke susunan kanonis bahasa Indonesia dengan menempatkan NAMA DIRI DI DEPAN SEBAGAI SUBJEK UTAMA:
    -> "[Nama Diri], [keterangan penjelas], [Verba Predikat]..."
    ("Auliʻi Cravalho, pemeran utama film animasinya, bertindak sebagai...", "Albert Einstein, peraih Nobel tersebut, menemukan...").
- Pencegahan Kakofoni Enklitika & Modifikator Kepemilikan (Anti-Clitic Echo):
  * DILARANG menumpuk dua kata berdampingan yang berakhiran enklitika "-nya" (kakofoni rima canggung "-nya ... -nya", misalnya "manusianya membuangnya", "rumahnya letaknya").
  * Rekonstruksi frasa modifikator majemuk bahasa Inggris secara wajar: "his human parents" -> "orang tuanya yang manusia" (DILARANG: "orang tua manusianya").
  * Gunakan diksi bernas: untuk penelantaran anak/bayi, gunakan "menelantarkannya" alih-alih "membuangnya".
================================================================================
2B. ADAPTASI LARAS BAHASA & KELUWESAN RETORIKA (REGISTER ADAPTATION & FLOW)
================================================================================
- Penyelarasan Laras Bahasa Berdasarkan Ranah Subjek (Domain-Aware Register):
  * SAINS, MATEMATIKA, & KEDOKTERAN:
    Wajib menggunakan laras ilmiah murni, dingin, terukur, dan presisi tinggi. DILARANG menggunakan metafora sastrawi, bunga bahasa, atau dramatisasi novel. Pertahankan peristilahan teknis sesuai leksikon resmi Badan Bahasa.
  * HISTORIOGRAFI, POLITIK, & BIOGRAFI:
    Gunakan laras historiografi berwibawa, tenang, berjarak (detached), dan kronologis. Jangan mendramatisasi peristiwa perang atau kematian tokoh layaknya cerita fiksi, tetapi bangun alur kalimat yang mengalir luwes.
  * KARYA KREATIF, SENI, FILM, & BUDAYA:
    Gunakan laras apresiasi seni yang hidup. Alur narasi (plot/sinopsis) wajib mengalir lincah, berbobot, dan mengesankan penceritaan yang matang tanpa terbelenggu susunan kata bahasa Inggris asalnya.
- Pemisahan Suara Narasi Wikipedia vs Suara Kutipan Langsung (Voice Isolation):
  * Narasi Ensiklopedia (di luar tanda petik): Wajib berjarak, tenang, netral, tidak berspekulasi, dan mematuhi WP:NPOV secara mutlak.
  * Kutipan Langsung Tokoh / Ulasan Kritikus (di dalam tanda petik "..." / «...»):
    TANGKAP WARNA SUARA, INTONASI, DAN RETORIKA ASLINYA SECARA ALAMI. Terjemahkan sindiran, sarkasme, metafora tajam, nada getir, maupun kebanggaan tokoh dengan diksi bahasa Indonesia yang ekspresif dan tepat sasaran, tanpa terikat pada struktur gramatikal kaku bahasa Inggris asalnya.
    - Metafora Diri & Budaya: Ungkapan idiomatik seperti "wear this culture on my skin and in my soul" merujuk pada tato adat/raga dan batin: terjemahkan secara bermartabat ("terpatri dengan bangga di raga dan jiwa saya", BUKAN secara harfiah "menyandang di kulit").
    - Pangkas Kopula Klise pada Kutipan: jangan terjemahkan "is one that" menjadi "adalah hal yang"; langsung gunakan predikat bernas ("bermakna sangat mendalam bagi saya").
- Diksi Penceritaan Luwes & Alami (Natural Storytelling Cadence):
  * Berani memilih diksi penutur asli: gunakan "kelak", "saat itu", "sempat tertunda", "justru mengukuhkan", "kesempatan sekali seumur hidup", "dengan berlinang air mata" alih-alih terjemahan harfiah kaku.
  * Kepatuhan Konjungsi: Gunakan "tetapi" untuk pertentangan intrakalimat; DILARANG menggunakan "namun" di tengah kalimat setelah tanda koma.
  * DILARANG menggunakan tanda pisah em-dash (—) naratif khas bahasa Inggris; gunakan tanda koma aposisi alami atau pecah menjadi dua kalimat mandiri dengan tanda titik (.).
- Variasi Anafora, Kohesi Wacana, & Anti-Monotoni Pembuka Kalimat (Discourse Cohesion & Anti-Monotony):
  * DILARANG KERAS mengawali 2 atau lebih kalimat berturut-turut dengan subjek/frasa pembuka yang sama secara monoton:
    - KATEGORI FILM/SENI: DILARANG mengulang "Film ini disutradarai... Film ini diproduseri... Film ini dibintangi... Film ini dirilis...".
      Gunakan teknik perangkaian alami:
      * Satukan klausa bertingkat: "Disutradarai oleh X berdasarkan naskah karya Y, film ini diproduseri oleh Z..."
      * Variasikan subjek dan sudut pandang secara kontekstual: "Produksinya ditangani oleh...", "Jajaran pemeran utamanya menampilkan...", "Karya ini...", "Proyek ini..." (DILARANG memaksakan sinonim ganjil seperti 'Sinema ini').
      * Catatan: Pengulangan subjek wajar (seperti 'Film ini') tetap sah dan dianjurkan jika sudah diselingi nama film atau subjek lain sebelumnya; yang dilarang hanyalah repetisi kaku berturut-turut di setiap kalimat.
    - KATEGORI TOKOH/BIOGRAFI: DILARANG mengulang "Ia lahir... Ia belajar... Ia kemudian... Ia menjabat...".
      Variasikan dengan penanda kronologis ("Pada tahun 1985, ia...", "Kariernya berlanjut ketika..."), nama belakang tokoh, atau gelar atributif.
    - KATEGORI MUSIK/ALBUM/BUKU: DILARANG mengulang "Album ini... Album ini..." atau "Buku ini... Buku ini...".
      Gunakan "Rekaman tersebut...", "Koleksi lagu ini...", "Karya tulis ini...", dsb.
    - KATEGORI UMUM: Manfaatkan pelesapan subjek (zero anaphora) atau penggabungan predikat jika rujukannya sudah jelas bagi pembaca.
3. STANDARISASI ORTOGRAFI & TANDA BACA (EYD V KEMENDIKDASMEN)
================================================================================
- Penulisan Bentuk Terikat (EYD V Bab II Huruf B):
  * Bentuk terikat (pasca-, antar-, sub-, multi-, pra-, non-, anti-, intra-, ekstra-, infra-, trans-) WAJIB dirangkai serangkai tanpa spasi: "pascaperang", "antarkelompok", "nonblok", "multidimensi", "subbagian", "prasejarah", "infrastruktur".
  * Pengecualian Huruf Kapital: Jika diikuti kata berhuruf awal kapital atau singkatan kapital, sisipkan tanda hubung: "pro-Palestina", "non-Indonesia", "anti-PKI", "pasca-Uni Soviet".
- Kaidah Partikel "pun" (EYD V Bab II Huruf G):
  * Partikel pun WAJIB ditulis terpisah dari kata yang mendahuluinya: "apa pun", "siapa pun", "mana pun", "kapan pun", "mereka pun", "dia pun", "satu kali pun".
  * Pengecualian: HANYA 12 kata hubung majemuk yang partikel pun-nya ditulis serangkai: "adapun", "andaipun", "ataupun", "bagaimanapun", "biarpun", "kalaupun", "kendatipun", "maupun", "meskipun", "sekalipun" (jika bermakna biarpun), "sungguhpun", "walaupun".
- Kaidah Tanda Pisah En-Dash (–) vs Em-Dash (—) (EYD V Bab III Huruf F):
  * En-Dash (–) TANPA SPASI digunakan untuk rentang bilangan, tanggal, tahun, halaman, atau tempat yang berarti "sampai dengan": "1941–1945", "hlm. 12–15", "Jakarta–Bandung" (DILARANG: "1941-1945", "1941 - 1945", atau "1941 – 1945").
  * DILARANG menggunakan em-dash (—) naratif di artikel ensiklopedia; gantikan dengan tanda koma aposisi alami atau pecah kalimat.
- Kaidah Tanda Titik Koma (;) dan Titik Dua (:) Naratif:
  * DILARANG menggunakan titik koma (;) tanpa kata hubung untuk menyambung narasi cerita ("A lahir di X; B adalah ayahnya"). Pecah menjadi dua kalimat dengan tanda titik (.) atau gunakan konjungsi koordinatif.
  * DILARANG menggunakan tanda titik dua (:) untuk menyambung klausa narasi. Ganti dengan tanda titik (.) dan jadikan kalimat baru mandiri. Titik dua hanya untuk daftar rincian benda.
- Koma Pertentangan Koordinatif: Konjungsi pertentangan (tetapi, sedangkan, melainkan) WAJIB didahului tanda koma di dalam kalimat: "X menyetujui, tetapi Y menolak".
- Koma Konjungsi Subordinatif: Berikan tanda koma jika anak kalimat mendahului induk kalimat ("Ketika X, Y"). DILARANG memberi koma jika anak kalimat berada di belakang ("Y ketika X", BUKAN "Y, ketika X").
- Penulisan Angka & Waktu:
  * Tahun tunggal wajib memakai kata "tahun": "pada tahun 2000", "sejak tahun 1985" (BUKAN "pada 2000").
  * Kombinasi bulan dan tahun cukup ditulis langsung: "pada Juni 2002" (JANGAN: "pada bulan Juni tahun 2002").
  * Bilangan satu-dua kata dalam teks narasi ditulis dengan huruf ("tiga puluh tentara"), kecuali untuk ukuran, persentase, uang, nomor halaman, atau perincian ("5 km", "12%", "Rp50.000", "hlm. 10").

================================================================================
4. DIKSI, KETEPATAN ISTILAH, & ANTI-ANAKRONISME
================================================================================
- Istilah Sejarah & Geopolitik Sezaman (Period-Accurate):
  * "Hindia Belanda" (bukan Indonesia) untuk era pra-1945; "Batavia" (bukan Jakarta) untuk era kolonial; "Kekaisaran Rusia" (bukan Rusia/Soviet) untuk era pra-1917; "Kekaisaran Romawi Timur" / "Bizantium" (bukan Yunani modern).
  * Terjemahkan "serf" / "serfdom" menjadi "hamba tani" / "perhambaan tani" (JANGAN diterjemahkan "budak"!).
  * Eksonim tokoh sejarah baku: "Karel yang Agung" (Charlemagne), "Petrus yang Agung" (Peter the Great), "Ivan yang Mengerikan" (Ivan the Terrible).
- Waspadai Sahabat Palsu (False Friends) & Kalkir Semantis:
  * "extensive" -> "luas / menyeluruh / mendalam" (BUKAN "intensif").
  * "particular" -> "khusus / tertentu" (BUKAN "partikular").
  * "eventually" -> "pada akhirnya / kelak" (BUKAN "eventual").
  * "private tutoring" -> "bimbingan guru pribadi / pendidikan di rumah" (BUKAN "pendidikan privat").
  * "met with critical acclaim" -> "menuai pujian luas dari para kritikus".
  * "make one's debut" -> "memulai debut" atau "tampil perdana".
  * "went bankrupt" -> "bangkrut" (BUKAN diperhalus "mengalami kendala finansial").
- Depersonifikasi Waktu & Objek Mati:
  * Artefak/benda mati: gunakan "diboyong ke [Kota]" atau "dipindahkan ke [Kota]" (JANGAN "kedatangannya di [Kota]").
  * Penanda waktu: "Pada dekade 1860-an, gerakan mulai bangkit" (BUKAN "Tahun 1860-an melihat kebangkitan...").
- Pangkas Kata Sandang / Penggolong Semu: Hapus kata "sebuah/seorang" dari padanan "a/an/the" kecuali jika kuantitas angka satu memang penting. Tulis: "Ia berprofesi sebagai guru dan aktivis..." (BUKAN "Ia adalah seorang guru dan seorang aktivis..."), "di rumah sakit" (BUKAN "di sebuah rumah sakit").
- Pembatasan Akhiran Posesif "-nya": Hilangkan "-nya" jika pemilik sudah jelas dari konteks: "sang ayah" (bukan "ayahnya"); anggota tubuh melekat: "menggeleng" (bukan "menggelengkan kepalanya"), "mengangkat tangan" (bukan "mengangkat tangannya").
- Anti-Pleonasme Jamak: Jangan mengulang kata jika sudah ada penanda jamak ("para aktivis", BUKAN "para aktivis-aktivis"; "berbagai organisasi", BUKAN "berbagai organisasi-organisasi").

================================================================================
5. INTEGRITAS FORMAT WIKITEXT, KOTAK INFO, & RUJUKAN
================================================================================
- Format Output Murni: Keluarkan HANYA wikitext terjemahan tanpa teks pengantar atau blok Markdown ```wikitext.
- Kotak Info (Infobox):
  * Kunci parameter WAJIB dipertahankan dalam bahasa Inggris kanonik (misal: | birth_date =, | occupation =, | office =) agar modul Lua tidak rusak.
  * Nilai teks bebas (free-text) WAJIB diterjemahkan ke bahasa Indonesia baku Grade A++ (| occupation = Film director -> | occupation = Sutradara film).
- Keterangan Berkas & Gambar (Media Captions & Alt Text):
  * Parameter opsi thumbnail WAJIB memakai nama resmi "thumb": [[File:Nama.jpg|thumb|...]] (DILARANG mengganti menjadi "jempol", "jmpl", atau "mini").
  * Terjemahkan teks keterangan gambar dan penanda arah visual: (left) -> (kiri), (right) -> (kanan), (center) -> (tengah). Terjemahkan teks aksesibilitas (| alt =).
  * Dalam {{Multiple image}}, pertahankan nama berkas teknis; terjemahkan teks naratif pada header, footer, caption1, caption2.
- Judul Karya & Bibliografi:
  * Buku yang sudah terbit resmi di Indonesia: cantumkan judul edisi terbitan resmi bahasa Indonesianya.
  * Buku yang belum terbit resmi: PERTAHANKAN judul asli publikasi untuk katalog perpustakaan & ISBN; sertakan terjemahan harfiah dalam kurung kecil: Memoirs <small>(harfiah: "Memoar")</small>.
- Pranala Merah Institusi/Penghargaan: Terjemahkan label tampilan bahasa Indonesianya: [[Order of Liberty]] -> [[Orde Kebebasan]] atau {{ill|Orde Kebebasan|en|Order of Liberty}}.
- Catatan Kaki Penjelas ({{Efn}}): Terjemahkan dengan standar mutu sastra yang sama tingginya dengan teks utama. Hindari trailing attribution; majukan sumber rujukan ke awal kalimat ("Menurut sejarawan X, kelompok ini...").
- Perlindungan Teknis Mutlak:
  * Pertahankan nama berkas, URL, DOI, ISBN, ISSN, dan atribut tabel (class="wikitable", style).
  * Pertahankan isi rujukan <ref>...</ref> dan templat sitasi ({{cite web}}, {{cite book}}), termasuk judul publikasi dan nama pengarang.
  * Pertahankan isi <math>, chem, code, syntaxhighlight, nowiki, dan komentar HTML.
  * Pertahankan setiap placeholder token (⟦REF_0⟧, ⟦CITE_0⟧, ⟦MATH_0⟧, ⟦CODE_0⟧) persis pada posisinya."""


TOPIC_GLOSSARIES: Dict[str, Dict[str, str]] = {
    "computing_science": {
        "algorithm": "algoritma",
        "annealing": "penganilan",
        "benchmark": "tolok ukur",
        "bloch sphere": "bola Bloch",
        "classical computer": "komputer klasik",
        "computational complexity": "kompleksitas komputasi",
        "computer": "komputer",
        "data center": "pusat data",
        "database": "basis data",
        "fault-tolerant": "toleran kesalahan",
        "framework": "kerangka kerja",
        "hardware": "perangkat keras",
        "interface": "antarmuka",
        "matrix": "matriks",
        "network": "jaringan",
        "parameter": "parameter",
        "qubit": "kubit",
        "quantum annealing": "penganilan kuantum",
        "quantum circuit": "sirkuit kuantum",
        "quantum computer": "komputer kuantum",
        "quantum computing": "komputasi kuantum",
        "quantum decoherence": "dekoherensi kuantum",
        "quantum entanglement": "keterikatan kuantum",
        "quantum error correction": "koreksi kesalahan kuantum",
        "quantum gate": "gerbang kuantum",
        "quantum state": "keadaan kuantum",
        "quantum supremacy": "keunggulan kuantum",
        "real-time": "waktu nyata",
        "software": "perangkat lunak",
        "state of the art": "mutakhir / terkini",
        "streamlining": "perampingan",
        "superposition": "superposisi",
    },
    "physics_mathematics": {
        "algorithm": "algoritma",
        "angular momentum": "momentum sudut",
        "black hole": "lubang hitam",
        "continuous": "kontinu",
        "differential equation": "persamaan diferensial",
        "discrete": "diskret",
        "eigenstate": "keadaan eigen",
        "eigenvalue": "nilai eigen",
        "eigenvector": "vektor eigen",
        "general relativity": "relativitas umum",
        "matrix": "matriks",
        "matrix mechanics": "mekanika matriks",
        "parameter": "parameter",
        "probability density": "kerapatan probabilitas",
        "special relativity": "relativitas khusus",
        "spin": "spin",
        "thermodynamics": "termodinamika",
        "uncertainty principle": "prinsip ketidakpastian",
        "wave function": "fungsi gelombang",
        "wave mechanics": "mekanika gelombang",
    },
    "medical_biology": {
        "antibody": "antibodi",
        "antigen": "antigen",
        "cellular": "seluler",
        "central nervous system": "sistem saraf pusat",
        "clinical trial": "uji klinis",
        "double-blind": "buta ganda",
        "efficacy": "efikasi / kemanjuran",
        "gene expression": "ekspresi gen",
        "immune system": "sistem imun / sistem kekebalan tubuh",
        "mutation": "mutasi",
        "pathogen": "patogen",
        "placebo": "plasebo",
        "randomized controlled trial": "uji coba terkontrol teracak",
        "side effect": "efek samping",
        "transcription": "transkripsi",
        "translation": "translasi",
    },
    "history_social": {
        "abdicate": "turun takhta / melepaskan takhta",
        "accession": "kenaikan takhta",
        "administrative division": "pembagian administratif / wilayah administratif",
        "agrarian": "agraria / pertanian",
        "ancient history": "sejarah kuno",
        "annexation": "aneksasi / pencaplokan wilayah",
        "appointed as": "diangkat sebagai",
        "archaeology": "arkeologi",
        "aristocracy": "kaum bangsawan / aristokrasi",
        "armistice": "gencatan senjata",
        "ascend the throne": "naik takhta",
        "autocracy": "otokrasi",
        "baron": "baron",
        "battle": "pertempuran",
        "belligerent": "pihak yang berperang",
        "bourgeoisie": "kaum borjuis",
        "cabinet": "kabinet",
        "campaign": "kampanye militer / aksi politik",
        "casus belli": "alasan perang (casus belli)",
        "chancellor": "kanselir",
        "chronicle": "babad / kronik",
        "civil war": "perang saudara",
        "civilization": "peradaban",
        "colonialism": "kolonialisme",
        "commander-in-chief": "panglima tertinggi",
        "commoner": "rakyat jelata",
        "confederacy": "konfederasi",
        "conquest": "penaklukan",
        "constituency": "daerah pemilihan (dapil)",
        "constitutional monarchy": "monarki konstitusional",
        "coronation": "penobatan",
        "count": "pangeran / count",
        "coup d'état": "kudeta",
        "decolonization": "dekolonisasi",
        "decree": "dekret / titah kekaisaran",
        "demilitarized zone": "zona demiliterisasi",
        "dissolution": "pembubaran",
        "duke": "adipati / duke",
        "dynasty": "dinasti / wangsa",
        "earl": "earl / bangsawan",
        "edict": "maklumat / edik",
        "empire": "kekaisaran / imperium",
        "feudalism": "feodalisme",
        "heir apparent": "putra mahkota / pewaris takhta utama",
        "heir presumptive": "pewaris takhta sementara",
        "held office": "menjabat / memangku jabatan",
        "imperial": "kekaisaran / imperial",
        "indigenous": "masyarakat adat / pribumi",
        "insurgency": "pemberontakan",
        "interregnum": "masa peralihan kekuasaan (interregnum)",
        "kingdom": "kerajaan",
        "knighthood": "gelar kebangsawanan / ksatria",
        "line of succession": "garis suksesi takhta",
        "lord": "tuan / bangsawan",
        "marquess": "marquess",
        "middle ages": "abad pertengahan",
        "modern era": "era modern / zaman modern",
        "monarchy": "monarki",
        "nobility": "kaum bangsawan / ningrat",
        "parliament": "parlemen",
        "peerage": "kebangsawanan (peerage)",
        "plebiscite": "plebisit / referendum",
        "prime minister": "perdana menteri",
        "protectorate": "protektorat",
        "puppet state": "negara boneka",
        "regent": "wali penguasa / pemangku takhta",
        "regency": "dewan perwalian",
        "reign": "masa kekuasaan / masa pemerintahan",
        "republic": "republik",
        "revolution": "revolusi",
        "royal family": "keluarga kerajaan",
        "saint petersburg": "Sankt-Peterburg",
        "sedition": "penghasutan / subversi",
        "senate": "senat",
        "siege": "pengepungan",
        "skirmish": "pertempuran kecil / bentrokan",
        "sovereignty": "kedaulatan",
        "st. petersburg": "Sankt-Peterburg",
        "styled": "bergelar",
        "succession": "suksesi",
        "survived by": "meninggalkan (keluarga yang masih hidup)",
        "suzerainty": "suzerenitas / pertuanan",
        "tenure": "masa jabatan",
        "treaty": "perjanjian / traktat",
        "tribute": "upeti",
        "truce": "gencatan senjata",
        "unconditional surrender": "penyerahan tanpa syarat",
        "vassal state": "negara vasal / negara bawahan",
        "viscount": "viscount",
        # Period-accurate terms and historical exonyms (WP:Panduan menerjemahkan artikel/Sejarah & Tokoh)
        "serf": "hamba tani",
        "serfs": "hamba tani",
        "serfdom": "perhambaan tani / sistem hamba tani",
        "decembrist": "kaum Dekabris / Dekabris",
        "decembrists": "kaum Dekabris",
        "charlemagne": "Karel yang Agung",
        "peter the great": "Petrus yang Agung",
        "ivan the terrible": "Ivan yang Mengerikan",
        "batavia": "Batavia",
        "dutch east indies": "Hindia Belanda",
        "byzantine empire": "Kekaisaran Romawi Timur / Kekaisaran Bizantium",
        "ottoman empire": "Kesultanan Utsmaniyah / Kekaisaran Utsmaniyah",
        "holy roman empire": "Kekaisaran Romawi Suci",
        "russian empire": "Kekaisaran Rusia",
        "tsar": "tsar",
        "tsarina": "tsarina",
        "tsardom": "ketsaran",
        "tsarist": "Tsaris",
        "tsarist autocracy": "otokrasi Tsaris",
        "general elections": "pemilihan umum",
        "manumission": "pemerdekaan budak / pembebasan",
        "indentured servant": "buruh kontrak feodal",
        "fief": "tanah lungguh / fief feodal",
    },
    "film": {
        "academy awards": "Academy Awards (Piala Oscar)",
        "approval rating": "peringkat persetujuan",
        "barrister": "advokat / pengacara",
        "box office": "pencapaian box office / bioskop komersial",
        "box-office bomb": "film gagal secara komersial",
        "box-office flop": "film gagal secara komersial",
        "cameo": "kameo",
        "character": "karakter / tokoh",
        "cgi": "citra hasil komputer (CGI)",
        "cinematographer": "penata sinematografi / pengarah fotografi",
        "critical reception": "penerimaan kritis / tanggapan kritikus",
        "debut": "debut",
        "development": "pengembangan",
        "direct-to-streaming": "rilis langsung ke layanan pengaliran",
        "director of photography": "penata sinematografi / pengarah fotografi (DoP)",
        "distributor": "distributor",
        "executive producer": "produser eksekutif",
        "feature film": "film cerita panjang / film panjang",
        "foley": "foley",
        "franchise": "waralaba",
        "genre": "genre",
        "gross revenue": "pendapatan kotor",
        "lead actor": "pemeran utama pria",
        "lead actress": "pemeran utama wanita",
        "metacritic": "Metacritic",
        "nomination": "nominasi",
        "original score": "musik orisinal",
        "pilot episode": "episode perintis / episode pilot",
        "plot summary": "ringkasan alur cerita",
        "post-credits scene": "adegan pascakredit",
        "post-production": "pascaproduksi",
        "pre-production": "praproduksi",
        "premiere": "pemutaran perdana",
        "prequel": "prekuel",
        "principal photography": "pengambilan gambar utama",
        "production": "produksi",
        "production company": "rumah produksi",
        "rotten tomatoes": "Rotten Tomatoes",
        "runtime": "durasi film",
        "screenplay": "skenario",
        "screenwriter": "penulis skenario",
        "script": "naskah / skenario",
        "sequel": "sekuel",
        "short film": "film pendek",
        "sound effect": "efek suara",
        "soundtrack": "jalur suara",
        "special effects": "efek khusus (SFX)",
        "spin-off": "sempalan",
        "straight-to-video": "rilis langsung ke video",
        "streamlining": "perampingan",
        "stunt double": "pemeran pengganti",
        "supporting actor": "pemeran pendukung pria",
        "supporting actress": "pemeran pendukung wanita",
        "supporting cast": "pemeran pendukung",
        "theatrical release": "perilisan bioskop",
        "thriller": "cerita seru / film cerita seru",
        "visual effects": "efek visual (VFX)",
    },
    "tv_series": {
        "approval rating": "peringkat persetujuan",
        "broadcasting": "penyiaran",
        "cameo": "kameo",
        "character": "karakter / tokoh",
        "cliffhanger": "cerita menggantung / ujung gantung",
        "critical reception": "penerimaan kritis / tanggapan kritikus",
        "debut": "debut",
        "distributor": "distributor",
        "episode": "episode",
        "executive producer": "produser eksekutif",
        "foley": "foley",
        "franchise": "waralaba",
        "genre": "genre",
        "guest appearance": "penampilan tamu",
        "guest star": "bintang tamu",
        "main cast": "pemeran utama",
        "miniseries": "serial mini",
        "nomination": "nominasi",
        "pilot episode": "episode perintis / episode pilot",
        "premiere": "pemutaran perdana",
        "recurring role": "peran berulang",
        "season": "musim",
        "season finale": "akhir musim / episode pemungkas musim",
        "season premiere": "pemutaran perdana musim",
        "series regular": "pemeran reguler serial",
        "showrunner": "penggagas utama serial / pengelola acara (showrunner)",
        "sound effect": "efek suara",
        "spin-off": "sempalan",
        "streaming service": "layanan pengaliran media / layanan streaming",
        "syndication": "sindikasi",
        "teleplay": "naskah televisi",
        "television series": "serial televisi",
        "tv series": "serial TV / serial televisi",
        "voice actor": "pengisi suara / pemeran suara",
        "voice actress": "pengisi suara wanita / pemeran suara wanita",
        "voice cast": "pengisi suara / jajaran pengisi suara",
    },
    "entertainment": {
        "academy awards": "Academy Awards (Piala Oscar)",
        "approval rating": "peringkat persetujuan",
        "box office": "pencapaian box office / bioskop komersial",
        "box-office bomb": "film gagal secara komersial",
        "box-office flop": "film gagal secara komersial",
        "cameo": "kameo",
        "cgi": "citra hasil komputer (CGI)",
        "character": "karakter / tokoh",
        "cinematographer": "penata sinematografi / pengarah fotografi",
        "cliffhanger": "cerita menggantung / ujung gantung",
        "critical reception": "penerimaan kritis / tanggapan kritikus",
        "debut": "debut",
        "development": "pengembangan",
        "director of photography": "penata sinematografi / pengarah fotografi (DoP)",
        "distributor": "distributor",
        "entertainment": "hiburan",
        "feature film": "film cerita panjang / film panjang",
        "foley": "foley",
        "franchise": "waralaba",
        "genre": "genre",
        "gross revenue": "pendapatan kotor",
        "guest appearance": "penampilan tamu",
        "lead actor": "pemeran utama pria",
        "lead actress": "pemeran utama wanita",
        "metacritic": "Metacritic",
        "miniseries": "serial mini",
        "nomination": "nominasi",
        "original score": "musik orisinal",
        "pilot episode": "episode perintis / episode pilot",
        "plot summary": "ringkasan alur cerita",
        "post-credits scene": "adegan pascakredit",
        "post-production": "pascaproduksi",
        "pre-production": "praproduksi",
        "premiere": "pemutaran perdana",
        "prequel": "prekuel",
        "principal photography": "pengambilan gambar utama",
        "production company": "rumah produksi",
        "recurring role": "peran berulang",
        "rotten tomatoes": "Rotten Tomatoes",
        "runtime": "durasi",
        "screenplay": "skenario",
        "screenwriter": "penulis skenario",
        "season finale": "akhir musim / episode pemungkas musim",
        "season premiere": "pemutaran perdana musim",
        "sequel": "sekuel",
        "short film": "film pendek",
        "showrunner": "penggagas utama serial / pengelola acara (showrunner)",
        "sound effect": "efek suara",
        "soundtrack": "jalur suara",
        "spin-off": "sempalan",
        "streaming service": "layanan pengaliran media / layanan streaming",
        "stunt double": "pemeran pengganti",
        "supporting actor": "pemeran pendukung pria",
        "supporting actress": "pemeran pendukung wanita",
        "theatrical release": "perilisan bioskop",
        "visual effects": "efek visual (VFX)",
        "voice actor": "pengisi suara / pemeran suara",
        "voice cast": "pengisi suara / pemeran suara",
    },
    "aerospace_aviation": {
        "afterburner": "pembakar lanjut",
        "afterburning": "berpembakar lanjut",
        "aileron": "aileron / kemudi guling",
        "airframe": "badan pesawat / rangka pesawat",
        "angle of attack": "sudut serang",
        "apogee": "apogea / titik terjauh orbit",
        "attitude control": "kendali orientasi wahana",
        "avionics": "avionika",
        "boundary layer": "lapisan batas",
        "bypass ratio": "rasio pintas",
        "camber": "kelengkungan sayap",
        "canard": "kanard / sayap depan",
        "ceiling": "ketinggian jelajah maksimum",
        "climb rate": "laju tanjak",
        "combustion chamber": "ruang bakar",
        "convergent-divergent nozzle": "nosel konvergen-divergen",
        "de-icing": "pencairan es",
        "delta wing": "sayap delta",
        "drag coefficient": "koefisien hambatan",
        "elevator": "kemudi anggul / elevator",
        "empennage": "bidang ekor / empennage",
        "flaps": "sirip sayap / flap",
        "flight control system": "sistem kendali penerbangan",
        "fly-by-wire": "kendali terbang kawat (fly-by-wire)",
        "fuselage": "badan pesawat (fuselage)",
        "hypersonic": "hipersonik",
        "instrument flight rules": "aturan terbang instrumen (IFR)",
        "jet engine": "mesin jet",
        "landing gear": "roda pendaratan",
        "leading edge": "tepi depan sayap",
        "lift-to-drag ratio": "rasio gaya angkat terhadap hambatan",
        "mach number": "bilangan Mach",
        "payload": "muatan berbayar / muatan",
        "perigee": "perigea / titik terdekat orbit",
        "pitch": "gerak anggul (pitch)",
        "propulsion": "daya dorong / propulsi",
        "radar cross-section": "penampang radar",
        "ramjet": "ramjet",
        "roll": "gerak guling (roll)",
        "rotor": "baling-baling / rotor",
        "rudder": "kemudi belok / rudder",
        "scramjet": "scramjet",
        "service ceiling": "ketinggian terbang operasional maksimum",
        "slats": "slat / bilah tepi depan",
        "sonic boom": "ledakan sonik",
        "specific fuel consumption": "konsumsi bahan bakar spesifik",
        "specific impulse": "impuls spesifik",
        "stall": "kehilangan gaya angkat / stall",
        "supercruise": "jelajah supersonik (supercruise)",
        "supersonic": "supersonik",
        "thrust": "daya dorong",
        "thrust vectoring": "pembelokan daya dorong",
        "thrust-to-weight ratio": "rasio daya dorong terhadap berat",
        "trailing edge": "tepi belakang sayap",
        "turbofan": "turbofan",
        "turbojet": "turbojet",
        "turboprop": "turboprop",
        "turboshaft": "turboshaft",
        "variable-sweep wing": "sayap sapuan variabel",
        "visual flight rules": "aturan terbang visual (VFR)",
        "vortex": "pusaran udara / vorteks",
        "yaw": "gerak geleng (yaw)",
    },
    "mechanical_engineering": {
        "actuator": "aktuator",
        "annealing": "penganilan",
        "bearing": "bantalan peluru / laher",
        "bending moment": "momen lentur",
        "camshaft": "poros nok / poros bumbungan",
        "centrifugal force": "gaya sentrifugal",
        "combustion chamber": "ruang bakar",
        "compressor": "kompresor",
        "crankcase": "bak engkol",
        "crankshaft": "poros engkol",
        "damping": "redaman",
        "diesel engine": "mesin diesel",
        "displacement": "kapasitas mesin / perpindahan volume",
        "efficiency": "efisiensi / daya guna",
        "enthalpy": "entalpi",
        "entropy": "entropi",
        "exhaust manifold": "manifold buang",
        "fatigue life": "usia lelah bahan",
        "finite element analysis": "analisis elemen hingga (FEA)",
        "fluid dynamics": "dinamika fluida",
        "flywheel": "roda gila / roda penerus",
        "forced convection": "konveksi paksa",
        "four-stroke engine": "mesin empat langkah (4 tak)",
        "friction": "gesekan",
        "gasket": "paking / gasket",
        "gear ratio": "rasio roda gigi",
        "gearbox": "kotak roda gigi",
        "heat dissipation": "pelepasan panas / disipasi panas",
        "heat exchanger": "penukar panas",
        "horsepower": "tenaga kuda (hp)",
        "hydraulic": "hidraulis",
        "internal combustion engine": "mesin pembakaran dalam",
        "kinematics": "kinematika",
        "laminar flow": "aliran laminer",
        "lubricant": "pelumas",
        "machining": "pemesinan",
        "manifold": "manifold",
        "mechanical advantage": "keuntungan mekanis",
        "piston": "torak / piston",
        "planetary gear": "roda gigi planet",
        "pneumatic": "pneumatik",
        "shear stress": "tegangan geser",
        "spark plug": "busi",
        "stress concentration": "konsentrasi tegangan",
        "supercharger": "supercharger",
        "tensile strength": "kekuatan tarik",
        "thermal conductivity": "konduktivitas termal",
        "thermal expansion": "pemuaian termal",
        "thermodynamics": "termodinamika",
        "torque": "torsi / momen gaya",
        "transmission": "transmisi",
        "turbine": "turbin",
        "turbocharger": "turbocharger",
        "turbulent flow": "aliran turbulen",
        "valve": "katup",
        "viscosity": "viskositas / kekentalan",
        "yield strength": "kekuatan luluh",
    },
    "mathematics_statistics": {
        "algebraic topology": "topologi aljabar",
        "asymptote": "asimtot",
        "axiom": "aksioma",
        "bayesian inference": "inferensi Bayes",
        "bijection": "bijeksi / pemetaan bijektif",
        "binomial distribution": "distribusi binomial",
        "calculus of variations": "kalkulus variasi",
        "cauchy sequence": "barisan Cauchy",
        "central limit theorem": "teorema limit pusat",
        "characteristic polynomial": "polinomial karakteristik",
        "closed set": "himpunan tertutup",
        "compact space": "ruang kompak",
        "conditional probability": "probabilitas bersyarat",
        "confidence interval": "interval kepercayaan",
        "continuous mapping": "pemetaan kontinu",
        "correlation": "korelasi",
        "covariance": "kovarians",
        "differential geometry": "geometri diferensial",
        "divergence": "divergensi",
        "eigenvalue": "nilai eigen",
        "eigenvector": "vektor eigen",
        "euclidean space": "ruang Euklides",
        "gradient": "gradien",
        "hausdorff space": "ruang Hausdorff",
        "hilbert space": "ruang Hilbert",
        "homeomorphism": "homeomorfisme",
        "hypothesis testing": "pengujian hipotesis",
        "infimum": "infimum / batas bawah terbesar",
        "injection": "injeksi / pemetaan injektif",
        "inner product space": "ruang hasil kali dalam",
        "integral": "integral",
        "isomorphism": "isomorfisme",
        "linear algebra": "aljabar linear",
        "manifold": "manifol",
        "markov chain": "rantai Markov",
        "maximum likelihood": "kemungkinan maksimum (maximum likelihood)",
        "mean": "rata-rata / rerata",
        "median": "median / nilai tengah",
        "mode": "modus",
        "normal distribution": "distribusi normal / distribusi Gauss",
        "null hypothesis": "hipotesis nol",
        "open set": "himpunan terbuka",
        "p-value": "nilai-p",
        "partial derivative": "turunan parsial",
        "probability distribution": "distribusi probabilitas",
        "random variable": "variabel acak / peubah acak",
        "regression analysis": "analisis regresi",
        "riemannian manifold": "manifol Riemann",
        "sample size": "ukuran sampel",
        "standard deviation": "deviasi standar / simpangan baku",
        "set": "himpunan",
        "subset": "himpunan bagian / subhimpunan",
        "proper subset": "himpunan bagian sejati",
        "empty set": "himpunan kosong",
        "universal set": "himpunan semesta",
        "element": "elemen / anggota himpunan",
        "intersection": "irisan",
        "union": "gabungan",
        "complement": "komplemen",
        "function": "fungsi",
        "map": "pemetaan",
        "mapping": "pemetaan",
        "domain": "domain / daerah asal",
        "codomain": "kodomain / daerah kawan",
        "range": "daerah hasil",
        "injective": "injektif (satu-ke-satu)",
        "surjective": "surjektif (pada)",
        "bijective": "bijektif (korespondensi satu-satu)",
        "inverse": "invers / balikan",
        "real number": "bilangan real",
        "real numbers": "bilangan real",
        "natural number": "bilangan asli",
        "natural numbers": "bilangan asli",
        "integer": "bilangan bulat",
        "integers": "bilangan bulat",
        "rational number": "bilangan rasional",
        "rational numbers": "bilangan rasional",
        "irrational number": "bilangan irasional",
        "irrational numbers": "bilangan irasional",
        "complex number": "bilangan kompleks",
        "complex numbers": "bilangan kompleks",
        "prime number": "bilangan prima",
        "prime numbers": "bilangan prima",
        "field": "medan (aljabar) / lapangan",
        "ring": "gelanggang",
        "group": "grup",
        "subgroup": "subgrup",
        "linear transformation": "transformasi linear",
        "determinant": "determinan",
        "derivative": "turunan / derivatif",
        "limit": "limit",
        "theorem": "teorema",
        "lemma": "lemma",
        "corollary": "korolar / akibat",
        "proposition": "proposisi",
        "conjecture": "konjektur / dugaan",
        "postulate": "postulat",
        "proof": "bukti",
        "q.e.d.": "Q.E.D. / Terbukti",
        "sequence": "barisan",
        "series": "deret",
        "polynomial": "polinomial / suku banyak",
        "graph theory": "teori graf",
        "topology": "topologi",
        "supremum": "supremum / batas atas terkecil",
        "surjection": "surjeksi / pemetaan surjektif",
        "tensor": "tensor",
        "variance": "varians",
    },
    "chemistry_materials": {
        "activation energy": "energi aktivasi",
        "alkali metal": "logam alkali",
        "alloy": "paduan logam / lakur",
        "amorphous": "amorf",
        "aqueous solution": "larutan berair",
        "atomic radius": "jari-jari atom",
        "catalyst": "katalis",
        "chemical equilibrium": "kesetimbangan kimia",
        "composite material": "material komposit",
        "covalent bond": "ikatan kovalen",
        "crystal lattice": "kisi kristal",
        "crystallography": "kristalografi",
        "electronegativity": "elektronegativitas / keelektronegatifan",
        "enthalpy of reaction": "entalpi reaksi",
        "half-life": "waktu paruh",
        "hydrogen bond": "ikatan hidrogen",
        "ionic bond": "ikatan ionik",
        "isomer": "isomer",
        "isotope": "isotop",
        "kinetic theory": "teori kinetik",
        "molar mass": "massa molar",
        "molecular geometry": "geometri molekul",
        "nanomaterial": "material nano",
        "noble gas": "gas mulia",
        "oxidation state": "bilangan oksidasi / tingkat oksidasi",
        "phase transition": "transisi fase",
        "polymerization": "polimerisasi",
        "precipitate": "endapan",
        "redox reaction": "reaksi redoks",
        "semiconductor": "semikonduktor",
        "solute": "zat terlarut",
        "solvent": "pelarut",
        "stoichiometry": "stoikiometri",
        "superconductivity": "superkonduktivitas",
        "valence electron": "elektron valensi",
    },
    "earth_environment": {
        "aquifer": "akuifer / lapisan pembawa air",
        "biodiversity": "keanekaragaman hayati",
        "biome": "bioma",
        "carbon footprint": "jejak karbon",
        "carbon sequestration": "sekuestrasi karbon / penyerapan karbon",
        "continental drift": "pergeseran benua",
        "deforestation": "deforestasi / penggundulan hutan",
        "epicenter": "episentrum",
        "fault line": "garis patahan / sesar",
        "fossil fuel": "bahan bakar fosil",
        "geological fault": "sesar geologis",
        "glacier": "gletser",
        "global warming": "pemanasan global",
        "greenhouse effect": "efek rumah kaca",
        "greenhouse gas": "gas rumah kaca",
        "groundwater": "air tanah",
        "igneous rock": "batuan beku",
        "lithosphere": "litosfer",
        "magma chamber": "dapur magma",
        "mantle": "mantel bumi",
        "metamorphic rock": "batuan metamorf",
        "monsoon": "angin muson",
        "ozone layer": "lapisan ozon",
        "permafrost": "ibun abadi / permafrost",
        "plate tectonics": "tektonika lempeng",
        "precipitation": "presipitasi / curah hujan",
        "renewable energy": "energi terbarukan",
        "sedimentary rock": "batuan sedimen",
        "seismic wave": "gelombang seismik",
        "stratigraphy": "stratigrafi",
        "subduction zone": "zona penunjaman / zona subduksi",
        "tectonic plate": "lempeng tektonik",
        "volcanic arc": "busur vulkanik",
        "watershed": "daerah aliran sungai (DAS)",
    },
    "economics_finance": {
        "aggregate demand": "permintaan agregat",
        "aggregate supply": "penawaran agregat",
        "amortization": "amortisasi",
        "arbitrage": "arbitrase",
        "asset allocation": "alokasi aset",
        "balance of payments": "neraca pembayaran",
        "balance of trade": "neraca perdagangan",
        "bear market": "pasar lesu / tren turun (bear market)",
        "bull market": "pasar bergairah / tren naik (bull market)",
        "capital expenditure": "belanja modal (capex)",
        "central bank": "bank sentral",
        "commodity": "komoditas",
        "compound interest": "bunga majemuk",
        "consumer price index": "indeks harga konsumen (IHK)",
        "current account deficit": "defisit transaksi berjalan",
        "depreciation": "penyusutan / depresiasi",
        "derivative": "instrumen derivatif",
        "dividend yield": "imbal hasil dividen",
        "elasticity": "elastisitas",
        "exchange rate": "kurs mata uang",
        "fiscal policy": "kebijakan fiskal",
        "gross domestic product": "produk domestik bruto (PDB)",
        "gross national income": "pendapatan nasional bruto (PNB)",
        "hedge fund": "dana lindung nilai",
        "inflation": "inflasi",
        "initial public offering": "penawaran umum perdana (IPO)",
        "interest rate": "suku bunga",
        "leverage": "daya ungkit / rasio utang (leverage)",
        "liquidity": "likuiditas",
        "macroeconomics": "makroekonomi",
        "market capitalization": "kapitalisasi pasar",
        "microeconomics": "mikroekonomi",
        "monetary policy": "kebijakan moneter",
        "mutual fund": "reksa dana",
        "opportunity cost": "biaya peluang",
        "purchasing power parity": "paritas daya beli (PPP)",
        "quantitative easing": "pelonggaran kuantitatif",
        "sovereign debt": "utang negara",
        "supply and demand": "penawaran dan permintaan",
        "venture capital": "modal ventura",
        "yield curve": "kurva imbal hasil",
    },
    "military_defense": {
        "air superiority": "keunggulan udara",
        "aircraft carrier": "kapal induk",
        "amphibious assault": "serbuan amfibi",
        "armored personnel carrier": "kendaraan angkut personel lapis baja (APC)",
        "artillery": "artileri",
        "ballistic missile": "rudal balistik",
        "battleship": "kapal tempur",
        "chain of command": "rantai komando",
        "close air support": "dukungan udara jarak dekat (CAS)",
        "collateral damage": "kerusakan sampingan",
        "countermeasure": "langkah penangkal / penangkal balasan",
        "cruise missile": "rudal jelajah",
        "destroyer": "kapal perusak (destroyer)",
        "doctrine": "doktrin militer",
        "drone": "pesawat nirawak (drone)",
        "electronic warfare": "perang elektronik",
        "frigate": "fregat",
        "guided missile": "peluru kendali / rudal",
        "infantry": "infanteri",
        "insurgency": "pemberontakan",
        "intercontinental ballistic missile": "rudal balistik antarbenua (ICBM)",
        "logistics": "logistik militer",
        "main battle tank": "tank tempur utama (MBT)",
        "naval warfare": "peperangan laut",
        "preemptive strike": "serangan pencegahan",
        "radar": "radar",
        "reconnaissance": "pengintaian / rekonsiliasi militer",
        "rules of engagement": "aturan pelibatan militer (ROE)",
        "sortie": "misi terbang tempur (sortie)",
        "stealth aircraft": "pesawat siluman",
        "surface-to-air missile": "rudal darat-ke-udara (SAM)",
        "tactical": "taktis",
        "unmanned aerial vehicle": "wahana udara nirawak (UAV)",
        "war of attrition": "perang atrisi",
    },
    "music_arts": {
        "acoustics": "akustik",
        "aria": "aria",
        "avant-garde": "avant-garde / garda depan",
        "baroque": "barok",
        "cadence": "kadensa",
        "chamber music": "musik kamar",
        "chiaroscuro": "kiaroskuro",
        "chord progression": "progresi akor",
        "choreography": "koreografi",
        "classical music": "musik klasik",
        "concerto": "konserto",
        "counterpoint": "kontrapung",
        "curator": "kurator seni",
        "dissonance": "disonansi",
        "exhibition": "pameran seni",
        "fresco": "fresco",
        "harmony": "harmoni",
        "improvisation": "improvisasi",
        "installation art": "seni instalasi",
        "key signature": "tanda mula",
        "libretto": "libreto",
        "modernism": "modernisme",
        "motif": "motif musik",
        "movement": "babak musik / movement",
        "orchestration": "orkestrasi",
        "overture": "overtur / pembuka simfoni",
        "performance art": "seni pertunjukan",
        "polyphony": "polifoni",
        "renaissance": "renaisans",
        "resonance": "resonansi",
        "scale": "tangga nada",
        "sculpture": "seni patung",
        "sonata": "sonata",
        "symphony": "simfoni",
        "tempo": "tempo",
        "timbre": "warna nada / timbre",
    },
    "law_jurisprudence": {
        "acquittal": "pembebasan / vonis bebas",
        "adjudication": "ajudikasi",
        "amendment": "amendemen konstitusi",
        "appeal": "banding",
        "appellate court": "pengadilan tinggi / pengadilan banding",
        "arbitration": "arbitrase",
        "bail": "jaminan penangguhan penahanan (uang jaminan)",
        "breach of contract": "wanprestasi / pelanggaran kontrak",
        "civil law": "hukum perdata",
        "common law": "hukum umum / common law",
        "constitution": "konstitusi / undang-undang dasar",
        "copyright infringement": "pelanggaran hak cipta",
        "damages": "ganti rugi",
        "defendant": "terdakwa / tergugat",
        "due process": "proses hukum yang adil (due process of law)",
        "extradition": "ekstradisi",
        "habeas corpus": "habeas corpus",
        "indictment": "surat dakwaan",
        "injunction": "putusan sela / perintah pengadilan",
        "intellectual property": "kekayaan intelektual",
        "judicial review": "peninjauan kembali / uji materiil",
        "jurisdiction": "yurisdiksi / kewenangan hukum",
        "jurisprudence": "yurisprudensi",
        "lawsuit": "gugatan hukum",
        "liability": "tanggung gugat / kewajiban hukum",
        "litigation": "litigasi",
        "plaintiff": "penggugat",
        "precedent": "preseden hukum",
        "prosecutor": "jaksa penuntut umum",
        "statute": "undang-undang / statuta",
        "statutory law": "hukum tertulis / perundang-undangan",
        "supreme court": "mahkamah agung",
        "tort": "perbuatan melawan hukum (PMH)",
        "treaty": "perjanjian internasional / traktat",
        "verdict": "putusan pengadilan",
    },
    "religion": {
        # Christianity / Catholicism (WP:Panduan dalam menerjemahkan artikel/Agama)
        "abbey": "keabasan / biara keabasan / pertapaan",
        "priory": "priorat",
        "eparchy": "eparki",
        "eparch": "epark",
        "archdiocese": "keuskupan agung",
        "diocese": "keuskupan",
        "archbishop": "uskup agung",
        "bishop": "uskup",
        "cardinal": "kardinal",
        "patriarch": "patriark",
        "patriarchate": "patriarkat",
        "papacy": "kepausan",
        "pope": "paus",
        "monk": "biarawan",
        "nun": "biarawati / suster",
        "clergy": "klerus / rohaniwan",
        "priest": "imam / pastor",
        "deacon": "diaken",
        "mass": "misa",
        "eucharist": "ekaristi",
        "liturgy": "liturgi",
        "parish": "paroki",
        "deanery": "dekenat",
        "apostolic nuncio": "nunsius apostolik",
        "holy see": "Takhta Suci",
        "vatican": "Vatikan",
        "basilica": "basilika",
        "cathedral": "katedral",
        "chapel": "kapel",
        "altar": "altar",
        "tabernacle": "tabernakel",
        "canonization": "kanonisasi",
        "beatification": "beatifikasi",
        "encyclical": "ensiklik",
        "pilgrim": "peziarah",
        "pilgrimage": "ziarah",
        # Buddhism (WP:Panduan dalam menerjemahkan artikel/Agama)
        "bhikkhu": "bikkhu",
        "bhikkhuni": "bikkhuni",
        "three refuges": "Tri Sarana (Tiga Perlindungan)",
        "triple gem": "Tri Ratna (Tiga Permata)",
        "devotion": "kebaktian / bakti",
        "deity": "istadewata",
        "sangha": "sangha",
        "dharma": "dharma",
        "dhamma": "dhamma",
        "karma": "karma",
        "kamma": "kamma",
        "nirvana": "nirwana",
        "nibbana": "nibbana",
        "sutra": "sutra",
        "sutta": "sutta",
        "bodhisattva": "bodhisatwa",
        "vihara": "vihara",
        "stupa": "stupa",
        "pagoda": "pagoda",
        # Islam
        "missionary": "dai / pendakwah",
        "mosque": "masjid",
        "caliph": "khalifah",
        "caliphate": "kekhalifahan",
        "hadith": "hadis",
        "sunnah": "sunnah",
        "fiqh": "fikih",
        "sharia": "syariat",
        "fatwa": "fatwa",
        "ulama": "ulama",
        "madrasa": "madrasah",
        # Judaism & Other
        "rabbi": "rabi",
        "synagogue": "sinagoge",
        "torah": "Taurat",
        "talmud": "Talmud",
        "shabbat": "Sabat",
        "kosher": "kosher",
        "temple": "pura / candi / mandir",
        "moksha": "moksa",
        "samsara": "samsara",
        "vedas": "Weda",
        "upanishads": "Upanisad",
    },
}

# Topic aliases for flexible CLI selection and user convenience
TOPIC_GLOSSARIES["cinema"] = TOPIC_GLOSSARIES["film"]
TOPIC_GLOSSARIES["television"] = TOPIC_GLOSSARIES["tv_series"]
TOPIC_GLOSSARIES["media"] = TOPIC_GLOSSARIES["entertainment"]
TOPIC_GLOSSARIES["aerospace"] = TOPIC_GLOSSARIES["aerospace_aviation"]
TOPIC_GLOSSARIES["aviation"] = TOPIC_GLOSSARIES["aerospace_aviation"]
TOPIC_GLOSSARIES["jet"] = TOPIC_GLOSSARIES["aerospace_aviation"]
TOPIC_GLOSSARIES["aircraft"] = TOPIC_GLOSSARIES["aerospace_aviation"]
TOPIC_GLOSSARIES["engineering"] = TOPIC_GLOSSARIES["mechanical_engineering"]
TOPIC_GLOSSARIES["mechanics"] = TOPIC_GLOSSARIES["mechanical_engineering"]
TOPIC_GLOSSARIES["thermodynamics"] = TOPIC_GLOSSARIES["mechanical_engineering"]
TOPIC_GLOSSARIES["math"] = TOPIC_GLOSSARIES["mathematics_statistics"]
TOPIC_GLOSSARIES["mathematics"] = TOPIC_GLOSSARIES["mathematics_statistics"]
TOPIC_GLOSSARIES["statistics"] = TOPIC_GLOSSARIES["mathematics_statistics"]
TOPIC_GLOSSARIES["chemistry"] = TOPIC_GLOSSARIES["chemistry_materials"]
TOPIC_GLOSSARIES["materials_science"] = TOPIC_GLOSSARIES["chemistry_materials"]
TOPIC_GLOSSARIES["material"] = TOPIC_GLOSSARIES["chemistry_materials"]
TOPIC_GLOSSARIES["geology"] = TOPIC_GLOSSARIES["earth_environment"]
TOPIC_GLOSSARIES["geography"] = TOPIC_GLOSSARIES["earth_environment"]
TOPIC_GLOSSARIES["climate"] = TOPIC_GLOSSARIES["earth_environment"]
TOPIC_GLOSSARIES["environment"] = TOPIC_GLOSSARIES["earth_environment"]
TOPIC_GLOSSARIES["economics"] = TOPIC_GLOSSARIES["economics_finance"]
TOPIC_GLOSSARIES["finance"] = TOPIC_GLOSSARIES["economics_finance"]
TOPIC_GLOSSARIES["business"] = TOPIC_GLOSSARIES["economics_finance"]
TOPIC_GLOSSARIES["military"] = TOPIC_GLOSSARIES["military_defense"]
TOPIC_GLOSSARIES["defense"] = TOPIC_GLOSSARIES["military_defense"]
TOPIC_GLOSSARIES["music"] = TOPIC_GLOSSARIES["music_arts"]
TOPIC_GLOSSARIES["art"] = TOPIC_GLOSSARIES["music_arts"]
TOPIC_GLOSSARIES["arts"] = TOPIC_GLOSSARIES["music_arts"]
TOPIC_GLOSSARIES["law"] = TOPIC_GLOSSARIES["law_jurisprudence"]
TOPIC_GLOSSARIES["legal"] = TOPIC_GLOSSARIES["law_jurisprudence"]
TOPIC_GLOSSARIES["biography"] = TOPIC_GLOSSARIES["history_social"]
TOPIC_GLOSSARIES["history"] = TOPIC_GLOSSARIES["history_social"]
TOPIC_GLOSSARIES["monarchy"] = TOPIC_GLOSSARIES["history_social"]
TOPIC_GLOSSARIES["politics"] = TOPIC_GLOSSARIES["history_social"]
TOPIC_GLOSSARIES["pure_mathematics"] = TOPIC_GLOSSARIES["mathematics_statistics"]
TOPIC_GLOSSARIES["religion_theology"] = TOPIC_GLOSSARIES["religion"]
TOPIC_GLOSSARIES["theology"] = TOPIC_GLOSSARIES["religion"]
TOPIC_GLOSSARIES["agama"] = TOPIC_GLOSSARIES["religion"]


STRUCTURAL_EXEMPLARS: Dict[str, List[Dict[str, str]]] = {
    "history_social": [
        {
            "en": "Born into a minor noble family in Corsica, Napoleon rose rapidly through the ranks of the military during the French Revolution, leveraging his tactical brilliance in the Italian campaigns before staging a coup d'état and crowning himself Emperor.",
            "id": "Napoleon lahir di Korsika dari keluarga bangsawan rendahan. Bakat taktisnya yang gemilang selama kampanye militer di Italia membuat kariernya melesat pesat semasa Revolusi Prancis. Setelah memimpin kudeta, ia akhirnya menobatkan dirinya sebagai Kaisar Prancis.",
            "note": "Memecah partisip awal 'Born into...', menyusun subjek-predikat aktif 'kariernya melesat pesat', dan memilih istilah penobatan kaisar yang baku 'menobatkan'.",
        },
        {
            "en": "Upon the sudden death of the King without an heir apparent, his brother acted as regent, but political pressure from the landed aristocracy forced him to renounce his claims to the throne.",
            "id": "Menyusul kemangkatan sang raja tanpa meninggalkan putra mahkota, adik laki-lakinya ditunjuk sebagai wali penguasa. Kendati demikian, tekanan politik dari kaum bangsawan tuan tanah memaksanya melepaskan hak atas takhta.",
            "note": "Menerjemahkan 'death of the King' menjadi 'kemangkatan sang raja', 'heir apparent' menjadi 'putra mahkota', 'regent' menjadi 'wali penguasa' (bukan bupati), dan merangkai kalimat dengan konjungsi 'Kendati demikian'.",
        },
        {
            "en": "She married at 19, and she and her husband, Konstantin, had seven children before she devoted herself entirely to women's advocacy.",
            "id": "Ia menikah dengan Konstantin pada usia 19 tahun dan dikaruniai tujuh anak sebelum mendedikasikan hidupnya secara penuh untuk pembelaan hak-hak perempuan.",
            "note": "Melebur subjek ganda 'she and her husband' menjadi satu alur terpadu, mengubah 'had children' menjadi pasif kultural 'dikaruniai anak', dan menggunakan verba aktif 'mendedikasikan'.",
        },
        {
            "en": "Both her parents died when she was very young: her father died in 1839, while her mother died giving birth the following year.",
            "id": "Kedua orang tuanya wafat ketika ia masih sangat kecil. Sang ayah meninggal pada 1839, sedangkan sang ibu berpulang saat melahirkan pada tahun berikutnya.",
            "note": "Menghilangkan tanda titik dua naratif ':' dari bahasa Inggris dan memecahnya menjadi dua kalimat mandiri dengan tanda titik '.', sesuai konvensi bahasa Indonesia ensiklopedia.",
        },
    ],
    "aerospace_aviation": [
        {
            "en": "Featuring two-dimensional thrust-vectoring convergent-divergent nozzles, the aircraft achieves high maneuverability at supersonic speeds while operating without afterburner in the supercruise regime.",
            "id": "Pesawat ini dilengkapi nosel konvergen-divergen dengan pembelok daya dorong dua dimensi sehingga memiliki kelincahan manuver tinggi pada kecepatan supersonik. Selain itu, pesawat mampu beroperasi tanpa pembakar lanjut dalam mode jelajah supersonik (supercruise).",
            "note": "Memecah klausa bertingkat, membalik urutan modifikasi D-M, dan mengubah 'featuring' menjadi 'dilengkapi'.",
        }
    ],
    "mechanical_engineering": [
        {
            "en": "Heat dissipation from the planetary gearbox is achieved through forced-air cooling over finned casings, preventing thermal degradation of the synthetic lubricant under peak-load conditions.",
            "id": "Pelepasan panas pada kotak roda gigi planet memanfaatkan pendinginan udara paksa yang dialirkan melewati selubung bersirip. Sistem ini mencegah penurunan mutu pelumas sintetis akibat suhu tinggi saat beroperasi pada beban puncak.",
            "note": "Membongkar pasif pasak 'is achieved through' menjadi aktif instrumental 'memanfaatkan', serta memecah kalimat.",
        }
    ],
    "mathematics_statistics": [
        {
            "en": "If f: X -> Y is a continuous surjective mapping from a compact topological space X onto a Hausdorff space Y, then f is a closed map, which implies that the image of any compact subset is necessarily closed.",
            "id": "Misalkan f: X -> Y merupakan pemetaan surjektif kontinu dari ruang topologis kompak X ke ruang Hausdorff Y. Dengan demikian, f adalah pemetaan tertutup. Konsekuensinya, bayangan dari setiap himpunan bagian kompak pasti tertutup di Y.",
            "note": "Menggunakan tradisi leksikon matematika 'Misalkan...', memecah klausa 'which implies that', dan menerjemahkan 'image' menjadi 'bayangan'.",
        }
    ],
    "chemistry_materials": [
        {
            "en": "The transition metal catalyst lowers the activation energy of the hydrogenation reaction, allowing it to proceed rapidly at room temperature without requiring elevated pressure.",
            "id": "Katalis logam transisi menurunkan energi aktivasi reaksi hidrogenasi sehingga reaksi dapat berlangsung cepat pada suhu ruang tanpa memerlukan tekanan tinggi.",
            "note": "Mengganti konstruksi participle 'allowing it to proceed' menjadi klausa hubungan sebab-akibat lugas 'sehingga reaksi dapat berlangsung'.",
        }
    ],
    "economics_finance": [
        {
            "en": "The central bank implemented aggressive quantitative easing to stimulate aggregate demand, while simultaneously raising reserve requirements to mitigate inflation risks.",
            "id": "Bank sentral menerapkan pelonggaran kuantitatif secara agresif demi merangsang permintaan agregat. Pada saat yang sama, otoritas moneter menaikkan rasio cadangan wajib guna menekan risiko lonjakan inflasi.",
            "note": "Memecah kalimat pada konjungsi 'while', mengelak dari repetisi kata, dan menyusun kalimat dengan partikel bernas 'demi/guna'.",
        }
    ],
    "computing_science": [
        {
            "en": "The implementation of fault-tolerant quantum error correction protocols presents significant challenges due to qubit decoherence caused by environmental thermal noise.",
            "id": "Penerapan protokol koreksi galat kuantum yang toleran terhadap kesalahan menghadapi kendala besar akibat dekoherensi kubit yang dipicu oleh derau termal lingkungan.",
            "note": "Mengubah 'presents significant challenges' menjadi 'menghadapi kendala besar', dan 'error correction' menjadi istilah baku 'koreksi galat'.",
        }
    ],
    "military_defense": [
        {
            "en": "Equipped with advanced active electronically scanned array radar and low-observable shaping, the fighter maintains air superiority while conducting standoff precision strikes against defended airspace.",
            "id": "Pesawat tempur ini dilengkapi radar larik pemindai elektronik aktif mutakhir serta rancang bangun berpenampang radar rendah. Kemampuan tersebut menjamin keunggulan udara saat melancarkan serangan presisi jarak jauh ke wilayah udara yang dipertahankan lawan.",
            "note": "Membalik modifier majemuk AESA radar, memecah kalimat, dan memilih istilah pertahanan baku.",
        }
    ],
}

def build_translation_prompt(
    section_title: str,
    wikitext_content: str,
    context_notes: Optional[str] = None,
    topic: Optional[str] = None,
    custom_glossary: Optional[Dict[str, str]] = None,
    resolved_glossary: Optional[Dict[str, str]] = None,
) -> str:
    """Build one contextual glossary, with explicit custom terms taking priority."""
    active_glossary = {
        key.casefold(): (key, value)
        for key, value in TOPIC_GLOSSARIES.get(topic, {}).items()
    }
    for glossary in (resolved_glossary, custom_glossary):
        active_glossary.update({
            key.casefold(): (key, value) for key, value in (glossary or {}).items()
        })
    prompt_parts = [f"### Bagian yang Diterjemahkan: {section_title or 'Pengantar Utama'}"]
    if active_glossary:
        prompt_parts.append("\n### Glosarium Istilah Khusus:")
        if resolved_glossary:
            prompt_parts.append("### GLOSARIUM SPESIFIK UNTUK BAGIAN INI:")
        prompt_parts.append("Pilih padanan sesuai konteks sumber; jangan memaksakan padanan yang berbeda makna.")
        for en_term, id_term in sorted(active_glossary.values()):
            prompt_parts.append(f'- "{en_term}" -> "{id_term}"')
    if context_notes:
        prompt_parts.append(
            "\n### Catatan Konteks Tambahan (bukan teks untuk diterjemahkan):\n"
            + context_notes
        )
    canonical_topic = topic
    if topic:
        for canon, gloss in TOPIC_GLOSSARIES.items():
            if gloss is TOPIC_GLOSSARIES.get(topic):
                canonical_topic = canon
                break

    exemplars = STRUCTURAL_EXEMPLARS.get(canonical_topic or "")
    if exemplars:
        prompt_parts.append("\n### Pola Rekonstruksi Struktur Bahasa Indonesia Alami (Grade A++):")
        for ex in exemplars[:2]:
            prompt_parts.append(f'- Teks Asli (EN): "{ex["en"]}"')
            prompt_parts.append(f'  Pola Rekonstruksi Baku (ID): "{ex["id"]}"')
            prompt_parts.append(f'  Catatan Redaksi: {ex["note"]}')
    prompt_parts.extend([
        "\n### Teks Sumber Wikitext (Bahasa Inggris):",
        "```wikitext",
        wikitext_content,
        "```",
        "\n### Instruksi Terjemahan (Kepatuhan Penuh EYD V & TBBBI):",
        "1. Terjemahkan hanya teks sumber di atas. Pertahankan makna, batas paragraf, markup wikitext, dan setiap rujukan pada klaim yang sama persis. Konteks bukan sumber fakta tambahan.",
        "2. Kaidah Tanda Baca & Sintaksis EYD V (Wajib Patuh):",
        "   - JANGAN menyalin buta tanda koma bahasa Inggris.",
        "   - DILARANG mengapit nama diri dengan koma jika didahului sebutan kekerabatan/profesi/status (\"mantan istrinya Dany Garcia\", BUKAN \"mantan istrinya, Dany Garcia,\").",
        "   - Rekonstruksi aposisi terbalik bahasa Inggris: letakkan Nama Diri di depan sebagai subjek utama (\"Auliʻi Cravalho, pemeran utama film animasinya, bertindak...\", BUKAN \"Pemeran utama film animasinya, Auliʻi Cravalho, bertindak...\").",
        "   - Keterangan pembuka ganda (waktu + tempat) adalah satu kesatuan blok (\"Dahulu kala di Pulau Motunui di Polinesia, ...\", BUKAN \"Dahulu kala, di...\").",
        "   - Hindari rima kakofoni enklitika \"-nya\" beruntun (\"orang tuanya yang manusia menelantarkannya\", BUKAN \"orang tua manusianya membuangnya\").",
        "   - Hindari repetisi subjek pembuka kalimat yang monoton berturut-turut.",
        "3. Keluarkan HANYA hasil terjemahan wikitext tanpa pengantar atau pagar Markdown.",
    ])
    return "\n".join(prompt_parts)

SYSTEM_PROMPT_HUMANIZE_POLISH = SYSTEM_PROMPT_GRADE_A_PLUS_PLUS + """
### Tugas penyunting (Redaktur & Humanize Polish)
Sunting draf Indonesia dengan membandingkannya terhadap sumber Inggris.
Tugas utama Anda adalah de-Anglicization (menghapus sisa-sisa pola sintaksis bahasa Inggris)
dan menata ulang aliran kalimat (cadence/flow) agar berstandar jurnalistik ensiklopedia tertinggi (Grade A++):
1. Keharmonisan Sambungan Antarkalimat: Pastikan transisi antarkalimat mengalir luwes dan padu (kohesif).
2. Pangkas Frasa Kaku & Mubazir: Singkirkan kata pengisi ("sebuah", "dari", "telah", "oleh") yang tidak
   menambah nilai informasi dan terasa seperti luaran terjemahan mesin.
3. Pecah Kalimat yang Terlalu Panjang: Jika draf memiliki satu kalimat yang memuat lebih dari 25 kata
   atau menumpuk lebih dari dua anak kalimat, pecah menjadi dua kalimat yang bernas.
4. Preservasi Makna & Rujukan: Perbaiki kalimat kaku tanpa menggeser makna, pelaku, atau tingkat kepastian.
   Pertahankan seluruh markup wikitext, parameter, dan rujukan persis pada klaim aslinya.
5. Peleburan Subjek & Pemilihan Aktif/Pasif: Leburkan repetisi pronomina subjek ganda ("ia dan suaminya", "mereka berdua")
   menjadi satu subjek terpadu yang wajar dalam bahasa Indonesia. Gunakan kalimat aktif untuk tindakan tokoh dan
   pasif kultural untuk anugerah/keluarga ("dikaruniai X anak").
6. Penataan Tanda Baca & Subjek Naratif: Ganti tanda titik dua (:) naratif menjadi tanda titik (.),
   depersonifikasikan waktu/dokumen ("1860s saw" -> "Pada dekade 1860-an"), dan rapikan tanda pisah em-dash
   menjadi koma aposisi atau klausa pembanding di awal kalimat.
7. Pembongkaran Penumpukan Tanda Koma: Jika draf lama memuat kalimat dengan lebih dari 2–3 tanda koma bertumpuk (keterangan waktu ganda + aposisi jabatan + kurung penjelas), pecah menjadi dua kalimat terpisah agar ritme baca tidak tersendat.
8. Penyelarasan Laras Bahasa & Warna Suara Kutipan:
   - Pada teks narasi: sesuaikan laras bahasa (sains = dingin dan presisi; sejarah = berwibawa dan kronologis; seni = mengalir dan apresiatif).
   - Pada kutipan langsung ("..."): jangan kaku menerjemahkan kata demi kata. Tangkap warna suara, sarkasme kritikus, metafora, dan emosi pembicara aslinya secara hidup dan luwes dalam bahasa Indonesia penutur asli.
9. Penghapusan Repetisi Pembuka Monoton (Anti-Monotony Anaphora):
   - Jika menemukan dua atau lebih kalimat berturut-turut yang diawali subjek yang sama (misalnya: "Film ini diproduseri... Film ini dibintangi...", atau "Ia lahir... Ia bersekolah..."), WAJIB lakukan variasi sintaktis:
     * Leburkan menjadi kalimat berpredikat majemuk atau klausa partisipial ("Disutradarai oleh X, film ini diproduseri oleh Y...").
     * Variasikan frasa rujukan ("Produksinya ditangani oleh...", "Jajaran pemeran utamanya menampilkan...", "Karya ini...", "Proyek ini...").
10. Eliminasi Kakofoni Enklitika "-nya" Beruntun:
    - Pangkas penumpukan kata berakhiran "-nya" yang berdampingan (misal "manusianya membuangnya" -> "kedua orang tuanya yang manusia menelantarkannya"). Gunakan konstruksi frasa relatif "yang [adjektiva/nomina]" dan verba bernas agar kalimat tidak terdengar berima canggung.
11. Restrukturisasi Aposisi Terbalik Bahasa Inggris:
    - Jika draf memuat pola terbalik "[Deskripsi/Peran], [Nama Orang], [Predikat]..." (misal: "Pemeran utama film animasinya, Auliʻi Cravalho, bertindak..."), WAJIB rekonstruksi ke susunan kanonis bahasa Indonesia: letakkan Nama Orang di depan sebagai Subjek Utama, diikuti keterangan penjelas diapit koma ("Auliʻi Cravalho, pemeran utama film animasinya, bertindak...").
"""

def build_polish_prompt(source_en: str, draft_id: str, *, topic: Optional[str] = None, glossary: Optional[Dict[str, str]] = None, context_notes: Optional[str] = None) -> str:
    """
    Builds a prompt for the 2nd pass Humanize / Polish editor mode.
    """
    glossary_text = "\n".join(f"- {en} → {id_}" for en, id_ in (glossary or {}).items()) or "(tidak ada)"
    context_text = context_notes or "(tidak ada; jangan menambah fakta)"
    return f"""### Bidang/topik: {topic or '(umum)'}

### Glosarium yang sudah disepakati:
{glossary_text}

### Konteks bagian sebelumnya (acuan istilah/pronomina, bukan sumber fakta baru):
{context_text}

### Teks Asli (Bahasa Inggris):
```wikitext
{source_en}
```

### Draf Terjemahan Bahasa Indonesia Saat Ini:
```wikitext
{draft_id}
```

### Instruksi Redaktur:
Periksa setiap klaim sebelum memoles: pelaku, objek, negasi, sebab-akibat, urutan waktu, angka, kutipan, modalitas (may/must), dan batas kepastian. Jangan menghapus atau menambah klaim. Gunakan glosarium hanya jika cocok dengan konteks. Pertahankan seluruh markup wikitext, isi rujukan, dan placeholder. Keluarkan HANYA hasil wikitext yang telah dipoles."""
