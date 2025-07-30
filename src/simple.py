# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "datastar-py",
#     "python-fasthtml",
# ]
# [tool.uv.sources]
# datastar-py = { path = "../../" }
# ///
import asyncio
import capnp
import json
from datetime import datetime
from hypercorn.asyncio import serve as hc_serve
from hypercorn.config import Config as HcConfig
import os
import sys
import zalfmas_common.common as mas_common
import zalfmas_capnp_schemas
sys.path.append(os.path.dirname(zalfmas_capnp_schemas.__file__))
import climate_capnp

# ruff: noqa: F403, F405
from fasthtml.common import *
from fasthtml import ft
import uvicorn

from datastar_py.fasthtml import DatastarResponse, ServerSentEventGenerator as SSE, read_signals
from datastar_py.consts import ElementPatchMode

app, rt = fast_app(
    htmx=False,
    surreal=False,
    live=True,
    hdrs=(
        Script(
            type="module",
            src="https://cdn.jsdelivr.net/gh/starfederation/datastar@main/bundles/datastar.js",
        ),
    ),
)

example_style = Style(
    "html, body { height: 100%; width: 100%; } h1 { color: #ccc; text-align: center } body { background-image: linear-gradient(to right bottom, oklch(0.424958 0.052808 253.972015), oklch(0.189627 0.038744 264.832977)); } .container { display: grid; place-content: center; } .time { padding: 2rem; border-radius: 8px; margin-top: 3rem; font-family: monospace, sans-serif; background-color: oklch(0.916374 0.034554 90.5157); color: oklch(0.265104 0.006243 0.522862 / 0.6); font-weight: 600; }"
)


@rt("/")
async def index():
    now = datetime.isoformat(datetime.now())
    return Titled(
        "Datastar FastHTML example",
        example_style,
        Body(data_signals=json.dumps({"currentTime": now}))(
            Div(cls="container")(
                Div(data_on_load="@get('/updates')", cls="time")(
                    "Current time from element: ",
                    Span(id="currentTime")(now),
                ),
                Div(cls="time")(
                    "Current time from signal: ",
                    Span(data_text="$currentTime")(now),
                ),
                Button("press me",
                       {"data-on-click__once": "@get('/timeseries')"}),
                Div(id="data")(
                    H3("Data")
                ),
            ),
        ),
    )


async def clock():
    while True:
        now = datetime.isoformat(datetime.now())
        yield SSE.patch_elements(Span(id="currentTime")(now))
        await asyncio.sleep(1)
        yield SSE.patch_signals({"currentTime": f"{now}"})
        await asyncio.sleep(1)


@app.get("/updates")
#@datastar_response
async def updates(request):
    signals = await read_signals(request)
    print(signals)
    return DatastarResponse(clock())

con_man = mas_common.ConnectionManager()
async def timeseries2():
    sr = "capnp://localhost:8888/timeseries"
    ts = await con_man.connect(sr, cast_as=climate_capnp.TimeSeries)
    header = await ts.header()
    for h in header.header:
        yield SSE.patch_elements(Div(h),
                                 selector="#headers",
                                 mode=ElementPatchMode.APPEND)
        #await asyncio.sleep(1)
    data = await ts.data()
    yield SSE.patch_elements(
        Div(id="data")(
            Table(cls="striped")(
                Thead(*[Th(str(h), scope="col") for h in header.header]),
                Tbody(id="tbody")
            )
        )
    )
    for d in data.data:
        row = []
        for i, _ in enumerate(header.header):
            row.append(Td(d[i]))
        yield SSE.patch_elements(Tr(*row),
                                 selector="#tbody",
                                 mode=ElementPatchMode.APPEND)


@app.get("/timeseries")
async def timeseries(request):
    signals = await read_signals(request)
    print(signals)
    return DatastarResponse(timeseries2())

if __name__ == "__main__":
    #via hypercorn
    #if False:
    #    config = HcConfig()
    #    config.bind = ["0.0.0.0:8080"]
    #    config.startup_timeout = 1200
    #    config.root_path = "/"
    #    asyncio.run(capnp.run(hc_serve(app, config)))

    #via uvicorn directly
    #if False:
    #    uvicorn.run("simple:app", host="0.0.0.0", port=8080, reload=True, reload_includes=None,
    #                reload_excludes=None)

    #via uvicorn
    config = uvicorn.Config(
        "simple:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
    server = uvicorn.Server(config=config)
    if config.should_reload:
        sock = config.bind_socket()
        from uvicorn.supervisors.watchfilesreload import WatchFilesReload as ChangeReload
        ChangeReload(config, target=server.run, sockets=[sock]).run()
        #def my_run(sockets):
        #    server.config.setup_event_loop()
        #    asyncio.run(capnp.run(server.serve(sockets=sockets)))
        #ChangeReload(config, target=my_run, sockets=[sock]).run()
    else:
        server.config.setup_event_loop()
        #asyncio.run(server.serve(sockets=None))
        asyncio.run(capnp.run(server.serve(sockets=None)))
        #server.run()

    #via fasthtml via uvicorn
    #    serve()
