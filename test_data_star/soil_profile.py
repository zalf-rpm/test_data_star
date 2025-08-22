import asyncio
import capnp
import json
from datetime import datetime
import os
import sys
import zalfmas_common.common as mas_common
import zalfmas_capnp_schemas
sys.path.append(os.path.dirname(zalfmas_capnp_schemas.__file__))
import climate_capnp
import soil_capnp
import fasthtml_components as c

# ruff: noqa: F403, F405
from fasthtml.common import *
#from monsterui.all import *
from fasthtml import ft
import uvicorn

from datastar_py.fasthtml import DatastarResponse, ServerSentEventGenerator as SSE, read_signals
from datastar_py.consts import ElementPatchMode
import datastar_py

app, rt = fast_app(
    secret_key="your-secret-key-here",
    htmx=False,
    surreal=False,
    live=True,
    hdrs=(
        #Theme.blue.headers(highlightjs=True),
        Script(
            type="module",
            src="https://cdn.jsdelivr.net/gh/starfederation/datastar@main/bundles/datastar.js",
        ),
    ),
)

dyn_routes = []

example_style = Style(
    """
html, body { height: 100%; width: 100%; } 
h1 { color: #ccc; text-align: center } 
body { 
    background-image: linear-gradient(
        to right bottom, 
        oklch(0.424958 0.052808 253.972015), 
        oklch(0.189627 0.038744 264.832977)
    ); 
} 
.container { display: grid; place-content: center; } 
.time { 
    padding: 2rem; 
    border-radius: 8px; 
    margin-top: 3rem; 
    font-family: monospace, sans-serif; 
    background-color: oklch(0.916374 0.034554 90.5157); 
    color: oklch(0.265104 0.006243 0.522862 / 0.6); 
    font-weight: 600; 
}
    """
)

@rt("/")
async def index():
    return Titled(
        "Soil profile viewer",
        #example_style,
        Body()(
            c.SoilService(),
        ),
    )

#@app.get("/add_sturdy_ref")
#async def add_sturdy_ref(request):
#    signals = await read_signals(request)
#    print(signals)
#    return DatastarResponse(SSE.patch_elements(
#        c.AddSturdyRef(),
#        selector="body",
#        mode=ElementPatchMode.PREPEND,
#    ))

#dyn_routes.append(c.new_sturdy_ref_handler(app, route="/add_sturdy_ref"))
c.new_sturdy_ref_handler(app, route="/add_sturdy_ref")

@app.delete("/add_sturdy_ref")
async def add_sturdy_ref(request):
    signals = await read_signals(request)
    print(signals)
    return DatastarResponse(SSE.patch_elements(
        selector="#add_sr_dialog",
        mode=ElementPatchMode.REMOVE,
    ))

#@app.get("/updates")
#async def updates(request):
#    signals = await read_signals(request)
#    print(signals)
#    return DatastarResponse(clock())

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
    #via uvicorn
    config = uvicorn.Config(
        "soil_profile:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
    )
    server = uvicorn.Server(config=config)
    if config.should_reload:
        sock = config.bind_socket()
        from uvicorn.supervisors.watchfilesreload import WatchFilesReload as ChangeReload
        ChangeReload(config, target=server.run, sockets=[sock]).run()
    else:
        server.config.setup_event_loop()
        asyncio.run(capnp.run(server.serve(sockets=None)))
