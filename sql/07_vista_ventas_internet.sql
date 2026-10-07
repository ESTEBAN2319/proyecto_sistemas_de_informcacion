/*
    Hecho de la entrega corta: solo pedidos de internet (OnlineOrderFlag = 1).

    Fact_Sales sigue guardando los dos canales. Esta vista es la que Power BI
    debe relacionar con Dim_Product, Dim_Territory y Dim_Date.

    Total exigido en la tarjeta:
        Lineas  = 60398
        Importe = 29358677.2207
*/
CREATE OR ALTER VIEW vw_FactInternetSales AS
SELECT
    f.SalesKey,
    f.ProductKey,
    f.TerritoryKey,
    f.OrderDateKey,
    f.SalesOrderNumber,
    f.SalesOrderDetailID,
    f.OrderQty,
    f.UnitPrice,
    f.DiscountPct,
    f.SalesAmount
FROM dbo.Fact_Sales AS f
INNER JOIN AdventureWorks2025.Sales.SalesOrderDetail AS d
    ON d.SalesOrderDetailID = f.SalesOrderDetailID
INNER JOIN AdventureWorks2025.Sales.SalesOrderHeader AS h
    ON h.SalesOrderID = d.SalesOrderID
WHERE h.OnlineOrderFlag = 1;
GO

SELECT
    COUNT(*) AS LineasInternet,
    SUM(SalesAmount) AS ImporteInternet
FROM dbo.vw_FactInternetSales;
GO
