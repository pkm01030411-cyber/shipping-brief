"""전체 파이프라인 실행: 수집 → 요약 → 사이트 빌드.

  python run.py                 # 오늘자 전체 실행
  python run.py --skip-collect  # 수집 생략 (이미 모은 데이터로 요약·빌드)
  python run.py --skip-summarize
  python run.py --build-only    # 사이트만 다시 생성
  python run.py --resummarize   # 오늘 기사 요약을 처음부터 다시
  python run.py --date 2026-11-16
  python run.py --skip-eurasia  # 러시아·유라시아 섹션 건너뜀
  python run.py --eurasia-only  # 러시아·유라시아 섹션만 (수집·요약 → 빌드)
"""
import argparse
import logging
import sys

from src import build_site, collect, eurasia, eurasia_weekly, geo, summarize, weekly


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--skip-summarize", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--resummarize", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="주간 리뷰 강제 생성 (지난 7일)")
    ap.add_argument("--weekly-if-monday", action="store_true", help="월요일이면 지난주 리뷰 생성 (워크플로용)")
    ap.add_argument("--skip-eurasia", action="store_true", help="러시아·유라시아 섹션 건너뜀")
    ap.add_argument("--eurasia-only", action="store_true", help="러시아·유라시아 섹션만 실행")
    ap.add_argument("--eurasia-resummarize", action="store_true", help="오늘 유라시아 기사 요약을 처음부터 다시")
    ap.add_argument("--backfill-geo", action="store_true", help="geo 태깅이 없는 과거 기사에 국제정세 태깅만 추가")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.build_only and not args.eurasia_only:
        if not args.skip_collect:
            collect.run(args.date)
        if not args.skip_summarize:
            target = args.date
            if args.resummarize and not target:
                # 오늘 파일이 없으면(새 기사 0건) 가장 최근 브리핑을 다시 요약
                from src.common import all_days, load_day, today_str, load_config
                today = today_str(load_config())
                if not (load_day(today) or {}).get("articles"):
                    days = all_days()
                    target = days[0] if days else None
            summarize.run(target, force=args.resummarize)
        if args.backfill_geo:
            geo.backfill()
        if args.weekly:
            weekly.run(args.date)
        elif args.weekly_if_monday:
            weekly.run(args.date, only_monday=True)
    if not args.build_only and not args.skip_eurasia:
        # 별도 섹션 — 실패해도 해운물류 브리핑 배포는 계속
        try:
            eurasia.run(args.date, force=args.eurasia_resummarize)
            if args.weekly:
                eurasia_weekly.run(args.date)
            elif args.weekly_if_monday:
                eurasia_weekly.run(args.date, only_monday=True)
        except Exception:  # noqa: BLE001
            logging.getLogger("brief").exception("러시아·유라시아 섹션 실패 — 해운물류 브리핑은 그대로 배포")
    build_site.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
