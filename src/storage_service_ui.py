from aiostream import stream as aios
import asyncio
from collections import defaultdict
import capnp
import json
from datetime import datetime
import os
import sys
import uuid
import zalfmas_common.common as mas_common
import zalfmas_capnp_schemas
sys.path.append(os.path.dirname(zalfmas_capnp_schemas.__file__))
import storage_capnp
import fasthtml_components as c

# ruff: noqa: F403, F405
from fasthtml.common import *
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

@rt("/")
async def index():
    return Titled(
        "Storage service management",
        Body()(
            Article(data_signals="{'srConnected': false, 'connectionInvalid': false}")(
                Fieldset(role="group")(
                    #Label("Sturdy Ref")(
                    Input(placeholder="Enter a Storage Service Sturdy Ref here",
                          data_bind="sr",
                          type="text",
                          data_attr="{'aria-invalid': $connectionInvalid}"),
                        #Small("Copy here the sturdy ref to your storage service"),
                    #),
                    Button(data_text="$srConnected ? 'Connected' : 'Connect'",
                           data_on_click="@post('/connect')")
                )
            ),
            Article(id="containers", data_show="$srConnected")(
                P(id="no_container_placeholder")("no containers available")
            )
        ),
    )

all_user_data = defaultdict(dict)
con_man = mas_common.ConnectionManager()

@app.post("/connect")
async def connect(request, session: dict):
    signals = await read_signals(request)
    sr = signals.get("sr", None)
    if sr:
        user_id = session.setdefault("user_id", str(uuid.uuid4()))
        user_data = all_user_data[user_id]
        if ("sr" not in user_data
                or user_data["sr"] != sr
                or "cap" not in user_data):
            try:
                cap = await con_man.try_connect(sr, cast_as=storage_capnp.Store)
                user_data["cap"] = cap
                user_data["id_to_container_cap"] = {}
                list_container_patches = [
                    SSE.patch_elements(el,
                                       selector="#containers",
                                       mode=ElementPatchMode.APPEND)
                    for el in await list_containers(cap, user_data["id_to_container_cap"])]
                return DatastarResponse(
                    itertools.chain([
                        SSE.patch_signals({"srConnected": True,
                                           "connectionInvalid": "false"}),
                        SSE.patch_elements(selector="#no_container_placeholder",
                                           mode=ElementPatchMode.REMOVE)
                    ], list_container_patches)
                )
            except capnp.KjException as e:
                print(e)
    return DatastarResponse(
        SSE.patch_signals({"srConnected": False,
                           "connectionInvalid": "true"}),
    )


async def list_containers(storage_service_cap, id_to_container_cap):
    patches = []
    try:
        cs = (await storage_service_cap.listContainers()).containers
        for c in cs:
            id_to_container_cap[c.id] = c.container
            patches.append(
                Details(
                    Summary(H4(c.name),
                            open=False,
                            data_on_click=f"@get('/containers/{c.id}')"),
                    Article(id=f"c_{c.id}")("-----")
                )
            )
            patches.append(Hr())
    except capnp.KjException as e:
        print(e)
    return patches


@app.get("/containers/{container_id}")
async def get_container(request, session, container_id: str):
    signals = await read_signals(request)
    user_id = session.get("user_id", None)
    if user_id:
        user_data = all_user_data[user_id]
        if container_id in user_data.get("id_to_container_cap", {}):
            c = user_data["id_to_container_cap"][container_id]
            try:
                entries = (await c.listEntries()).entries
                return DatastarResponse(SSE.patch_elements(
                    Table(cls="striped")(
                        Thead(Tr(Th("Key"), Th("Value"), Th("Actions"))),
                        Tbody(*[
                            Tr(Td(e.key), Td("---"), Td(Button("Edit"), Button("Delete")))
                            for e in entries
                        ])
                    ),
                    selector=f"#c_{container_id}",
                    mode=ElementPatchMode.INNER))
            except capnp.KjException as e:
                print(e)
    return DatastarResponse()


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
#c.new_sturdy_ref_handler(app, route="/add_sturdy_ref")

#@app.delete("/add_sturdy_ref")
#async def add_sturdy_ref(request):
#    signals = await read_signals(request)
#    print(signals)
#    return DatastarResponse(SSE.patch_elements(
#        selector="#add_sr_dialog",
#        mode=ElementPatchMode.REMOVE,
#    ))

#@app.get("/updates")
#async def updates(request):
#    signals = await read_signals(request)
#    print(signals)
#    return DatastarResponse(clock())

#con_man = mas_common.ConnectionManager()
#async def timeseries2():
#    sr = "capnp://localhost:8888/timeseries"
#    ts = await con_man.connect(sr, cast_as=climate_capnp.TimeSeries)
#    header = await ts.header()
#    for h in header.header:
#        yield SSE.patch_elements(Div(h),
#                                 selector="#headers",
#                                 mode=ElementPatchMode.APPEND)
#        #await asyncio.sleep(1)
#    data = await ts.data()
#    yield SSE.patch_elements(
#        Div(id="data")(
#            Table(cls="striped")(
#                Thead(*[Th(str(h), scope="col") for h in header.header]),
#                Tbody(id="tbody")
#            )
#        )
#    )
#    for d in data.data:
#        row = []
#        for i, _ in enumerate(header.header):
#            row.append(Td(d[i]))
#        yield SSE.patch_elements(Tr(*row),
#                                 selector="#tbody",
#                                 mode=ElementPatchMode.APPEND)


#@app.get("/timeseries")
#async def timeseries(request):
#    signals = await read_signals(request)
#    print(signals)
#    return DatastarResponse(timeseries2())

if __name__ == "__main__":
    #via uvicorn
    config = uvicorn.Config(
        "storage_service_ui:app",
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
