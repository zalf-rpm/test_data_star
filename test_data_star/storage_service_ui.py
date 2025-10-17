#from aiostream import stream as aios
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

# ruff: noqa: F403, F405
#import uvicorn

from hypercorn.asyncio import serve as hc_serve
from hypercorn.config import Config as HcConfig
#
# from datastar_py.fasthtml import (
#     DatastarResponse,
#     ServerSentEventGenerator as SSE,
#     read_signals,
# )
# from datastar_py.consts import ElementPatchMode
# import datastar_py
from starhtml import *

app, rt = star_app(
    title="Storage service management",
    secret_key="your-secret-key-here",
    live=False,
    # hdrs=(
    #     # Theme.blue.headers(highlightjs=True),
    #     #Script(
    #     #    type="module",
    #     #    src="https://cdn.jsdelivr.net/gh/starfederation/datastar@main/bundles/datastar.js",
    #     #),
    # ),
)

dyn_routes = []

# @rt("/")
# def home():
#     return Div(
#         H1("StarHTML Demo"),
#
#         # Define reactive state with signals
#         Div(
#             (counter := Signal("counter", 0)),  # Python-first signal definition
#
#             # Reactive UI that updates automatically
#             P("Count: ", Span(data_text=counter)),
#             Button("+", data_on_click=counter.add(1)),
#             Button("Reset", data_on_click=counter.set(0)),
#
#             # Conditional styling
#             data_class_active=counter > 0
#         ),
#
#         # Server-side interactions
#         Button("Load Data", data_on_click=get("/api/data")),
#         Div(id="content")
#     )

@rt("/api/data")
def api_data():
    return Div("Data loaded from server!", id="content")

#serve()

connection_invalid = Signal("connection_invalid", False)
sturdy_ref = Signal("sturdy_ref", "capnp://UsDvHic7pWXb5R7e1HTFwNB5kKhqZEflZp9_Srbjq4Q@10.10.28.186:45195/769e56cf-ddad-4b60-b636-174bf035bc16")
#data = Signal("data", {"c_1": {"e_1": "bla", "e_2": "bli"}, "c_2": {"e_1": "bla2", "e_2": "bli2"}})

@app.get("/")
async def index():
    # return Div(
    #     H1("StarHTML Demo"),
    #
    #     # Define reactive state with signals
    #     Div(
    #         (counter := Signal("counter", 0)),  # Python-first signal definition
    #
    #         # Reactive UI that updates automatically
    #         P("Count: ", Span(data_text=counter)),
    #         Button("+", data_on_click=counter.add(1)),
    #         Button("Reset", data_on_click=counter.set(0)),
    #
    #         # Conditional styling
    #         data_class_active=counter > 0
    #     ),
    #
    #     # Server-side interactions
    #     Button("Load Data", data_on_click=get("/api/data")),
    #     Div(id="content")
    # )
    return Div(
        Article(
            (sr_connected := Signal("sr_connected", False)),
            connection_invalid,
            sturdy_ref,
            Fieldset(role="group")(
                # Label("Sturdy Ref")(
                Input(
                    placeholder="Enter a Storage Service Sturdy Ref here",
                    data_bind=sturdy_ref,
                    type="text",
                    data_attr_aria_invalid=connection_invalid, #"{'aria-invalid': $connectionInvalid}",
                ),
                # Small("Copy here the sturdy ref to your storage service"),
                # ),
                Button(
                    data_text=sr_connected.if_("Connected", "Connect"), #"$sr_connected ? 'Connected' : 'Connect'",
                    data_on_click=post('/connect'),
                ),
            )
        ),
        Pre(data_json_signals=True),
        Article(id="containers", data_show=sr_connected)(
            P(id="no_container_placeholder")("no containers available")
        ),
    )


all_user_data = defaultdict(dict)
con_man = mas_common.ConnectionManager()


