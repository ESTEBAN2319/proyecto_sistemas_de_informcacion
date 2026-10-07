"""
ETL de AdventureWorks2025 hacia AdventureWorks_DWH.

Orden:
    1. Fabricar Dim_Date (calendario y año fiscal julio-junio).
    2. Extraer producto, cliente y territorio ya aplanados.
    3. MERGE de dimensiones por clave de negocio. IDENTITY asigna la surrogada.
    4. Vaciar el hecho y volver a insertarlo, resolviendo esas surrogadas.
    5. Publicar vw_Sales.
    6. Abortar si el número de líneas o la suma de importes no cuadra.

Ejecutar dos veces seguidas: la segunda carga tiene que dejar el mismo
número de filas en Fact_Sales.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyodbc

SERVER = r"localhost\SQLEXPRESS"
SOURCE_DB = "AdventureWorks2025"
DWH_DB = "AdventureWorks_DWH"
ROOT = Path(__file__).resolve().parents[1]
VIEW_SQL = (ROOT / "sql" / "04_crear_vista_ventas.sql").read_text(encoding="utf-8")

MESES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DESCONOCIDO = "Desconocido"


def pick_driver() -> str:
    installed = list(pyodbc.drivers())
    for name in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ):
        if name in installed:
            return name
    raise RuntimeError(
        "No hay un controlador ODBC de SQL Server. Instalados: " + ", ".join(installed)
    )


def connect(database: str) -> pyodbc.Connection:
    driver = pick_driver()
    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(connection_string, autocommit=False)
    return connection


def fetch_frame(connection: pyodbc.Connection, sql: str) -> pd.DataFrame:
    cursor = connection.cursor()
    cursor.execute(sql)
    columns = [column[0] for column in cursor.description]
    frame = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
    cursor.close()
    return frame


def plain_rows(frame: pd.DataFrame) -> list[tuple]:
    rows: list[tuple] = []
    for record in frame.itertuples(index=False, name=None):
        values = []
        for value in record:
            if hasattr(value, "item") and not isinstance(value, str):
                value = value.item()
            values.append(value)
        rows.append(tuple(values))
    return rows


def insert_many(
    cursor: pyodbc.Cursor,
    sql: str,
    rows: list[tuple],
    sizes: list | None = None,
    size: int = 5000,
) -> None:
    cursor.fast_executemany = True
    if sizes is not None:
        cursor.setinputsizes(sizes)
    for start in range(0, len(rows), size):
        cursor.executemany(sql, rows[start : start + size])


def ensure_staging(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.stg_Date', N'U') IS NULL
        CREATE TABLE stg_Date (
            DateKey INT NOT NULL,
            FullDate DATE NOT NULL,
            CalendarYear INT NOT NULL,
            FiscalYear INT NOT NULL,
            Quarter INT NOT NULL,
            FiscalQuarter INT NOT NULL,
            Month INT NOT NULL,
            MonthName VARCHAR(20) NOT NULL,
            Day INT NOT NULL,
            DayOfWeekName VARCHAR(20) NOT NULL
        );

        IF OBJECT_ID(N'dbo.stg_Product', N'U') IS NULL
        CREATE TABLE stg_Product (
            ProductAlternateKey INT NOT NULL,
            ProductName NVARCHAR(50) NOT NULL,
            ProductNumber NVARCHAR(25) NOT NULL,
            Color NVARCHAR(15) NOT NULL,
            SubcategoryName NVARCHAR(50) NOT NULL,
            CategoryName NVARCHAR(50) NOT NULL
        );

        IF OBJECT_ID(N'dbo.stg_Customer', N'U') IS NULL
        CREATE TABLE stg_Customer (
            CustomerAlternateKey INT NOT NULL,
            CustomerType VARCHAR(10) NOT NULL,
            CustomerName NVARCHAR(150) NOT NULL
        );

        IF OBJECT_ID(N'dbo.stg_Territory', N'U') IS NULL
        CREATE TABLE stg_Territory (
            TerritoryAlternateKey INT NOT NULL,
            TerritoryName NVARCHAR(50) NOT NULL,
            CountryRegionCode NVARCHAR(3) NOT NULL,
            TerritoryGroup NVARCHAR(50) NOT NULL
        );

        IF OBJECT_ID(N'dbo.stg_Fact', N'U') IS NULL
        CREATE TABLE stg_Fact (
            ProductID INT NOT NULL,
            CustomerID INT NOT NULL,
            TerritoryID INT NOT NULL,
            OrderDateKey INT NOT NULL,
            SalesOrderNumber NVARCHAR(25) NOT NULL,
            SalesOrderDetailID INT NOT NULL,
            OrderQty SMALLINT NOT NULL,
            UnitPrice DECIMAL(19,4) NOT NULL,
            DiscountPct DECIMAL(9,4) NOT NULL,
            SalesAmount DECIMAL(19,4) NOT NULL
        );
        """
    )


