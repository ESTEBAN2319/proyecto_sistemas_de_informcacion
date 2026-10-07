/*
    Paso 1. Comprueba el OLTP antes de tocar el Data Warehouse.

    Origen real de esta máquina: AdventureWorks2025 en localhost\SQLEXPRESS.
    Resultado de referencia ya obtenido:
        LineasPedido = 121317
        Pedidos      = 31465
        Clientes     = 19820
        Store        = 701
        Person       = 19119
*/
USE AdventureWorks2025;
GO

SELECT COUNT(*) AS LineasPedido FROM Sales.SalesOrderDetail;
SELECT COUNT(*) AS Pedidos FROM Sales.SalesOrderHeader;
SELECT COUNT(*) AS Clientes FROM Sales.Customer;

SELECT
    CASE WHEN PersonID IS NOT NULL THEN 'Person' ELSE 'Store' END AS TipoCliente,
    COUNT(*) AS Clientes
FROM Sales.Customer
GROUP BY CASE WHEN PersonID IS NOT NULL THEN 'Person' ELSE 'Store' END;
GO