@app.post("/connect")
@sse
async def connect(request, sturdy_ref: str, session: dict):
    if len(sturdy_ref) == 0:
        yield signals(sr_connected=False, connection_invalid=True)
        return
    user_id = session.setdefault("user_id", str(uuid.uuid4()))
    user_data = all_user_data[user_id]
    if "sturdy_ref" not in user_data or user_data["sturdy_ref"] != sturdy_ref or "cap" not in user_data:
        try:
            cap = await con_man.try_connect(sturdy_ref, cast_as=storage_capnp.Store)
            user_data["cap"] = cap
            user_data["id_to_container_cap"] = {}
            user_data["data"] = defaultdict(dict) # container id to entry id to data
            yield signals(sr_connected=True, connection_invalid=False)
            yield elements(None, "#no_container_placeholder", "remove")
            for el in await list_containers(cap, user_data["id_to_container_cap"]):
                yield elements(el, "#containers", "append")
        except capnp.KjException as e:
            print(e)



async def list_containers(storage_service_cap, id_to_container_cap):
    patches = []
    try:
        cs = (await storage_service_cap.listContainers()).containers
        for c in cs:
            container_c_id = f"c_{c.id}"
            id_to_container_cap[container_c_id] = c.container
            patches.append(
                Details(
                    Summary(
                        H4(c.name),
                        open=False,
                        data_on_click=get(f"/containers/{container_c_id}"),
                    ),
                    Article(id=f"{container_c_id}")("-----"),
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
    return all_user_data.get(user_id, {}).get("id_to_container_cap", {}).get(container_c_id, None)


@app.get("/containers/{container_c_id}")
@sse
async def get_container(request, container_c_id: str, session: dict):
    user_id = session.get("user_id", None)
    if ((container := get_container_from_user_data(user_id, container_c_id)) is not None
            and (data := all_user_data.get(user_id, {}).get("data", None)) is not None):
        try:
            entries = (await container.listEntries()).entries
            rows = []
            for entry in entries:
                css_id = get_css_id_from_user_data(
                    user_id, f"{container_c_id}_e_{entry.key}"
                )
                entry_e_key = f"e_{entry.key}"
                data[container_c_id][entry_e_key] = {"edit_id": f"edit_{css_id}", "delete_id": f"delete_{css_id}"}
                rows.append(
                    Tr(
                        id=f"delete_{css_id}",
                    )(
                        Td(entry.key),
                        Td(id=f"edit_{css_id}")("---"),
                        Td()(
                            Button(
                                "Edit",
                                data_on_click=get(f"/containers/{container_c_id}/entries/{entry_e_key}", edit_id=css_id),
                            ),
                            Button(
                                "Delete",
                                data_on_click=delete(f"/containers/{container_c_id}/entries/{entry_e_key}", delete_id=css_id),
                            ),
                        ),
                    )
                )
            #yield signals(data=user_data["data"])
            yield elements(
                Table(cls="striped")(
                    Thead(Tr(Th("Key"), Th("Value"), Th("Actions"))), Tbody(*rows)
                ),
                f"#{container_c_id}",
                "inner",
            )
        except capnp.KjException as e:
            print(e)


@app.get("/containers/{container_c_id}/entries/{entry_e_key}")
@sse
async def get_entry(request, session, container_c_id: str, entry_e_key: str):
    user_id = session.get("user_id", None)
    if (container := get_container_from_user_data(user_id, container_c_id)):
        try:
            v = await container.getEntry(entry_e_key[2:]).entry.getValue()
            css_id = get_css_id_from_user_data(user_id, f"{container_c_id}_{entry_e_key}")
            yield elements(
                storage_input_field(
                    container_c_id,
                    entry_e_key,
                    f"/containers/{container_c_id}/entries/{entry_e_key}",
                    v.value,
                    v.isUnset,
                    css_id
                ),
                f"#edit_{css_id}",
                "inner",
            )
        except capnp.KjException as e:
            print(e)


@app.put("/containers/{container_c_id}/entries/{entry_e_key}/{value_type}")
@sse
async def update_entry(request, session, body, container_c_id: str, entry_e_key: str, value_type: str):
    user_id = session.get("user_id", None)
    if container := get_container_from_user_data(user_id, container_c_id):
        sigs = json.loads(body)
        css_id = get_css_id_from_user_data(user_id, f"{container_c_id}_{entry_e_key}")
        if new_value := sigs.get(f"value_{css_id}", None):
            try:
                entry_prom = container.getEntry(entry_e_key).entry
                success = await entry_prom.setValue({value_type: new_value})
                if success:
                    yield elements(Td(f"{new_value}"), f"#edit_{css_id}", "inner")
            except capnp.KjException as e:
                print(e)


def storage_input_field(
    container_c_id,
    entry_e_key,
    update_route: str,
    stor_val: storage_capnp.Store.Container.Entry.Value,
    is_unset: bool,
    css_id: str,
):
    val_type = stor_val.which()
    if val_type == "boolValue":
        return Input(
            #(value_invalid := Signal("bool_value_invalid", is_unset, namespace=f"{container_c_id}_{entry_e_key}")),
            #(value := Signal("bool_value", stor_val.boolValue, namespace=f"{container_c_id}_{entry_e_key}")),
            type="checkbox",
            data_attr_aria_invalid=value(is_unset),#value_invalid,
            data_bind=Signal(f"value_{css_id}", stor_val.boolValue),
            data_on_change=put(f"{update_route}/boolValue"),
        )
    elif val_type == "int8Value":
        sigs = {
            container_c_id: {
                entry_e_key: {
                    "int8ValueInvalid": False,
                    "int8Value": stor_val.int8Value,
                }
            }
        }
        return Input(
            type="number",
            min=f"{-(2**7)}",
            max=f"{2**7 - 1}",
            data_signals=json.dumps(sigs),
            data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.int8ValueInvalid}}",
            data_bind=f"{container_c_id}.{entry_e_key}.int8Value",
            data_on_change=f"@put('{update_route}/int8Value')",
        )
    elif val_type == "uint8Value":
        sigs = {
            container_c_id: {
                entry_e_key: {
                    "uint8ValueInvalid": False,
                    "uint8Value": stor_val.uint8Value,
                }
            }
        }
        return Input(
            type="number",
            min="0",
            max=f"{2**8 - 1}",
            data_signals=json.dumps(sigs),
            data_attr=f"{{'aria-invalid': ${container_c_id}.{entry_e_key}.uint8ValueInvalid}}",
            data_bind=f"{container_c_id}.{entry_e_key}.uint8Value",
            data_on_change=f"@put('{update_route}/uint8Value')",
        )
    elif val_type == "int16Value":
        # sigs = {
        #     container_c_id: {
        #         entry_e_key: {
        #             "int16ValueInvalid": False,
        #             "int16Value": stor_val.int16Value,
        #         }
        #     }
        # }
        return Input(
            type="number",
            min=f"{-(2**15)}",
            max=f"{2**15 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=Signal(f"value_{css_id}", stor_val.int16Value),
            data_on_change=put(f"{update_route}/int16Value"),
        )
    elif val_type == "uint16Value":
        # sigs = {
        #     container_c_id: {
        #         entry_e_key: {
        #             "uint16ValueInvalid": False,
        #             "uint16Value": stor_val.uint16Value,
        #         }
        #     }
        # }
        return Input(
            type="number",
            min="0",
            max=f"{2**16 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=Signal(f"value_{css_id}", stor_val.uint16Value),
            data_on_change=put(f"{update_route}/uint16Value"),
        )
    return Input()


if __name__ == "__main__":
    use = "hypercorn"
    # use = "uvicorn"
    if use == "hypercorn":
        config = HcConfig()
        config.bind = ["0.0.0.0:8080"]
        config.startup_timeout = 1200
        config.root_path = "/"
        asyncio.run(capnp.run(hc_serve(app, config)))
    elif use == "uvicorn":
        config = uvicorn.Config(
            "storage_service_ui:app",
            host="127.0.0.1",
            port=8080,
            reload=False,
        )
        server = uvicorn.Server(config=config)
        if config.should_reload:
            sock = config.bind_socket()
            from uvicorn.supervisors.watchfilesreload import (
                WatchFilesReload as ChangeReload,
            )

            ChangeReload(config, target=server.run, sockets=[sock]).run()
        else:
            server.config.setup_event_loop()
            asyncio.run(capnp.run(server.serve(sockets=None)))
