import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import API_KEY, BIND_HOST, BIND_PORT, DASHBOARD_PASSWORD
from usage import init_db, purge_old_requests
from routes_openai import router as openai_router
from routes_dashboard import router as dashboard_router


async def _purge_loop() -> None:
    """Delete usage_requests rows older than 30 days; runs at startup then every 24 h."""
    while True:
        try:
            deleted = await asyncio.to_thread(purge_old_requests, 30)
            if deleted:
                print(f"[traepilot] purged {deleted} request log row(s) older than 30 days")
        except Exception as exc:
            print(f"[traepilot] purge error (non-fatal): {exc}")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(_purge_loop())
    _local = ("127.0.0.1", "localhost", "::1")
    if BIND_HOST not in _local and not API_KEY and not DASHBOARD_PASSWORD:
        print(
            "\n*** WARNING: TraePilot is bound to a non-local interface "
            f"({BIND_HOST}) with no API_KEY or DASHBOARD_PASSWORD set. "
            "The proxy is completely unauthenticated — anyone on the network "
            "can use it. Set API_KEY and/or DASHBOARD_PASSWORD in your .env. ***\n"
        )
    yield


app = FastAPI(title="TraePilot", version="0.3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(openai_router)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn
    _host_disp = "localhost" if BIND_HOST in ("127.0.0.1", "0.0.0.0", "::1") else BIND_HOST
    _base = f"http://{_host_disp}:{BIND_PORT}"
    _title = f"TraePilot  v{app.version}"
    _w = 46
    _bar = "-" * _w
    print(f"\n  +{_bar}+")
    print(f"  |  {_title:<{_w - 2}}|")
    print(f"  +{_bar}+\n")
    print(f"  Proxy      {_base}/v1")
    print(f"  Dashboard  {_base}/dashboard\n")
    uvicorn.run("main:app", host=BIND_HOST, port=BIND_PORT, reload=False)
