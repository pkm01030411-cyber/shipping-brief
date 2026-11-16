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

from src import build_site, collect, summarize, weekly


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--skip-summarize", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--resummarize", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="주간 리뷰 강제 생성 (지난 7일)")
    ap.add_argument("--weekly-if-monday", action="store_true", help="월요일이면 지난주 리뷰 생성 (워크플로용)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.build_only:
        if not args.skip_collect:
            collect.run(args.date)
        if not args.skip_summarize:
            summarize.run(args.date, force=args.resummarize)
        if args.weekly:
            weekly.run(args.date)
        elif args.weekly_if_monday:
            weekly.run(args.date, only_monday=True)
    build_site.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
