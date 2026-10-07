/*
    Verificación final. Abrir en SQL Server Management Studio como consulta nueva
    y ejecutar completo (F5) contra localhost\SQLEXPRESS.

    No depende de la base seleccionada en la barra: usa nombres de tres partes.
    Cada fila debe decir OK. Una sola FALLO invalida el informe de Power BI.

    No ejecutar sql/03_verificar_dwh_vacio.sql: ese script correspondía al
    esquema vacío, antes de la carga.
*/
SELECT
    Prueba,
    Esperado,
    Obtenido,
    CASE WHEN Esperado = Obtenido THEN 'OK' ELSE 'FALLO' END AS Resultado
FROM (
    SELECT
        'Lineas OLTP' AS Prueba,
        CAST(121317 AS decimal(19, 4)) AS Esperado,
        CAST((
            SELECT COUNT(*)
            FROM AdventureWorks2025.Sales.SalesOrderDetail
        ) AS decimal(19, 4)) AS Obtenido

    UNION ALL
    SELECT
        'Lineas Fact_Sales',
        CAST(121317 AS decimal(19, 4)),
        CAST((SELECT COUNT(*) FROM AdventureWorks_DWH.dbo.Fact_Sales) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Lineas vw_Sales',
        CAST(121317 AS decimal(19, 4)),
        CAST((SELECT COUNT(*) FROM AdventureWorks_DWH.dbo.vw_Sales) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Lineas unicas SalesOrderDetailID',
        CAST(121317 AS decimal(19, 4)),
        CAST((
            SELECT COUNT(DISTINCT SalesOrderDetailID)
            FROM AdventureWorks_DWH.dbo.Fact_Sales
        ) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Importe origen',
        CAST(109846381.4250 AS decimal(19, 4)),
        (
            SELECT SUM(CAST(LineTotal AS decimal(19, 4)))
            FROM AdventureWorks2025.Sales.SalesOrderDetail
        )

    UNION ALL
    SELECT
        'Importe Fact_Sales',
        CAST(109846381.4250 AS decimal(19, 4)),
        (SELECT SUM(SalesAmount) FROM AdventureWorks_DWH.dbo.Fact_Sales)

    UNION ALL
    SELECT
        'Importe vw_Sales',
        CAST(109846381.4250 AS decimal(19, 4)),
        (SELECT SUM(SalesAmount) FROM AdventureWorks_DWH.dbo.vw_Sales)

    UNION ALL
    SELECT
        'Clientes persona',
        CAST(19119 AS decimal(19, 4)),
        CAST((
            SELECT COUNT(*)
            FROM AdventureWorks_DWH.dbo.Dim_Customer
            WHERE CustomerType = 'Person'
        ) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Clientes tienda',
        CAST(701 AS decimal(19, 4)),
        CAST((
            SELECT COUNT(*)
            FROM AdventureWorks_DWH.dbo.Dim_Customer
            WHERE CustomerType = 'Store'
        ) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Productos',
        CAST(504 AS decimal(19, 4)),
        CAST((SELECT COUNT(*) FROM AdventureWorks_DWH.dbo.Dim_Product) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Territorios',
        CAST(10 AS decimal(19, 4)),
        CAST((SELECT COUNT(*) FROM AdventureWorks_DWH.dbo.Dim_Territory) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Fechas',
        CAST(1492 AS decimal(19, 4)),
        CAST((SELECT COUNT(*) FROM AdventureWorks_DWH.dbo.Dim_Date) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Fechas fiscales mal asignadas',
        CAST(0 AS decimal(19, 4)),
        CAST((
            SELECT COUNT(*)
            FROM AdventureWorks_DWH.dbo.Dim_Date
            WHERE (Month >= 7 AND FiscalYear <> CalendarYear + 1)
               OR (Month <= 6 AND FiscalYear <> CalendarYear)
        ) AS decimal(19, 4))

    UNION ALL
    SELECT
        'Vista vw_Sales presente',
        CAST(1 AS decimal(19, 4)),
        CAST((
            SELECT COUNT(*)
            FROM AdventureWorks_DWH.sys.views
            WHERE name = 'vw_Sales'
        ) AS decimal(19, 4))
) AS pruebas
ORDER BY Resultado, Prueba;
GO
