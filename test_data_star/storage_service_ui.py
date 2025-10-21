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

def empty_user_data():
    return {
        "sturdy_ref": "",
        "cap": None,
        "containers_loaded": False,
        "id_to_container_cap": {},
        "data": defaultdict(dict) # container id to entry id to data
    }

all_user_data = defaultdict(empty_user_data)
con_man = mas_common.ConnectionManager()

def id_from_long_id(user_id: str, long_id: str, prefix=""):
    user_id = "__no_user_id__" if user_id is None else user_id
    user_data = all_user_data[user_id]
    count_ids = user_data.setdefault("long_id_to_count_id", {})
    if long_id not in count_ids:
        count = user_data.setdefault("count", 0)
        user_data["count"] = (count := user_data.get("count", 0) + 1)
        count_ids[long_id] = f"{prefix}{count}"
    return count_ids[long_id]


def get_nested(d: dict, *args):
    val = d
    for arg in args:
        if (val := val.get(arg, None)) is None:
            return None
    return val


@app.get("/")
async def index(request, session: dict):
    user_id = session.setdefault("user_id", str(uuid.uuid4()))
    user_data = all_user_data[user_id]
    if user_data["cap"]:
        containers = await list_containers(user_id, user_data["cap"], user_data["id_to_container_cap"])
    else:
        containers = [no_container_placeholder()]
    return Div(
        Article(
            (sr_connected := Signal("sr_connected", user_data["cap"] is not None)),
            (connection_invalid := Signal("connection_invalid", ~sr_connected)),
            (sturdy_ref := Signal("sturdy_ref", user_data["sturdy_ref"])),
            Fieldset(role="group")(
                # Label("Sturdy Ref")(
                Input(
                    placeholder="Enter a Storage Service Sturdy Ref here",
                    data_bind=sturdy_ref,
                    type="text",
                    data_attr_aria_invalid=connection_invalid,
                ),
                # Small("Copy here the sturdy ref to your storage service"),
                # ),
                Button(
                    data_text=sr_connected.if_("Connected", "Connect"),
                    data_attr_disabled=sr_connected,
                    data_on_click=post("/connect"),
                ),
                Button("Disconnect",
                    data_show=sr_connected,
                    data_on_click=post("/disconnect"),
                ),
            )
        ),
        Pre(data_json_signals=True),
        Article(id="containers", data_show=sr_connected)(
            *containers
        ),
    )

def no_container_placeholder():
    return P(id="no_container_placeholder")("no containers available")

@app.post("/disconnect")
@sse
async def disconnect(session: dict):
    user_id = session.setdefault("user_id", str(uuid.uuid4()))
    all_user_data[user_id] = empty_user_data()
    yield signals(sr_connected=False, connection_invalid=True, sturdy_ref="")
    yield elements(no_container_placeholder(), "#containers", "inner")

@app.post("/connect")
@sse
async def connect(request, sturdy_ref: str, session: dict):
    if len(sturdy_ref) == 0:
        yield signals(sr_connected=False, connection_invalid=True)
        yield elements(no_container_placeholder(), "#containers", "inner")
    elif user_id := session.get("user_id", None):
        user_data = all_user_data[user_id]
        if "sturdy_ref" not in user_data or user_data["sturdy_ref"] != sturdy_ref or "cap" not in user_data:
            try:
                cap = await con_man.try_connect(sturdy_ref, cast_as=storage_capnp.Store)
                user_data["sturdy_ref"] = sturdy_ref
                user_data["cap"] = cap
                yield signals(sr_connected=True, connection_invalid=False)
                user_data["containers_loaded"] = False
            except capnp.KjException as e:
                print(e)
        if not user_data["containers_loaded"]:
            yield elements(no_container_placeholder(), "#containers", "inner")
            yield elements(None, "#no_container_placeholder", "remove")
            for el in await list_containers(user_id, user_data["cap"], user_data["id_to_container_cap"]):
                yield elements(el, "#containers", "append")
            user_data["containers_loaded"] = True


async def list_containers(user_id, storage_service_cap, id_to_container_cap):
    patches = []
    try:
        cs = (await storage_service_cap.listContainers()).containers
        for c in cs:
            container_c_id = id_from_long_id(user_id, c.id, prefix="c_")
            id_to_container_cap[container_c_id] = c.container
            patches.append(
                Details(
                    Summary(
                        H4(c.name),
                        open=False,
                        data_on_click=get(f"/containers/{container_c_id}"),
                    ),
                    Article(id=container_c_id)("-----"),
                )
            )
            patches.append(Hr())
    except capnp.KjException as e:
        print(e)
    return patches


def get_container_cap_from_user_data(user_id, container_c_id):
    return get_nested(all_user_data, user_id, "id_to_container_cap", container_c_id)


