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
            container_c_id = f"c_{c.id}"
            id_to_container_cap[container_c_id] = c.container
            patches.append(
                Details(
                    Summary(H4(c.name),
                            open=False,
                            data_on_click=f"@get('/containers/{container_c_id}')"),
                    Article(id=f"{container_c_id}")("-----")
                )
            )
            patches.append(Hr())
    except capnp.KjException as e:
        print(e)
    return patches

css_id_count = {"count": 0}
def get_css_id_from_user_data(user_id, long_id: str):
    if user_id:
        user_data = all_user_data[user_id]
        css_ids = user_data.setdefault("css_ids", {})
        if long_id in css_ids:
            return css_ids[long_id]
        else:
            css_id_count["count"] += 1
            css_ids[long_id] = f"id_{css_id_count['count']}"
            return css_ids[long_id]
    return None


def get_container_from_user_data(user_id, container_c_id):
    if user_id:
        user_data = all_user_data[user_id]
        if container_c_id in user_data.get("id_to_container_cap", {}):
            return user_data["id_to_container_cap"][container_c_id]
    return None

@app.get("/containers/{container_c_id}")
async def get_container(request, session, container_c_id: str):
    signals = await read_signals(request)
    user_id = session.get("user_id", None)
    container = get_container_from_user_data(user_id, container_c_id)
    if not container: return DatastarResponse()

    try:
        entries = (await container.listEntries()).entries
        rows = []
        for entry in entries:
            css_id = get_css_id_from_user_data(user_id, f"{container_c_id}.e_{entry.key}")
            rows.append(
                Tr()(
                    Td(entry.key),
                    Td(id=f"{css_id}")("---"),
                    Td()(
                        Button("Edit", data_on_click=f"@get('/containers/{container_c_id}/entries/e_{entry.key}')"),
                        Button("Delete", data_on_click=f"@delete('/containers/{container_c_id}/entries/e_{entry.key}')")
                    )
                )
            )
        return DatastarResponse(SSE.patch_elements(
            Table(cls="striped")(
                Thead(Tr(Th("Key"), Th("Value"), Th("Actions"))),
                Tbody(*rows)
            ),
            selector=f"#{container_c_id}",
            mode=ElementPatchMode.INNER
        ))
    except capnp.KjException as e:
        print(e)
    return DatastarResponse()


@app.get("/containers/{container_c_id}/entries/{entry_e_key}")
async def get_entry(request, session, container_c_id: str, entry_e_key: str):
    signals = await read_signals(request)
    user_id = session.get("user_id", None)
    container = get_container_from_user_data(user_id, container_c_id)
    if not container: return DatastarResponse()

    try:
        v = await container.getEntry(entry_e_key).entry.getValue()
        css_id = get_css_id_from_user_data(user_id, f"{container_c_id}.{entry_e_key}")
        return DatastarResponse(SSE.patch_elements(
            storage_input_field(container_c_id, entry_e_key,
                                f"/containers/{container_c_id}/entries/{entry_e_key}",
                                v.value),
            selector=f"#{css_id}",
            mode=ElementPatchMode.INNER
        ))
    except capnp.KjException as e:
        print(e)
    return DatastarResponse()

@app.put("/containers/{container_c_id}/entries/{entry_e_key}/{value_type}")
async def get_entry(request, session, container_c_id: str, entry_e_key: str, value_type: str):
    signals = await read_signals(request)
    new_value = signals.get(container_c_id, {}).get(entry_e_key, None)
    if not new_value: return DatastarResponse()

    user_id = session.get("user_id", None)
    container = get_container(user_id, container_c_id)
    if not container: return DatastarResponse()

    try:
        entry_prom = container.getEntry(entry_e_key).entry
        success = await entry_prom.setValue({value_type: new_value})
    except capnp.KjException as e:
        print(e)
    return DatastarResponse()


def storage_input_field(container_c_id, entry_e_key, update_route: str,
                        stor_val: storage_capnp.Store.Container.Entry.Value):
    val_type = stor_val.which()
    if val_type == "boolValue":
        return Input(type="checkbox",
                     data_signals=f"{{'{container_c_id}.{entry_e_key}.boolValueInvalid': false}}",
                     data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.boolValueInvalid}}",
                     data_bind=f"{container_c_id}.{entry_e_key}.boolValue",
                     data_on_change=f"@put('{update_route}/boolValue')")
    elif val_type == "int8Value":
        return Input(type="number",
                     min=-2**7,
                     max=2**7 - 1,
                     data_signals=f"{{'{container_c_id}.{entry_e_key}.int8ValueInvalid': false}}",
                     data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.int8ValueInvalid}}",
                     data_bind=f"{container_c_id}.{entry_e_key}.int8Value",
                     data_on_change=f"@put('{update_route}/int8Value')")
    elif val_type == "uint8Value":
        return Input(type="number",
                     min=0,
                     max=2 ** 8 - 1,
                     data_signals=f"{{'{container_c_id}.{entry_e_key}.uint8ValueInvalid': false}}",
                     data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.uint8ValueInvalid}}",
                     data_bind=f"{container_c_id}.{entry_e_key}.uint8Value",
                     data_on_change=f"@put('{update_route}/uint8Value')")
    elif val_type == "int16Value":
        return Input(type="number",
                     min=-2**15,
                     max=2**15 - 1,
                     data_signals=f"{{'{container_c_id}.{entry_e_key}.int16ValueInvalid': false}}",
                     data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.int16ValueInvalid}}",
                     data_bind=f"{container_c_id}.{entry_e_key}.int16Value",
                     data_on_change=f"@put('{update_route}/int16Value')")
    elif val_type == "uint16Value":
        return Input(type="number",
                     min=0,
                     max=2**16 - 1,
                     data_signals=f"{{'{container_c_id}.{entry_e_key}.uint16ValueInvalid': false}}",
                     data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.uint16ValueInvalid}}",
                     data_bind=f"{container_c_id}.{entry_e_key}.uint16Value",
                     data_on_change=f"@put('{update_route}/uint16Value')")
    return Input()

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
