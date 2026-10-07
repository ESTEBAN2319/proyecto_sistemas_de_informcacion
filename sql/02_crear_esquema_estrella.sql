/*
    Paso 2. Reescribe el esquema en estrella.

    Alcance cerrado:
        - Grano: una fila de Fact_Sales = una fila de Sales.SalesOrderDetail.
        - Decisiones: producto, territorio del pedido, tiempo y canal (Person/Store).
        - Esta entrega no calcula margen.
        - Flete e impuesto no entran en el hecho.
        - IDENTITY asigna las claves subrogadas. El ETL no las inventa.

    Ejecutar completo, de arriba abajo, en localhost\SQLEXPRESS.
*/

IF DB_ID(N'AdventureWorks_DWH') IS NULL
    CREATE DATABASE AdventureWorks_DWH;
GO

USE AdventureWorks_DWH;
GO

DROP TABLE IF EXISTS Fact_Sales;
DROP TABLE IF EXISTS Dim_Product;
DROP TABLE IF EXISTS Dim_Customer;
DROP TABLE IF EXISTS Dim_Territory;
DROP TABLE IF EXISTS Dim_Date;
GO

CREATE TABLE Dim_Date (
    DateKey INT PRIMARY KEY,                 -- AAAAMMDD
    FullDate DATE NOT NULL UNIQUE,
    CalendarYear INT NOT NULL,
    FiscalYear INT NOT NULL,                 -- julio-junio: jul-dic pertenece al año siguiente
    Quarter INT NOT NULL,
    FiscalQuarter INT NOT NULL,
    Month INT NOT NULL,
    MonthName VARCHAR(20) NOT NULL,
    Day INT NOT NULL,
    DayOfWeekName VARCHAR(20) NOT NULL
);

CREATE TABLE Dim_Product (
    ProductKey INT IDENTITY(1,1) PRIMARY KEY,
    ProductAlternateKey INT NOT NULL UNIQUE, -- Production.Product.ProductID
    ProductName NVARCHAR(50) NOT NULL,
    ProductNumber NVARCHAR(25) NOT NULL,
    Color NVARCHAR(15) NOT NULL,
    SubcategoryName NVARCHAR(50) NOT NULL,
    CategoryName NVARCHAR(50) NOT NULL
);

CREATE TABLE Dim_Customer (
    CustomerKey INT IDENTITY(1,1) PRIMARY KEY,
    CustomerAlternateKey INT NOT NULL UNIQUE, -- Sales.Customer.CustomerID
    CustomerType VARCHAR(10) NOT NULL,        -- Person o Store
    CustomerName NVARCHAR(150) NOT NULL
);

CREATE TABLE Dim_Territory (
    TerritoryKey INT IDENTITY(1,1) PRIMARY KEY,
    TerritoryAlternateKey INT NOT NULL UNIQUE, -- Sales.SalesTerritory.TerritoryID del pedido
    TerritoryName NVARCHAR(50) NOT NULL,
    CountryRegionCode NVARCHAR(3) NOT NULL,
    TerritoryGroup NVARCHAR(50) NOT NULL
);

CREATE TABLE Fact_Sales (
    SalesKey INT IDENTITY(1,1) PRIMARY KEY,
    ProductKey INT NOT NULL,
    CustomerKey INT NOT NULL,
    TerritoryKey INT NOT NULL,
    OrderDateKey INT NOT NULL,
    SalesOrderNumber NVARCHAR(25) NOT NULL,
    SalesOrderDetailID INT NOT NULL UNIQUE,
    OrderQty SMALLINT NOT NULL,
    UnitPrice DECIMAL(19,4) NOT NULL,
    DiscountPct DECIMAL(9,4) NOT NULL,
    SalesAmount DECIMAL(19,4) NOT NULL,

    CONSTRAINT FK_FactSales_Product
        FOREIGN KEY (ProductKey) REFERENCES Dim_Product (ProductKey),
    CONSTRAINT FK_FactSales_Customer
        FOREIGN KEY (CustomerKey) REFERENCES Dim_Customer (CustomerKey),
    CONSTRAINT FK_FactSales_Territory
        FOREIGN KEY (TerritoryKey) REFERENCES Dim_Territory (TerritoryKey),
    CONSTRAINT FK_FactSales_Date
        FOREIGN KEY (OrderDateKey) REFERENCES Dim_Date (DateKey)
);
GO

CREATE INDEX IX_FactSales_Product ON Fact_Sales (ProductKey);
CREATE INDEX IX_FactSales_Customer ON Fact_Sales (CustomerKey);
CREATE INDEX IX_FactSales_Territory ON Fact_Sales (TerritoryKey);
CREATE INDEX IX_FactSales_OrderDate ON Fact_Sales (OrderDateKey);
GO
