"""전체 파이프라인 실행: 수집 → 요약 → 사이트 빌드.

  python run.py                 # 오늘자 전체 실행
  python run.py --skip-collect  # 수집 생략 (이미 모은 데이터로 요약·빌드)
  python run.py --skip-summarize
  python run.py --build-only    # 사이트만 다시 생성
  python run.py --resummarize   # 오늘 기사 요약을 처음부터 다시
  python run.py --date 2026-11-16
"""
import argparse
import logging
import sys

from src import build_site, collect, summarize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--skip-summarize", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--resummarize", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.build_only:
        if not args.skip_collect:
            collect.run(args.date)
        if not args.skip_summarize:
            summarize.run(args.date, force=args.resummarize)
    build_site.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