def fiscal_parts(day: date) -> tuple[int, int]:
    """Año fiscal de AdventureWorks: empieza el 1 de julio."""
    if day.month >= 7:
        fiscal_year = day.year + 1
        fiscal_quarter = 1 if day.month <= 9 else 2
    else:
        fiscal_year = day.year
        fiscal_quarter = 3 if day.month <= 3 else 4
    return fiscal_year, fiscal_quarter


def build_dim_date(first_day: date, last_order_day: date) -> list[tuple]:
    """Calendario continuo desde el primer pedido hasta un año después del último."""
    end = last_order_day + timedelta(days=365)
    rows: list[tuple] = []
    current = first_day
    while current <= end:
        fiscal_year, fiscal_quarter = fiscal_parts(current)
        rows.append(
            (
                current.year * 10000 + current.month * 100 + current.day,
                current,
                current.year,
                fiscal_year,
                (current.month - 1) // 3 + 1,
                fiscal_quarter,
                current.month,
                MESES[current.month],
                current.day,
                DIAS[current.weekday()],
            )
        )
        current += timedelta(days=1)
    return rows


def text_or_unknown(series: pd.Series, limit: int) -> pd.Series:
    cleaned = series.fillna(DESCONOCIDO).astype(str).str.strip()
    cleaned = cleaned.mask(cleaned.eq(""), DESCONOCIDO)
    return cleaned.str.slice(0, limit)


def load_dates(cursor: pyodbc.Cursor, source: pyodbc.Connection) -> int:
    bounds = fetch_frame(
        source,
        "SELECT MIN(OrderDate) AS MinDate, MAX(OrderDate) AS MaxDate FROM Sales.SalesOrderHeader",
    )
    first_day = pd.Timestamp(bounds.loc[0, "MinDate"]).date()
    last_day = pd.Timestamp(bounds.loc[0, "MaxDate"]).date()
    rows = build_dim_date(first_day, last_day)
    cursor.execute("TRUNCATE TABLE stg_Date")
    insert_many(
        cursor,
        """
        INSERT INTO stg_Date (
            DateKey, FullDate, CalendarYear, FiscalYear, Quarter, FiscalQuarter,
            Month, MonthName, Day, DayOfWeekName
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
        sizes=[
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_TYPE_DATE,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_VARCHAR, 20, 0),
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_VARCHAR, 20, 0),
        ],
    )
    cursor.execute(
        """
        MERGE Dim_Date AS target
        USING stg_Date AS source
            ON target.DateKey = source.DateKey
        WHEN MATCHED THEN
            UPDATE SET
                FullDate = source.FullDate,
                CalendarYear = source.CalendarYear,
                FiscalYear = source.FiscalYear,
                Quarter = source.Quarter,
                FiscalQuarter = source.FiscalQuarter,
                Month = source.Month,
                MonthName = source.MonthName,
                Day = source.Day,
                DayOfWeekName = source.DayOfWeekName
        WHEN NOT MATCHED THEN
            INSERT (
                DateKey, FullDate, CalendarYear, FiscalYear, Quarter, FiscalQuarter,
                Month, MonthName, Day, DayOfWeekName
            )
            VALUES (
                source.DateKey, source.FullDate, source.CalendarYear, source.FiscalYear,
                source.Quarter, source.FiscalQuarter, source.Month, source.MonthName,
                source.Day, source.DayOfWeekName
            );
        """
    )
    return len(rows)


def load_products(cursor: pyodbc.Cursor, source: pyodbc.Connection) -> int:
    frame = fetch_frame(
        source,
        """
        SELECT
            p.ProductID AS ProductAlternateKey,
            p.Name AS ProductName,
            p.ProductNumber,
            p.Color,
            sc.Name AS SubcategoryName,
            cat.Name AS CategoryName
        FROM Production.Product AS p
        LEFT JOIN Production.ProductSubcategory AS sc
            ON sc.ProductSubcategoryID = p.ProductSubcategoryID
        LEFT JOIN Production.ProductCategory AS cat
            ON cat.ProductCategoryID = sc.ProductCategoryID
        """,
    )
    frame["ProductAlternateKey"] = frame["ProductAlternateKey"].astype(int)
    frame["ProductName"] = text_or_unknown(frame["ProductName"], 50)
    frame["ProductNumber"] = text_or_unknown(frame["ProductNumber"], 25)
    frame["Color"] = text_or_unknown(frame["Color"], 15)
    frame["SubcategoryName"] = text_or_unknown(frame["SubcategoryName"], 50)
    frame["CategoryName"] = text_or_unknown(frame["CategoryName"], 50)
    rows = plain_rows(frame)
    cursor.execute("TRUNCATE TABLE stg_Product")
    insert_many(
        cursor,
        """
        INSERT INTO stg_Product (
            ProductAlternateKey, ProductName, ProductNumber, Color,
            SubcategoryName, CategoryName
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
        sizes=[
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_WVARCHAR, 50, 0),
            (pyodbc.SQL_WVARCHAR, 25, 0),
            (pyodbc.SQL_WVARCHAR, 15, 0),
            (pyodbc.SQL_WVARCHAR, 50, 0),
            (pyodbc.SQL_WVARCHAR, 50, 0),
        ],
    )
    cursor.execute(
        """
        MERGE Dim_Product AS target
        USING stg_Product AS source
            ON target.ProductAlternateKey = source.ProductAlternateKey
        WHEN MATCHED THEN
            UPDATE SET
                ProductName = source.ProductName,
                ProductNumber = source.ProductNumber,
                Color = source.Color,
                SubcategoryName = source.SubcategoryName,
                CategoryName = source.CategoryName
        WHEN NOT MATCHED THEN
            INSERT (
                ProductAlternateKey, ProductName, ProductNumber, Color,
                SubcategoryName, CategoryName
            )
            VALUES (
                source.ProductAlternateKey, source.ProductName, source.ProductNumber,
                source.Color, source.SubcategoryName, source.CategoryName
            );
        """
    )
    return len(rows)


