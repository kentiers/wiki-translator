#!/usr/bin/env python3
"""
Seed and cache tool for Kateglo dictionary and thesaurus data.

Usage:
  python scripts/seed_kateglo.py --words "demokrasi, perestroika, transparansi, reformasi"
  python scripts/seed_kateglo.py --random 20
  python scripts/seed_kateglo.py --search "hukum"
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wiki_translator.kateglo_client import default_kateglo_client

def main():
    parser = argparse.ArgumentParser(description="Kateglo Dictionary & Thesaurus Seed Utility")
    parser.add_argument("--words", type=str, help="Comma-separated list of Indonesian words to fetch and cache")
    parser.add_argument("--random", type=int, default=0, help="Fetch N random words from Kateglo to seed cache")
    parser.add_argument("--search", type=str, help="Search lemmas matching keyword")

    args = parser.parse_args()

    client = default_kateglo_client

    if args.words:
        word_list = [w.strip() for w in args.words.split(",") if w.strip()]
        print(f"[*] Fetching and caching {len(word_list)} words from Kateglo...")
        for w in word_list:
            detail = client.get_entry_detail(w)
            synonyms = client.get_synonyms(w)
            if detail:
                entri = detail.get("entri", [])
                sumber = entri[0].get("sumber_kode", "KBBI") if entri else "KBBI"
                print(f"  [+] {w:20} -> {sumber} | {len(synonyms)} sinonim")
            else:
                print(f"  [-] {w:20} -> Tidak ditemukan")

    if args.random > 0:
        print(f"[*] Fetching {args.random} random lemmas from Kateglo...")
        for i in range(args.random):
            acak = client._api_get("kamus/acak")
            if acak and "indeks" in acak:
                lema = acak["indeks"]
                detail = client.get_entry_detail(lema)
                synonyms = client.get_synonyms(lema)
                print(f"  [{i+1}/{args.random}] {lema:20} -> {len(synonyms)} sinonim")

    if args.search:
        print(f"[*] Searching Kateglo for '{args.search}'...")
        res = client._api_get(f"kamus/cari/{args.search}")
        if res and "data" in res:
            items = res["data"]
            print(f"[+] Found {len(items)} matching entries:")
            for it in items[:10]:
                print(f"  - {it.get('entri')} ({it.get('jenis', 'dasar')})")

    print("[✔] Done! Cache saved at data/kateglo_cache.sqlite")


if __name__ == "__main__":
    main()
