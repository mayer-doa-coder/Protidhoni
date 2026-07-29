import asyncio
import sys

import uvicorn


async def _serve() -> None:
    config = uvicorn.Config(
        "protidhoni_api.main:app",
        host="127.0.0.1",
        port=8000,
    )
    await uvicorn.Server(config).serve()


def main() -> None:
    # Psycopg's async implementation cannot use Windows' default Proactor loop.
    # Passing a factory is the non-deprecated Python 3.12+ way to select the
    # compatible loop without changing process-global asyncio policy.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(_serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
