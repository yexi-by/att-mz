"""开发态命令行启动入口。

发布包通过 `app.cli_main:main` 作为标准 console script 入口；保留本文件是为了
兼容既有 `uv run python main.py ...` 的开发和文档命令。
"""

from __future__ import annotations

from app.cli_main import main

__all__: list[str] = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
