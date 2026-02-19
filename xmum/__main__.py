"""CLI 入口，同时支持 ``python -m xmum`` 调用方式。"""

import argparse

from dotenv import load_dotenv

from .commands import cmd_dump, cmd_grab, cmd_query


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="XMUM 小学期选课工具")
    parser.add_argument("--dump", action="store_true", help="保存原始 HTML（调试用）")
    sub = parser.add_subparsers(dest="command")

    q = sub.add_parser("query", help="查询所有课程余量")
    q.add_argument("--dump", action="store_true", help="同时保存原始 HTML")

    g = sub.add_parser("grab", help="从 config.json 读取目标课程并自动抢课")
    g.add_argument("--interval", type=float, default=5,
                   help="轮询间隔秒数（默认 5 秒）")
    g.add_argument("--rush", action="store_true",
                   help="急速模式：约 0.3 秒一轮")

    args = parser.parse_args()

    if args.command is None:
        if args.dump:
            cmd_dump(args)
        else:
            parser.print_help()
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "grab":
        cmd_grab(args)


if __name__ == "__main__":
    main()
