#!/usr/bin/env python3
"""
Diagnostic, seed, and cache maintenance tool for Kateglo dictionary and thesaurus data.

Usage:
  python scripts/seed_kateglo.py --health-check
  python scripts/seed_kateglo.py --stats
  python scripts/seed_kateglo.py --words "demokrasi, perestroika, transparansi, reformasi"
  python scripts/seed_kateglo.py --random 20
  python scripts/seed_kateglo.py --search "hukum"
  python scripts/seed_kateglo.py --clear
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wiki_translator.kateglo_client import default_kateglo_client


def main():
    parser = argparse.ArgumentParser(description="Kateglo Dictionary & Thesaurus Maintenance Utility")
    parser.add_argument("--health-check", action="store_true", help="Test live connectivity, endpoint availability, and latency to kateglo.org API")
    parser.add_argument("--stats", action="store_true", help="Display local cache statistics (entries, thesaurus, glossaries)")
    parser.add_argument("--words", type=str, help="Comma-separated list of Indonesian words to fetch and cache")
    parser.add_argument("--random", type=int, default=0, help="Fetch N random words from Kateglo to seed cache")
    parser.add_argument("--search", type=str, help="Search lemmas matching keyword")
    parser.add_argument("--force", action="store_true", help="Force refresh even if already cached")
    parser.add_argument("--clear", action="store_true", help="Clear all local Kateglo cache tables")

    args = parser.parse_args()

    client = default_kateglo_client

    if args.health_check:
        print("[*] Testing live connectivity to Kateglo API...")
        health = client.health_check()
        print(f"  Status   : {'[✔] HEALTHY' if health['healthy'] else '[!] UNHEALTHY / DOWN'}")
        print(f"  Latency  : {health['latency_ms']} ms")
        print(f"  Endpoint : {health['endpoint']}")
        if health.get("sample_response"):
            print(f"  Sample   : {health['sample_response']}")
        return

    if args.stats:
        stats = client.get_cache_stats()
        print("[*] Local Kateglo Cache Statistics:")
        print(f"  Database Path      : {client.cache_db_path}")
        print(f"  Cached Entries     : {stats['entries_cached']:,}")
        print(f"  Cached Thesaurus   : {stats['thesaurus_cached']:,}")
        print(f"  Bilingual Glossary : {stats['glossary_pairs_cached']:,} pairs")
        return

    if args.clear:
        ok = client.clear_cache()
        print(f"[*] Clearing cache: {'[✔] Succeeded' if ok else '[!] Failed'}")
        return

    if args.words:
        word_list = [w.strip() for w in args.words.split(",") if w.strip()]
        print(f"[*] Fetching and caching {len(word_list)} words from Kateglo (force={args.force})...")
        for w in word_list:
            detail = client.get_entry_detail(w, force_refresh=args.force)
            synonyms = client.get_synonyms(w, force_refresh=args.force)
            if detail:
                entries = client._extract_entries_defensively(detail)
                sumber = entries[0].get("sumber_kode", "KBBI") if entries else "KBBI"
                print(f"  [+] {w:20} -> {sumber} | {len(synonyms)} sinonim")
            else:
                print(f"  [-] {w:20} -> Tidak ditemukan")

    if args.random > 0:
        print(f"[*] Fetching {args.random} random lemmas from Kateglo...")
        for i in range(args.random):
            acak = client._api_get("kamus/acak")
            if acak and "indeks" in acak:
                lema = acak["indeks"]
                detail = client.get_entry_detail(lema, force_refresh=args.force)
                synonyms = client.get_synonyms(lema, force_refresh=args.force)
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