def load_customers(cursor: pyodbc.Cursor, source: pyodbc.Connection) -> int:
    frame = fetch_frame(
        source,
        """
        SELECT
            c.CustomerID AS CustomerAlternateKey,
            CASE
                WHEN c.PersonID IS NOT NULL THEN 'Person'
                ELSE 'Store'
            END AS CustomerType,
            CASE
                WHEN c.PersonID IS NOT NULL THEN CONCAT(p.FirstName, ' ', p.LastName)
                ELSE s.Name
            END AS CustomerName
        FROM Sales.Customer AS c
        LEFT JOIN Person.Person AS p
            ON p.BusinessEntityID = c.PersonID
        LEFT JOIN Sales.Store AS s
            ON s.BusinessEntityID = c.StoreID
        """,
    )
    frame["CustomerAlternateKey"] = frame["CustomerAlternateKey"].astype(int)
    frame["CustomerType"] = text_or_unknown(frame["CustomerType"], 10)
    frame["CustomerName"] = text_or_unknown(frame["CustomerName"], 150)
    rows = plain_rows(frame)
    cursor.execute("TRUNCATE TABLE stg_Customer")
    insert_many(
        cursor,
        """
        INSERT INTO stg_Customer (CustomerAlternateKey, CustomerType, CustomerName)
        VALUES (?, ?, ?)
        """,
        rows,
        sizes=[
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_VARCHAR, 10, 0),
            (pyodbc.SQL_WVARCHAR, 150, 0),
        ],
    )
    cursor.execute(
        """
        MERGE Dim_Customer AS target
        USING stg_Customer AS source
            ON target.CustomerAlternateKey = source.CustomerAlternateKey
        WHEN MATCHED THEN
            UPDATE SET
                CustomerType = source.CustomerType,
                CustomerName = source.CustomerName
        WHEN NOT MATCHED THEN
            INSERT (CustomerAlternateKey, CustomerType, CustomerName)
            VALUES (source.CustomerAlternateKey, source.CustomerType, source.CustomerName);
        """
    )
    return len(rows)


