"""전체 파이프라인.

  python run.py                 # 자동: config.yaml schedule에 따라 지금 할 일만 (워크플로가 30분마다 실행)
  python run.py --now           # 지금 모든 소스 수집 + 대상일(기본: 어제) 바로 게재
  python run.py --schedule      # 현재 일정 설정만 출력
  python run.py --build-only    # 사이트만 다시 생성
  python run.py --resummarize   # 최근 게재일 해운물류 요약을 처음부터 다시
  python run.py --eurasia-resummarize
  python run.py --weekly        # 주간 리뷰(해운·유라시아) 지금 생성
  python run.py --backfill-geo  # 과거 기사에 국제정세 태깅 추가

워크플로는 실행 뒤 data/ 변경이 있을 때만 커밋·배포한다.
"""
import argparse
import logging
import sys

from src import build_site, collect, eurasia, eurasia_weekly, geo, schedule, summarize, weekly
from src.common import all_days, is_published, load_config, load_day, now_local, published_days, save_day

log = logging.getLogger("brief")


def unpublished_shipping() -> list[str]:
    return [d for d in all_days() if (load_day(d) or {}).get("published_at", "legacy") is None]


def unpublished_eurasia() -> list[str]:
    return [d for d in eurasia.all_edays() if (eurasia.load_eday(d) or {}).get("published_at", "legacy") is None]


def publish_shipping(d: str, force: bool = False) -> None:
    day = load_day(d)
    if not day or not day.get("articles"):
        return
    summarize.run(d, force=force)
    day = load_day(d)
    if not day.get("published_at"):
        day["published_at"] = now_local(load_config()).isoformat(timespec="seconds")
        save_day(d, day)
        log.info("해운물류 %s 게재 (%d건)", d, len(day["articles"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="일정과 관계없이 지금 수집하고 대상일을 게재")
    ap.add_argument("--schedule", action="store_true", help="일정 설정 출력")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--skip-eurasia", action="store_true")
    ap.add_argument("--resummarize", action="store_true")
    ap.add_argument("--eurasia-resummarize", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="주간 리뷰 강제 생성 (지난 7일)")
    ap.add_argument("--backfill-geo", action="store_true")
    ap.add_argument("--date", help="--resummarize 대상 날짜 (기본: 최근 게재일)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config()
    now = schedule.now(cfg)
    if args.schedule:
        print("\n".join(schedule.describe(cfg)))
        return 0
    for line in schedule.describe(cfg):
        log.info("일정 %s", line)

    if not args.build_only:
        st = schedule.load_state()
        sections = ["shipping"] + ([] if args.skip_eurasia else ["eurasia"])
        for sec in sections:
            try:
                # 1) 수집 — 시각이 지난 소스만 (--now면 전부)
                keys = schedule.source_keys(cfg, sec) if args.now else schedule.due_sources(cfg, st, now, sec)
                if keys:
                    start = schedule.window_start(cfg, st, now, keys)
                    log.info("[%s] 수집: %s (%s 이후 기사)", sec, ", ".join(keys), start.strftime("%m-%d %H:%M"))
                    (collect.sweep if sec == "shipping" else eurasia.sweep)(keys, start)
                    schedule.mark_collected(st, keys, now)
                    schedule.save_state(st)
                # 2) 게재 — 게재 시각이 지난 대상일(밀린 날 포함)
                pending = unpublished_shipping() if sec == "shipping" else unpublished_eurasia()
                due = schedule.publish_due(cfg, sec, now, pending)
                if args.now:
                    target = schedule.target_day(cfg, sec, now).isoformat()
                    due = sorted(set(due) | ({target} & set(pending)))
                # 이미 게재된 날에 늦게 들어온 기사 보충 (최근 3일)
                if sec == "shipping":
                    late = [d for d in published_days()[:3]
                            if any(not a.get("summary") for a in (load_day(d) or {}).get("articles", []))]
                    for d in sorted(set(due) | set(late)):
                        publish_shipping(d)
                else:
                    late = [d for d in eurasia.all_edays()[:4]
                            if is_published(eurasia.load_eday(d)) and (eurasia.load_eday(d) or {}).get("pending")]
                    for d in sorted(set(due) | set(late)):
                        eurasia.publish(d)
                # 3) 주간 리뷰 — 월요일 게재 시각 이후 1회 (지난주 월~일)
                if now.weekday() == 0 and now.time() >= schedule.publish_time(cfg, sec):
                    (weekly.run if sec == "shipping" else eurasia_weekly.run)(None, only_monday=True)
            except Exception:  # noqa: BLE001 — 한 섹션이 실패해도 다른 섹션과 배포는 계속
                log.exception("[%s] 처리 실패", sec)

        # 수동 옵션
        if args.resummarize:
            d = args.date or (published_days() or [None])[0]
            if d:
                summarize.run(d, force=True)
        if args.eurasia_resummarize and not args.skip_eurasia:
            pub = [d for d in eurasia.all_edays() if is_published(eurasia.load_eday(d))]
            d = args.date or (pub or [None])[0]
            if d:
                eurasia.publish(d, force=True)
        if args.backfill_geo:
            geo.backfill()
        if args.weekly:
            weekly.run(None)
            if not args.skip_eurasia:
                eurasia_weekly.run(None)

    build_site.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
