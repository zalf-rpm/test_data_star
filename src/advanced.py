# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "asyncio",
#     "datastar-py",
#     "great-tables",
#     "pandas",
#     "polars",
#     "python-fasthtml",
# ]
# [tool.uv.sources]
# datastar-py = { path = "../../" }
# ///
import asyncio
import json
from datetime import datetime

import polars as pl

# ruff: noqa: F403, F405
from fasthtml.common import *
from great_tables import GT
from great_tables.data import reactions

from datastar_py.fasthtml import DatastarResponse, ServerSentEventGenerator

######################################################################################################
# This demo shows how FastHTML can be integrated with Datastar for server-driven interaction with a  #
# python library capable of generating HTML fragments (Great Tables). It uses Datastar's Python SDK  #
# to merge the generated table into the DOM through an asynchronous function call. It also           #
# demonstrates how Datastar can be used in conjunction with traditional GET requests to SSE for HTML #
# as the Engine of Application State.                                                                #
######################################################################################################

###################################################################################
# More information can be found in the documentation of the respective libraries: #
# - FastHTML: https://docs.fastht.ml/                                             #
# - Datastar: https://data-star.dev/                                              #
# - Great Tables: https://posit-dev.github.io/great-tables/articles/intro.html    #
###################################################################################

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

default_pattern = "aldehyde"


# Create a 'FastTag' (FT) that renders the Great Tables table with a built-in dataset
def GreatTable(pattern=default_pattern):
    return Div(id="gt-table")(
        NotStr(
            GT(
                pl.from_pandas(reactions)
                .select(
                    [
                        "cmpd_name",
                        "cmpd_mwt",
                        "cmpd_formula",
                        "cmpd_type",
                        "cmpd_smiles",
                        "cmpd_inchi",
                        "cmpd_inchikey",
                        "OH_k298",
                    ]
                )
                .filter(pl.col("cmpd_name").str.contains(pattern))
                .drop_nulls()
            )
            .cols_label(
                {
                    "cmpd_name": "Compound",
                    "cmpd_mwt": "Molecular Weight",
                    "cmpd_formula": "Formula",
                    "cmpd_type": "Type",
                    "cmpd_smiles": "SMILES",
                    "cmpd_inchi": "InChI",
                    "cmpd_inchikey": "InChI Key",
                    "OH_k298": "OH Rate Constant",
                }
            )
            .as_raw_html()
        )
    )


# Define an asynchronous function that uses the Python SDK's patch_elements method to patch the
# rendered table into the DOM with the request's 'filter' value
@app.post
async def table(filter: str):
    return DatastarResponse(ServerSentEventGenerator.patch_elements(GreatTable(filter)))


# Define default route which returns a FastTag from a GET request.
@rt
def index():
    now = datetime.isoformat(datetime.now())
    return Body(
        # Define the signals that Datastar will 'parse using data-signals=', passing in JSON in this case
        data_signals=json.dumps(
            {"currentTime": now, "filter": default_pattern, "filtering": "false"}
        )
    )(
        Div(cls="container")(
            Section(
                H2("Demonstration: Long-lived GET Request to Generator Function"),
                Div(data_on_load=f"@get('{time}')", cls="time")(
                    "Current time from element: ",
                    Span(id="currentTime")(now),
                ),
            ),
            Section(
                H2("Demonstration: HATEOS"),
                Div(
                    style="margin-top:1rem",
                )(HELLO_BUTTON),
            ),
            Section(
                H2("Demonstration: Realtime Filtering on a Great Tables Table"),
                P(
                    "This table contains 'Reaction rates for gas-phase atmospheric reactions of organic compounds.' - ",
                    A(
                        "Great Tables Documentation",
                        href="https://posit-dev.github.io/great-tables/reference/#built-in-datasets",
                    ),
                ),
                # When the below request is in flight, $filtering becomes true, setting the aria-busy attribute
                Label(fr="filter", data_attr_aria_busy="$filtering")("Filter Compound"),
                # Bind the 'filter' signal to the value of this input, debouncing using Datastar modifier
                Input(
                    {"data-on-input__debounce.250ms": f"@post('{table}')"},
                    data_bind_filter=True,
                    id="filter",
                    name="filter",
                    data_indicator_filtering=True,
                ),
                Div(id="gt-table", data_on_load=f"@post('{table}')"),
            ),
        ),
    )


# Define an async function that yields a patch_elements command every second
async def clock():
    while True:
        now = datetime.isoformat(datetime.now())
        yield ServerSentEventGenerator.patch_elements(Span(id="currentTime")(now))
        await asyncio.sleep(1)


@rt
async def time():
    return DatastarResponse(clock())


@rt
async def hello():
    async def _():
        # Simulate load time
        await asyncio.sleep(1)
        yield ServerSentEventGenerator.patch_elements(HELLO_BUTTON)

    return DatastarResponse(_())


@rt
async def reset():
    reset_and_hello = Div(id="myElement")(
        Button(
            data_on_click=f"@get('{hello}')",
            type="reset",
            data_indicator_resetting=True,
            data_attr_aria_busy="$resetting",
            data_attr_disabled="$resetting",
        )("Reset"),
        Div("Hello!"),
    )

    async def _():
        await asyncio.sleep(1)
        yield ServerSentEventGenerator.patch_elements(reset_and_hello)

    return DatastarResponse(_())


# Define the button once so that it can be used in the index response
HELLO_BUTTON = Div(id="myElement")(
    Button(
        data_on_click=f"@get('{reset}')",
        data_indicator_loading=True,
        data_attr_aria_busy="$loading",
        data_attr_disabled="$loading",
    )("Say hello"),
)


if __name__ == "__main__":
    serve()