def load_territories(cursor: pyodbc.Cursor, source: pyodbc.Connection) -> int:
    frame = fetch_frame(
        source,
        """
        SELECT
            t.TerritoryID AS TerritoryAlternateKey,
            t.Name AS TerritoryName,
            t.CountryRegionCode,
            t.[Group] AS TerritoryGroup
        FROM Sales.SalesTerritory AS t
        """,
    )
    frame["TerritoryAlternateKey"] = frame["TerritoryAlternateKey"].astype(int)
    frame["TerritoryName"] = text_or_unknown(frame["TerritoryName"], 50)
    frame["CountryRegionCode"] = text_or_unknown(frame["CountryRegionCode"], 3)
    frame["TerritoryGroup"] = text_or_unknown(frame["TerritoryGroup"], 50)
    rows = plain_rows(frame)
    null_territory = fetch_frame(
        source,
        "SELECT COUNT(*) AS PedidosSinTerritorio FROM Sales.SalesOrderHeader WHERE TerritoryID IS NULL",
    )
    if int(null_territory.loc[0, "PedidosSinTerritorio"]) > 0:
        rows.append((-1, DESCONOCIDO, "N/A", DESCONOCIDO))
    cursor.execute("TRUNCATE TABLE stg_Territory")
    insert_many(
        cursor,
        """
        INSERT INTO stg_Territory (
            TerritoryAlternateKey, TerritoryName, CountryRegionCode, TerritoryGroup
        ) VALUES (?, ?, ?, ?)
        """,
        rows,
        sizes=[
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_WVARCHAR, 50, 0),
            (pyodbc.SQL_WVARCHAR, 3, 0),
            (pyodbc.SQL_WVARCHAR, 50, 0),
        ],
    )
    cursor.execute(
        """
        MERGE Dim_Territory AS target
        USING stg_Territory AS source
            ON target.TerritoryAlternateKey = source.TerritoryAlternateKey
        WHEN MATCHED THEN
            UPDATE SET
                TerritoryName = source.TerritoryName,
                CountryRegionCode = source.CountryRegionCode,
                TerritoryGroup = source.TerritoryGroup
        WHEN NOT MATCHED THEN
            INSERT (
                TerritoryAlternateKey, TerritoryName, CountryRegionCode, TerritoryGroup
            )
            VALUES (
                source.TerritoryAlternateKey, source.TerritoryName,
                source.CountryRegionCode, source.TerritoryGroup
            );
        """
    )
    return len(rows)


