"""
Informe de la entrega corta: ventas por internet de AdventureWorks2025.

Cuatro bloques, todos de importe:
    tiempo, producto, territorio y la combinación categoría-territorio-año.

El total sin filtros tiene que ser 60.398 líneas y 29.358.677,22 USD.
Ese número es solo el canal internet, no el hecho completo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import pyodbc
from dash import Dash, Input, Output, callback, dash_table, dcc, html

SERVER = r"localhost\SQLEXPRESS"
DWH_DB = "AdventureWorks_DWH"
LINEAS_CONTROL = 60398
IMPORTE_CONTROL = 29358677.2207

CONSULTA = """
SELECT
    f.SalesAmount,
    d.CalendarYear,
    d.Month,
    d.MonthName,
    p.ProductName,
    p.CategoryName,
    p.SubcategoryName,
    t.TerritoryName
FROM dbo.vw_FactInternetSales AS f
INNER JOIN dbo.Dim_Date AS d
    ON d.DateKey = f.OrderDateKey
INNER JOIN dbo.Dim_Product AS p
    ON p.ProductKey = f.ProductKey
INNER JOIN dbo.Dim_Territory AS t
    ON t.TerritoryKey = f.TerritoryKey
"""


def elegir_controlador() -> str:
    instalados = list(pyodbc.drivers())
    for nombre in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ):
        if nombre in instalados:
            return nombre
    raise RuntimeError("No hay un controlador ODBC de SQL Server.")


def cargar_datos() -> pd.DataFrame:
    controlador = elegir_controlador()
    conexion = pyodbc.connect(
        f"DRIVER={{{controlador}}};SERVER={SERVER};DATABASE={DWH_DB};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;",
        autocommit=True,
    )
    try:
        cursor = conexion.cursor()
        cursor.execute(CONSULTA)
        columnas = [columna[0] for columna in cursor.description]
        datos = pd.DataFrame.from_records(cursor.fetchall(), columns=columnas)
    finally:
        conexion.close()

    datos["SalesAmount"] = pd.to_numeric(datos["SalesAmount"])
    datos["CalendarYear"] = pd.to_numeric(datos["CalendarYear"]).astype(int)
    datos["Month"] = pd.to_numeric(datos["Month"]).astype(int)

    lineas = len(datos)
    importe = float(datos["SalesAmount"].sum())
    if lineas != LINEAS_CONTROL or abs(importe - IMPORTE_CONTROL) >= 0.02:
        raise RuntimeError(
            "La vista de internet no cuadra con el control de la entrega: "
            f"{lineas} líneas y {importe:.4f} USD."
        )
    return datos


def formato_importe(valor: float) -> str:
    return f"{valor:,.2f} USD".replace(",", "X").replace(".", ",").replace("X", ".")


def formato_unidades(valor: float) -> str:
    return f"{int(round(valor)):,}".replace(",", ".")


def figura_base(figura, titulo: str):
    figura.update_layout(
        title=titulo,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=48, r=16, t=48, b=48),
        font=dict(family="Segoe UI", size=13, color="#1c2830"),
        xaxis_title=None,
        yaxis_title=None,
        legend_title=None,
    )
    figura.update_yaxes(tickformat=",.0f", gridcolor="#e6edf2")
    figura.update_xaxes(gridcolor="#e6edf2")
    return figura


def figura_vacia(titulo: str):
    figura = px.bar()
    figura.update_layout(
        title=titulo,
        annotations=[
            dict(
                text="Sin datos para este filtro",
                showarrow=False,
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
            )
        ],
    )
    return figura_base(figura, titulo)


DATOS = cargar_datos()

app = Dash(
    __name__,
    assets_folder=str(Path(__file__).resolve().parent / "assets"),
    title="AdventureWorks2025 Ventas por internet",
)

app.layout = html.Div(
    className="pagina",
    children=[
        html.Header(
            className="cabecera",
            children=[
                html.H1("AdventureWorks2025 Ventas por internet"),
                html.P(
                    "Entrega corta. Importe por tiempo, producto, territorio "
                    "y por la combinación categoría, territorio y año. "
                    f"Sin filtros, el control es {formato_unidades(LINEAS_CONTROL)} líneas "
                    f"y {formato_importe(IMPORTE_CONTROL)}."
                ),
            ],
        ),
        html.Div(
            className="filtros",
            children=[
                html.Div(
                    children=[
                        html.Label("Año"),
                        dcc.Dropdown(
                            id="filtro-anio",
                            options=sorted(DATOS["CalendarYear"].unique()),
                            multi=True,
                            placeholder="Todos los años",
                        ),
                    ]
                ),
                html.Div(
                    children=[
                        html.Label("Territorio"),
                        dcc.Dropdown(
                            id="filtro-territorio",
                            options=sorted(DATOS["TerritoryName"].unique()),
                            multi=True,
                            placeholder="Todos los territorios",
                        ),
                    ]
                ),
                html.Div(
                    children=[
                        html.Label("Categoría"),
                        dcc.Dropdown(
                            id="filtro-categoria",
                            options=sorted(DATOS["CategoryName"].unique()),
                            multi=True,
                            placeholder="Todas las categorías",
                        ),
                    ]
                ),
            ],
        ),
        html.Div(
            className="kpis",
            children=[
                html.Div(className="tarjeta", children=[html.Span("Importe"), html.Strong(id="kpi-importe")]),
                html.Div(className="tarjeta", children=[html.Span("Líneas"), html.Strong(id="kpi-lineas")]),
                html.Div(className="tarjeta", children=[html.Span("Año con mayor importe"), html.Strong(id="kpi-anio")]),
                html.Div(className="tarjeta", children=[html.Span("Territorio con mayor importe"), html.Strong(id="kpi-territorio")]),
            ],
        ),
        html.Section(
            className="bloque",
            children=[
                html.H2("1. Tiempo"),
                html.P("Importe por año y por mes. El mes usa el número de mes, no el orden alfabético.", className="nota"),
                html.Div(
                    className="graficos",
                    children=[
                        dcc.Graph(id="grafico-anio", config={"displaylogo": False}),
                        dcc.Graph(id="grafico-mes", config={"displaylogo": False}),
                    ],
                ),
                html.P(id="texto-tiempo", className="conclusion"),
            ],
        ),
        html.Section(
            className="bloque",
            children=[
                html.H2("2. Producto"),
                html.P("Importe por categoría y los diez productos que más venden.", className="nota"),
                html.Div(
                    className="graficos",
                    children=[
                        dcc.Graph(id="grafico-categoria", config={"displaylogo": False}),
                        dcc.Graph(id="grafico-top", config={"displaylogo": False}),
                    ],
                ),
            ],
        ),
        html.Section(
            className="bloque",
            children=[
                html.H2("3. Territorio"),
                html.P("Importe del pedido según el territorio de la venta, no el del cliente.", className="nota"),
                dcc.Graph(id="grafico-territorio", config={"displaylogo": False}),
            ],
        ),
        html.Section(
            className="bloque",
            children=[
                html.H2("4. Categoría, territorio y año"),
                html.P(
                    "La matriz responde cuánto se vendió de cada categoría en cada año. "
                    "La tabla muestra las combinaciones con mayor importe.",
                    className="nota",
                ),
                dcc.Graph(id="grafico-matriz", config={"displaylogo": False}),
                dash_table.DataTable(
                    id="tabla-combinaciones",
                    page_size=15,
                    sort_action="native",
                    style_table={"marginTop": "8px"},
                    style_cell={"fontFamily": "Segoe UI", "fontSize": "13px", "textAlign": "left", "padding": "8px"},
                    style_header={"fontWeight": "650", "backgroundColor": "#f7fafc"},
                ),
            ],
        ),
    ],
)


def aplicar_filtros(anios, territorios, categorias) -> pd.DataFrame:
    datos = DATOS
    if anios:
        datos = datos[datos["CalendarYear"].isin(anios)]
    if territorios:
        datos = datos[datos["TerritoryName"].isin(territorios)]
    if categorias:
        datos = datos[datos["CategoryName"].isin(categorias)]
    return datos


@callback(
    Output("kpi-importe", "children"),
    Output("kpi-lineas", "children"),
    Output("kpi-anio", "children"),
    Output("kpi-territorio", "children"),
    Output("grafico-anio", "figure"),
    Output("grafico-mes", "figure"),
    Output("texto-tiempo", "children"),
    Output("grafico-categoria", "figure"),
    Output("grafico-top", "figure"),
    Output("grafico-territorio", "figure"),
    Output("grafico-matriz", "figure"),
    Output("tabla-combinaciones", "data"),
    Output("tabla-combinaciones", "columns"),
    Input("filtro-anio", "value"),
    Input("filtro-territorio", "value"),
    Input("filtro-categoria", "value"),
)
def actualizar(anios, territorios, categorias):
    datos = aplicar_filtros(anios, territorios, categorias)
    columnas = [
        {"name": "Categoría", "id": "Categoría"},
        {"name": "Territorio", "id": "Territorio"},
        {"name": "Año", "id": "Año"},
        {"name": "Importe", "id": "Importe"},
    ]
    if datos.empty:
        vacio = "Sin datos"
        return (
            vacio,
            "0",
            vacio,
            vacio,
            figura_vacia("Importe por año"),
            figura_vacia("Importe por mes"),
            "El filtro no deja líneas.",
            figura_vacia("Importe por categoría"),
            figura_vacia("Diez productos con mayor importe"),
            figura_vacia("Importe por territorio"),
            figura_vacia("Importe por categoría y año"),
            [],
            columnas,
        )

    por_anio = (
        datos.groupby("CalendarYear", as_index=False)["SalesAmount"]
        .sum()
        .sort_values("CalendarYear")
    )
    por_mes = (
        datos.groupby(["Month", "MonthName"], as_index=False)["SalesAmount"]
        .sum()
        .sort_values("Month")
    )
    por_categoria = (
        datos.groupby("CategoryName", as_index=False)["SalesAmount"]
        .sum()
        .sort_values("SalesAmount", ascending=False)
    )
    top_productos = (
        datos.groupby("ProductName", as_index=False)["SalesAmount"]
        .sum()
        .nlargest(10, "SalesAmount")
        .sort_values("SalesAmount")
    )
    por_territorio = (
        datos.groupby("TerritoryName", as_index=False)["SalesAmount"]
        .sum()
        .sort_values("SalesAmount", ascending=False)
    )
    matriz = datos.pivot_table(
        index="CategoryName",
        columns="CalendarYear",
        values="SalesAmount",
        aggfunc="sum",
        fill_value=0,
    )
    matriz.columns = matriz.columns.astype(str)
    combinaciones = (
        datos.groupby(["CategoryName", "TerritoryName", "CalendarYear"], as_index=False)["SalesAmount"]
        .sum()
        .sort_values("SalesAmount", ascending=False)
        .head(15)
    )
    combinaciones["Importe"] = combinaciones["SalesAmount"].map(formato_importe)
    tabla = combinaciones.rename(
        columns={
            "CategoryName": "Categoría",
            "TerritoryName": "Territorio",
            "CalendarYear": "Año",
        }
    )[["Categoría", "Territorio", "Año", "Importe"]]

    anio_lider = por_anio.loc[por_anio["SalesAmount"].idxmax()]
    territorio_lider = por_territorio.loc[por_territorio["SalesAmount"].idxmax()]
    mes_max = por_mes.loc[por_mes["SalesAmount"].idxmax()]
    mes_min = por_mes.loc[por_mes["SalesAmount"].idxmin()]

    etiquetas = {
        "CalendarYear": "Año",
        "SalesAmount": "Importe",
        "MonthName": "Mes",
        "CategoryName": "Categoría",
        "ProductName": "Producto",
        "TerritoryName": "Territorio",
    }
    figura_anio = figura_base(
        px.bar(por_anio, x="CalendarYear", y="SalesAmount", labels=etiquetas, color_discrete_sequence=["#0f4c5c"]),
        "Importe por año",
    )
    figura_mes = figura_base(
        px.bar(por_mes, x="MonthName", y="SalesAmount", labels=etiquetas, color_discrete_sequence=["#1b6b7a"]),
        "Importe por mes",
    )
    figura_categoria = figura_base(
        px.bar(por_categoria, x="CategoryName", y="SalesAmount", labels=etiquetas, color_discrete_sequence=["#0f4c5c"]),
        "Importe por categoría",
    )
    figura_top = figura_base(
        px.bar(
            top_productos,
            x="SalesAmount",
            y="ProductName",
            orientation="h",
            labels=etiquetas,
            color_discrete_sequence=["#c17f3e"],
        ),
        "Diez productos con mayor importe",
    )
    figura_territorio = figura_base(
        px.bar(por_territorio, x="TerritoryName", y="SalesAmount", labels=etiquetas, color_discrete_sequence=["#0f4c5c"]),
        "Importe por territorio",
    )
    figura_matriz = figura_base(
        px.imshow(
            matriz,
            aspect="auto",
            color_continuous_scale=["#f4f7f8", "#0f4c5c"],
            labels=dict(x="Año", y="Categoría", color="Importe"),
        ),
        "Importe por categoría y año",
    )
    figura_anio.update_xaxes(type="category", tickformat=None)
    figura_matriz.update_yaxes(tickformat=None)

    texto = (
        f"El mayor importe anual es {int(anio_lider['CalendarYear'])} "
        f"({formato_importe(float(anio_lider['SalesAmount']))}). "
        f"El mes con más importe es {mes_max['MonthName']} "
        f"({formato_importe(float(mes_max['SalesAmount']))}) y el de menos es {mes_min['MonthName']} "
        f"({formato_importe(float(mes_min['SalesAmount']))})."
    )

    return (
        formato_importe(float(datos["SalesAmount"].sum())),
        formato_unidades(len(datos)),
        str(int(anio_lider["CalendarYear"])),
        str(territorio_lider["TerritoryName"]),
        figura_anio,
        figura_mes,
        texto,
        figura_categoria,
        figura_top,
        figura_territorio,
        figura_matriz,
        tabla.to_dict("records"),
        columnas,
    )


if __name__ == "__main__":
    app.run(debug=True)
