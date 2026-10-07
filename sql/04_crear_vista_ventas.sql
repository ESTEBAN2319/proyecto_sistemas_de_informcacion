/*
    Vista que consume Power BI.
    Una fila = una línea de pedido, con sus cuatro dimensiones ya resueltas.
*/
CREATE OR ALTER VIEW vw_Sales AS
SELECT
    f.SalesOrderNumber,
    f.SalesOrderDetailID,
    f.OrderQty,
    f.UnitPrice,
    f.DiscountPct,
    f.SalesAmount,
    d.FullDate,
    d.CalendarYear,
    d.FiscalYear,
    d.Quarter,
    d.FiscalQuarter,
    d.Month,
    d.MonthName,
    d.DayOfWeekName,
    p.ProductName,
    p.ProductNumber,
    p.Color,
    p.SubcategoryName,
    p.CategoryName,
    c.CustomerType,
    c.CustomerName,
    t.TerritoryName,
    t.CountryRegionCode,
    t.TerritoryGroup
FROM Fact_Sales AS f
INNER JOIN Dim_Date AS d ON d.DateKey = f.OrderDateKey
INNER JOIN Dim_Product AS p ON p.ProductKey = f.ProductKey
INNER JOIN Dim_Customer AS c ON c.CustomerKey = f.CustomerKey
INNER JOIN Dim_Territory AS t ON t.TerritoryKey = f.TerritoryKey;
GO