@app.get("/containers/{container_c_id}")
@sse
async def get_container(request, container_c_id: str, session: dict):
    if ((user_id := session.get("user_id", None))
            and (container := get_container_cap_from_user_data(user_id, container_c_id))
            and (data := get_nested(all_user_data, user_id, "data")) is not None):
        try:
            entries = (await container.listEntries()).entries
            rows = []
            for entry in entries:
                entry_e_id = id_from_long_id(user_id, entry.key, prefix="e_")
                data[container_c_id][entry_e_id] = {
                    "key": entry.key,
                }
                rows.append(
                    Tr(
                        id=f"{container_c_id}_{entry_e_id}",
                    )(
                        Td(entry.key),
                        Td(id=f"value_{container_c_id}_{entry_e_id}")("---"),
                        Td()(
                            Button(
                                (show_cancel := Signal(f"{container_c_id}_{entry_e_id}_show_cancel", False)),
                                "Edit",
                                data_show=~show_cancel,
                                data_on_click=[get(f"/containers/{container_c_id}/entries/{entry_e_id}?edit=true"),
                                               show_cancel.toggle()],
                            ),
                            Button(
                                "Cancel",
                                data_show=show_cancel,
                                data_on_click=[get(f"/containers/{container_c_id}/entries/{entry_e_id}?edit=false"),
                                               show_cancel.toggle()],
                            ),
                            Input(
                                (del_activated := Signal(f"{container_c_id}_{entry_e_id}_del_activated", False)),
                                type="checkbox",
                                data_bind=del_activated,
                            ),
                            Button(
                                "Delete",
                                data_attr_disabled=~del_activated,
                                data_on_click=delete(f"/containers/{container_c_id}/entries/{entry_e_id}"),
                            ),
                        ),
                    )
                )
            yield elements(
                Table(cls="striped")(
                    Thead(Tr(Th("Key"), Th("Value"), Th("Actions"))), Tbody(*rows)
                ),
                f"#{container_c_id}",
                "inner",
            )
        except capnp.KjException as e:
            print(e)



@app.get("/containers/{container_c_id}/entries/{entry_e_id}")
@sse
async def get_entry(request, session, container_c_id: str, entry_e_id: str, edit: bool):
    if ((user_id := session.get("user_id", None))
            and (container := get_container_cap_from_user_data(user_id, container_c_id))
            and (e_data := get_nested(all_user_data, user_id, "data", container_c_id, entry_e_id))):
        try:
            v = await container.getEntry(e_data["key"]).entry.getValue()
            if edit:
                yield elements(
                    storage_input_field(
                        container_c_id,
                        entry_e_id,
                        f"/containers/{container_c_id}/entries/{entry_e_id}",
                        v.value,
                        v.isUnset
                    ),
                    f"#value_{container_c_id}_{entry_e_id}",
                    "inner",
                )
            else:
                yield elements(Td(f"{v.value.__getattr__(v.value.which())}"),
                               f"#value_{container_c_id}_{entry_e_id}",
                               "inner")
        except capnp.KjException as e:
            print(e)


@app.put("/containers/{container_c_id}/entries/{entry_e_id}/{value_type}")
@sse
async def update_entry(request, session, body, container_c_id: str, entry_e_id: str, value_type: str):
    if ((user_id := session.get("user_id", None))
        and (container := get_container_cap_from_user_data(user_id, container_c_id))
        and (e_data := get_nested(all_user_data, user_id, "data", container_c_id, entry_e_id))):
        sigs = json.loads(body)
        if new_value := sigs.get(f"value_{container_c_id}_{entry_e_id}", None):
            try:
                entry_prom = container.getEntry(e_data["key"]).entry
                success = await entry_prom.setValue({value_type: new_value})
                if success.success:
                    yield elements(Td(f"{new_value}"),
                                   f"#value_{container_c_id}_{entry_e_id}",
                                   "inner")
            except capnp.KjException as e:
                print(e)

@app.delete("/containers/{container_c_id}/entries/{entry_e_id}")
@sse
async def delete_entry(request, session, container_c_id: str, entry_e_id: str):
    if ((user_id := session.get("user_id", None))
            and (container := get_container_cap_from_user_data(user_id, container_c_id))
            and (e_data := get_nested(all_user_data, user_id, "data", container_c_id, entry_e_id))):
        try:
            res = await container.removeEntry(e_data["key"])
            if res.success:
                yield elements(None, f"#{container_c_id}_{entry_e_id}", "remove")
        except capnp.KjException as e:
            print(e)


def storage_input_field(
    container_c_id,
    entry_e_id,
    update_route: str,
    stor_val: storage_capnp.Store.Container.Entry.Value,
    is_unset: bool,
):
    val_type = stor_val.which()
    if val_type == "boolValue":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.boolValue)),
            type="checkbox",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/boolValue"),
        )
    elif val_type == "int8Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.int8Value)),
            type="number",
            min=f"{-(2**7)}",
            max=f"{2**7 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/int8Value"),
        )
    elif val_type == "uint8Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.uint8Value)),
            type="number",
            min="0",
            max=f"{2**8 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/uint8Value"),
        )
    elif val_type == "int16Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.int16Value)),
            type="number",
            min=f"{-(2**15)}",
            max=f"{2**15 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/int16Value"),
        )
    elif val_type == "uint16Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.uint16Value)),
            type="number",
            min="0",
            max=f"{2**16 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/uint16Value"),
        )
    elif val_type == "int32Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.int32Value)),
            type="number",
            min=f"{-(2**31)}",
            max=f"{2**31 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/int32Value"),
        )
    elif val_type == "uint32Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.uint32Value)),
            type="number",
            min="0",
            max=f"{2**32 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/uint32Value"),
        )
    elif val_type == "int64Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.int64Value)),
            type="number",
            min=f"{-(2**63)}",
            max=f"{2**63 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/int64Value"),
        )
    elif val_type == "uint64Value":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.uint64Value)),
            type="number",
            min="0",
            max=f"{2**64 - 1}",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/uint64Value"),
        )
    elif val_type == "textValue":
        return Input(
            (val := Signal(f"value_{container_c_id}_{entry_e_id}", stor_val.textValue)),
            type="text",
            data_attr_aria_invalid=value(is_unset),
            data_bind=val,
            data_on_change=put(f"{update_route}/textValue"),
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
