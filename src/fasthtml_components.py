from datastar_py.fasthtml import DatastarResponse, ServerSentEventGenerator as SSE, read_signals
from datastar_py.consts import ElementPatchMode
from fasthtml import ft
from fasthtml.common import *
import json

def ConnectToSturdyRef(id, prefix=None, bookmarks=None):
    prefix = prefix or []
    route_prefix = "/".join(prefix)
    signal_prefix = ".".join(prefix)
    id_prefix = "_".join(prefix)
    bookmarks = bookmarks or []
    return Article()(
        Div(cls="grid")(
            Select(data_signals=json.dumps({id: ""}),
                   #data_on_change="@post"
                   )(
                *[Option(value=f"{b['sr']}")(b["petname"]) for b in bookmarks]
            ),
            Button("Connect", data_on_click=f"@get('/{route_prefix}/srs/connect')"),
            Button("Edit", data_on_click=f"@get('/{route_prefix}/srs/edit')"),
            Button("Add",
                   data_on_click=f"@get('/{route_prefix}/srs/add')"),
        )
    )



def AddSturdyRef():
    return Dialog(id="add_sr_dialog",
                  data_signals_open="true",
                  data_attr="{open: $open}")(
        Article()(
            Fieldset()(
                Label("Interface ID", Input(type="text")),
                Label("Petname", Input(type="text")),
                Label("Sturdy ref", Input(type="text")),
                Label("Auto-Connect?", Input(type="checkbox")),
                Label("Select by default?", Input(type="checkbox")),
                Button("Add"),
                Button("Cancel", data_on_click="$open=false; @delete('/add_sturdy_ref')"),
            ),
            Div(data_text="'Open:'+$open")
        )
    )

def new_sturdy_ref_handler(app, route):
    #@app.get(f"/{route}")
    async def add_sturdy_ref(request):
        signals = await read_signals(request)
        print(signals)
        return DatastarResponse(SSE.patch_elements(
            AddSturdyRef(),
            selector="body",
            mode=ElementPatchMode.PREPEND,
        ))
    app.route(route, methods=["GET"])(add_sturdy_ref)
    #return add_sturdy_ref


def GeoPosPicker(id):
    return Article("geo pos picker here")


def add_route(app, bookmarks):
    @app.post("/bookmarks/{id}/{value}")
    def bookmark(id: int, value: str):
        bookmarks[id] = value


def SoilPropertiesList(soil_props):
    ps = []
    for p in soil_props:
        ps.append(
            Li()(
                Label()(
                    Input(type="checkbox"),
                )
            )
        )
    return ps

def LoadSoilBar():
    return Article(
        Fieldset(cls="grid")(
            Label(
                Input(type="checkbox", role="switch"),
                "Auto-Load"
            ),
            Button("Load soil profile"),
            Details(cls="dropdown")(
                Summary("Selected mandatory soil properties"),
                Ul()(*SoilPropertiesList([]))
            ),
            Details(cls="dropdown")(
                Summary("Selected optional soil properties"),
                Ul()(*SoilPropertiesList([]))
            ),
        )
    )

def SoilTable(profile_data):
    header = []
    for h in []:
        header.append(Th(str(h), scope="col"))
    rows = []
    for i, r in enumerate([]):
        rows.append(Tr(Td(r[i])))
    return Article()(
        Table(cls="striped")(
            Thead(*header),
            Tbody(id="tbody")
        )
    )

def SoilProfileData(profile_data):
    l = []
    first = True
    for pd in profile_data:
        l.append(
            Details(open=first)(
                Summary(pd["profile_name"]),
                SoilTable(pd["data"])
            )
        )
        first = False

    return Article()(*l)

def SoilService():
    return Div()(
            ConnectToSturdyRef("soil_service_srs",
                               on_add_url="add_sturdy_ref"),
            ConnectToSturdyRef("soil_service_srs",
                               on_add_url="add_sturdy_ref"),
            GeoPosPicker("geo_pos_picker"),
            LoadSoilBar(),
            SoilProfileData([]),
        )