def load_facts(cursor: pyodbc.Cursor, source: pyodbc.Connection) -> tuple[int, Decimal]:
    extract = source.cursor()
    extract.execute(
        """
        SELECT
            d.ProductID,
            h.CustomerID,
            COALESCE(h.TerritoryID, -1) AS TerritoryID,
            h.OrderDate,
            h.SalesOrderNumber,
            d.SalesOrderDetailID,
            d.OrderQty,
            CAST(d.UnitPrice AS decimal(19,4)) AS UnitPrice,
            CAST(d.UnitPriceDiscount AS decimal(9,4)) AS DiscountPct,
            CAST(d.LineTotal AS decimal(19,4)) AS SalesAmount
        FROM Sales.SalesOrderDetail AS d
        INNER JOIN Sales.SalesOrderHeader AS h
            ON h.SalesOrderID = d.SalesOrderID
        """
    )
    rows: list[tuple] = []
    amount = Decimal("0")
    for product_id, customer_id, territory_id, order_date, number, line_id, qty, price, discount, sales in extract:
        order_day = order_date.date() if hasattr(order_date, "date") else order_date
        date_key = order_day.year * 10000 + order_day.month * 100 + order_day.day
        rows.append(
            (
                int(product_id),
                int(customer_id),
                int(territory_id),
                date_key,
                number,
                int(line_id),
                int(qty),
                price,
                discount,
                sales,
            )
        )
        amount += sales
    extract.close()

    cursor.execute("TRUNCATE TABLE stg_Fact")
    insert_many(
        cursor,
        """
        INSERT INTO stg_Fact (
            ProductID, CustomerID, TerritoryID, OrderDateKey, SalesOrderNumber,
            SalesOrderDetailID, OrderQty, UnitPrice, DiscountPct, SalesAmount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
        sizes=[
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_INTEGER,
            (pyodbc.SQL_WVARCHAR, 25, 0),
            pyodbc.SQL_INTEGER,
            pyodbc.SQL_SMALLINT,
            (pyodbc.SQL_DECIMAL, 19, 4),
            (pyodbc.SQL_DECIMAL, 9, 4),
            (pyodbc.SQL_DECIMAL, 19, 4),
        ],
    )
    cursor.execute("TRUNCATE TABLE Fact_Sales")
    cursor.execute(
        """
        INSERT INTO Fact_Sales (
            ProductKey, CustomerKey, TerritoryKey, OrderDateKey, SalesOrderNumber,
            SalesOrderDetailID, OrderQty, UnitPrice, DiscountPct, SalesAmount
        )
        SELECT
            p.ProductKey,
            c.CustomerKey,
            t.TerritoryKey,
            f.OrderDateKey,
            f.SalesOrderNumber,
            f.SalesOrderDetailID,
            f.OrderQty,
            f.UnitPrice,
            f.DiscountPct,
            f.SalesAmount
        FROM stg_Fact AS f
        INNER JOIN Dim_Product AS p
            ON p.ProductAlternateKey = f.ProductID
        INNER JOIN Dim_Customer AS c
            ON c.CustomerAlternateKey = f.CustomerID
        INNER JOIN Dim_Territory AS t
            ON t.TerritoryAlternateKey = f.TerritoryID
        INNER JOIN Dim_Date AS d
            ON d.DateKey = f.OrderDateKey
        """
    )
    return len(rows), amount


def reconcile(cursor: pyodbc.Cursor, source: pyodbc.Connection, staged_rows: int, staged_amount: Decimal) -> None:
    source_cursor = source.cursor()
    source_cursor.execute(
        """
        SELECT
            COUNT(*) AS Lineas,
            SUM(CAST(LineTotal AS decimal(19,4))) AS Importe
        FROM Sales.SalesOrderDetail
        """
    )
    source_rows, source_amount = source_cursor.fetchone()
    source_cursor.close()

    cursor.execute("SELECT COUNT(*) AS Lineas, SUM(SalesAmount) AS Importe FROM Fact_Sales")
    fact_rows, fact_amount = cursor.fetchone()
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN CustomerType = 'Person' THEN 1 ELSE 0 END) AS Personas,
            SUM(CASE WHEN CustomerType = 'Store' THEN 1 ELSE 0 END) AS Tiendas
        FROM Dim_Customer
        """
    )
    persons, stores = cursor.fetchone()

    print(f"Lineas origen:  {int(source_rows)}")
    print(f"Lineas staging: {staged_rows}")
    print(f"Lineas hecho:   {int(fact_rows)}")
    print(f"Importe origen:  {source_amount}")
    print(f"Importe staging: {staged_amount}")
    print(f"Importe hecho:   {fact_amount}")
    print(f"Personas: {int(persons)} | Tiendas: {int(stores)}")

    errors: list[str] = []
    if int(fact_rows) != int(source_rows) or int(fact_rows) != staged_rows:
        errors.append("El hecho no conserva el grano de SalesOrderDetail.")
    if fact_amount != source_amount or staged_amount != source_amount:
        errors.append("La suma de SalesAmount no cuadra con LineTotal.")
    if int(persons) != 19119 or int(stores) != 701:
        errors.append("Dim_Customer no conserva 19119 personas y 701 tiendas.")
    if errors:
        raise RuntimeError(" ".join(errors))


def publish_view(cursor: pyodbc.Cursor) -> None:
    statement = VIEW_SQL.replace("GO", "").strip()
    cursor.execute(statement)


def main() -> None:
    source = connect(SOURCE_DB)
    warehouse = connect(DWH_DB)
    cursor = warehouse.cursor()
    try:
        ensure_staging(cursor)
        dates = load_dates(cursor, source)
        products = load_products(cursor, source)
        customers = load_customers(cursor, source)
        territories = load_territories(cursor, source)
        print(f"Dim_Date: {dates}")
        print(f"Dim_Product: {products}")
        print(f"Dim_Customer: {customers}")
        print(f"Dim_Territory: {territories}")
        staged_rows, staged_amount = load_facts(cursor, source)
        reconcile(cursor, source, staged_rows, staged_amount)
        publish_view(cursor)
        warehouse.commit()
        print("Carga confirmada. vw_Sales publicada.")
    except Exception:
        warehouse.rollback()
        raise
    finally:
        cursor.close()
        source.close()
        warehouse.close()


if __name__ == "__main__":
    main()
