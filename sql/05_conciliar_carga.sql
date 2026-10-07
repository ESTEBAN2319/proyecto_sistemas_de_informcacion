/*
    Prueba de la carga. El hecho debe repetir el grano del OLTP.
    SalesAmount se guardó como DECIMAL(19,4), así que la suma origen
    usa el mismo redondeo.
*/
SELECT COUNT(*) AS LineasOrigen
FROM AdventureWorks2025.Sales.SalesOrderDetail;

SELECT COUNT(*) AS LineasDestino
FROM Fact_Sales;

SELECT SUM(CAST(LineTotal AS decimal(19,4))) AS ImporteOrigen
FROM AdventureWorks2025.Sales.SalesOrderDetail;

SELECT SUM(SalesAmount) AS ImporteDestino
FROM Fact_Sales;

SELECT CustomerType, COUNT(*) AS Clientes
FROM Dim_Customer
GROUP BY CustomerType
ORDER BY CustomerType;
GO
