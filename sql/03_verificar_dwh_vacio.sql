/*
    Paso 3. Confirma que el destino existe, tiene las cinco tablas y el hecho está vacío.
    Resultado exigido: Dim_Customer, Dim_Date, Dim_Product, Dim_Territory, Fact_Sales
    y FilasHecho = 0.
*/
USE AdventureWorks_DWH;
GO

SELECT name
FROM sys.tables
ORDER BY name;

SELECT COUNT(*) AS FilasHecho FROM Fact_Sales;
GO
