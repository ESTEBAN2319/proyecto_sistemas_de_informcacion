# De AdventureWorks OLTP al informe de ventas por internet

Documento de la entrega corta. Explica cómo se pasó de la base transaccional a un almacén con esquema en estrella, cómo se cargó con un proceso ETL en Python y cómo ese almacén alimenta el informe de Plotly Dash.

## 1. Objeto de la entrega

La pregunta de negocio que cierra esta entrega es:

> ¿Cuál es el importe de las ventas por categoría de producto, territorio y año?

El proceso analizado es la venta de productos por internet. Por eso el informe no usa todo el almacén: usa solo las líneas cuyo pedido tiene `OnlineOrderFlag = 1`.

El informe responde, con el importe como medida principal, cuatro bloques:

1. Evolución temporal.
2. Producto.
3. Territorio del pedido.
4. Combinación de categoría, territorio y año.

Esta entrega no calcula margen, no reparte flete ni impuesto y no analiza clientes.

## 2. Entorno

| Elemento | Valor |
|---|---|
| Motor | SQL Server Express, instancia `localhost\SQLEXPRESS` |
| Autenticación | Windows |
| Base transaccional | `AdventureWorks2025` |
| Base analítica | `AdventureWorks_DWH` |
| ETL | Python, `pyodbc` y Pandas (`etl/load_dwh.py`) |
| Informe | Plotly Dash (`dashboard.py`) |

La base transaccional y la analítica están separadas. Las consultas del informe no leen las tablas normalizadas de ventas. Leen el almacén ya conformado.

## 3. Qué es el OLTP y por qué no se consulta directamente

`AdventureWorks2025` es el sistema operacional. Guarda el pedido en el momento en que ocurre y está organizado para registrar transacciones, no para cruzar categorías, territorios y años en un informe.

La línea de venta no vive en una sola tabla. El importe está en `Sales.SalesOrderDetail`. La fecha, el cliente y el territorio están en `Sales.SalesOrderHeader`. El nombre del producto está en `Production.Product`, y la categoría está dos tablas más arriba, en `Production.ProductSubcategory` y `Production.ProductCategory`. El territorio está en `Sales.SalesTerritory`.

Antes de cargar nada se comprobó que el origen estaba completo:

| Comprobación | Resultado |
|---|---|
| Líneas de `Sales.SalesOrderDetail` | 121.317 |
| Pedidos de `Sales.SalesOrderHeader` | 31.465 |
| Clientes de `Sales.Customer` | 19.820 |
| Clientes con persona | 19.119 |
| Clientes solo tienda | 701 |

19.119 + 701 = 19.820. Esas cifras son la referencia del almacén completo. No son las cifras del informe de internet.

## 4. Decisiones del modelo en estrella

El almacén sigue la metodología de Kimball. El grano se fijó antes de crear las tablas:

**una fila de `Fact_Sales` = una fila de `Sales.SalesOrderDetail`.**

Ese grano es el que permite sumar importes sin duplicar la línea ni mezclar el flete de la cabecera. `Freight` y `TaxAmt` viven en la cabecera del pedido. Si se copiaran en cada línea, el flete se multiplicaría por el número de productos del pedido. Por eso no entran en el hecho.

### 4.1. Tablas

| Tabla analítica | Papel | Origen |
|---|---|---|
| `Dim_Date` | Cuándo se vendió | Se fabrica. No se extrae de una tabla del OLTP |
| `Dim_Product` | Qué se vendió, con categoría y subcategoría ya unidas | `Product`, `ProductSubcategory`, `ProductCategory` |
| `Dim_Customer` | Quién compró y si es persona o tienda | `Customer`, `Person`, `Store` |
| `Dim_Territory` | Dónde se atribuye la venta | Territorio de `SalesOrderHeader` |
| `Fact_Sales` | Cuánto se vendió | `SalesOrderDetail` + cabecera |

Las claves `ProductKey`, `CustomerKey` y `TerritoryKey` son subrogadas. Las asigna SQL Server con `IDENTITY`. El proceso Python no las inventa. La clave de negocio se conserva al lado (`ProductAlternateKey`, `CustomerAlternateKey`, `TerritoryAlternateKey`) para poder reconocer el registro del OLTP y para que una segunda carga actualice la dimensión en lugar de duplicarla.

`DateKey` no es identidad. Es un entero `AAAAMMDD`, para que la fecha del pedido y la dimensión de tiempo hablen el mismo código.

### 4.2. Medidas del hecho

| Columna | Significado |
|---|---|
| `OrderQty` | Unidades de la línea |
| `UnitPrice` | Precio unitario |
| `DiscountPct` | Descuento de la línea (`UnitPriceDiscount`) |
| `SalesAmount` | Importe de la línea |

`SalesAmount` es `LineTotal` guardado como `DECIMAL(19,4)`. La conciliación usa el mismo redondeo en el origen: `CAST(LineTotal AS decimal(19,4))`.

`SalesOrderDetailID` es único en el hecho. Esa restricción impide cargar dos veces la misma línea.

### 4.3. Aspectos que se decidieron a propósito

**El territorio es el del pedido.** En el operacional, el cliente tiene un territorio y el pedido tiene otro. El informe de ventas por territorio usa el de `SalesOrderHeader`, porque es el territorio de la operación. Guardarlo dentro del cliente atribuiría la venta a la región actual de la persona.

**La categoría va dentro del producto.** En el OLTP la jerarquía está normalizada. En el almacén, `Dim_Product` ya trae `CategoryName` y `SubcategoryName`. El informe no necesita volver a unir tres tablas de producto.

**El calendario se fabrica.** `Dim_Date` cubre desde el primer pedido hasta un año después del último, un día por fila. Incluye año calendario y año fiscal. El año fiscal de AdventureWorks empieza el 1 de julio: de julio a diciembre, el año fiscal es el año calendario más uno. El informe de esta entrega usa `CalendarYear`, porque la pregunta habla de «año» y no de ejercicio fiscal.

**El coste no está en el modelo.** El coste actual del producto cambia con el tiempo. Ponerlo en la dimensión y usarlo como margen histórico daría un margen falso. Esta entrega declara que no calcula rentabilidad.

**Los nulos de descripción se sustituyen por «Desconocido».** Un producto sin color o sin subcategoría sigue pudiendo sumarse. No desaparece del informe por un valor nulo.

## 5. Proceso ETL

El script es `etl/load_dwh.py`. El orden no es intercambiable: las dimensiones existen antes que el hecho, porque el hecho guarda sus claves subrogadas.

### Paso 1. Extraer ya unido

Los `JOIN` se hacen en SQL Server, en la misma instancia. Pandas no reconstruye la unión de producto, subcategoría y categoría. Recibe el resultado plano y aplica las reglas de limpieza: nulos, textos vacíos y el tipo de cliente.

- Producto: `Production.Product` con su subcategoría y su categoría.
- Cliente: `Sales.Customer` con `Person.Person` o `Sales.Store`. Si hay persona, el tipo es `Person` y el nombre es nombre y apellido. Si no, el tipo es `Store` y el nombre es el de la tienda.
- Territorio: `Sales.SalesTerritory`, con el nombre, el país y el grupo.
- Hecho: cada línea de `Sales.SalesOrderDetail` con su cabecera. De la cabecera se toman la fecha, el cliente, el territorio y el número de pedido. El importe que viaja al almacén ya va convertido a `DECIMAL(19,4)`.

### Paso 2. Fabricar el tiempo

Python lee la fecha mínima y la máxima de `Sales.SalesOrderHeader` y genera una fila por día. Para cada día calcula año, trimestre, mes, nombre del mes, día de la semana, año fiscal y trimestre fiscal.

### Paso 3. Cargar las dimensiones con `MERGE`

Cada dimensión pasa por una tabla de etapa (`stg_Date`, `stg_Product`, `stg_Customer`, `stg_Territory`). Después, `MERGE` busca por la clave de negocio:

- Si el registro ya existe, se actualizan el nombre y los atributos descriptivos. Es un cambio lento de tipo 1: se conserva la clave subrogada y se sustituye la descripción.
- Si no existe, se inserta y SQL Server asigna la clave subrogada.

### Paso 4. Cargar el hecho

La etapa del hecho guarda las claves de negocio (`ProductID`, `CustomerID`, `TerritoryID`) y el `DateKey`. El `INSERT` final las cambia por las claves subrogadas mediante unión con las dimensiones. Una línea que no encuentre producto, cliente, territorio o fecha no entra. La conciliación posterior lo detecta, porque el número de filas dejaría de coincidir.

Antes de insertar, el proceso vacía `Fact_Sales`. Volver a ejecutar el ETL no duplica líneas: deja otra vez el mismo grano.

### Paso 5. Publicar y abortar si no cuadra

Si las cifras no coinciden, el script revierte la transacción y no deja una carga a medias. Si coinciden, confirma la carga y publica `vw_Sales`, la vista del almacén completo unida a sus cuatro dimensiones.

La carga se ejecutó dos veces. La segunda dejó los mismos totales.

## 6. Conciliación del almacén completo

| Comprobación | Origen | Destino |
|---|---|---|
| Líneas | 121.317 | 121.317 en `Fact_Sales` |
| Importe a 4 decimales | 109.846.381,4250 | 109.846.381,4250 |
| Personas en `Dim_Customer` | 19.119 | 19.119 |
| Tiendas en `Dim_Customer` | 701 | 701 |
| Productos | — | 504 |
| Territorios | — | 10 |
| Fechas | — | 1.492 |

Estas cifras demuestran que el almacén reproduce el operacional. No son el total del informe. El operacional mezcla dos canales.

## 7. Por qué el informe no usa las 121.317 líneas

El pedido marca el canal en `Sales.SalesOrderHeader.OnlineOrderFlag`.

| Canal | Líneas | Importe |
|---|---|---|
| Internet (`OnlineOrderFlag = 1`) | 60.398 | 29.358.677,2207 |
| Resto de pedidos | 60.919 | 80.487.704,2043 |
| Total del hecho | 121.317 | 109.846.381,4250 |

`Fact_Sales` conserva los dos canales. La entrega corta crea encima la vista `vw_FactInternetSales`, definida en `sql/07_vista_ventas_internet.sql`. Esa vista devuelve las mismas columnas del hecho, pero solo las líneas de internet. El filtro se hace una vez, en SQL. El informe no vuelve a `SalesOrderHeader` en cada interacción.

Hay un matiz que no debe usarse como sustituto de ese filtro. En `Sales.Customer` existen 635 registros con persona y tienda a la vez. El ETL los clasifica como persona porque tienen `PersonID`. Por tanto, `CustomerType` no separa el canal. El canal válido para esta pregunta es `OnlineOrderFlag`.

En las líneas de internet, `OrderQty` es siempre 1. La suma de unidades y el número de líneas coinciden. El informe muestra líneas e importe, y no presenta las unidades como si fueran otra medida.

## 8. Del almacén al informe

`dashboard.py` hace una sola consulta al abrir. Une `vw_FactInternetSales` con `Dim_Date`, `Dim_Product` y `Dim_Territory` por las claves subrogadas. El resultado queda en memoria. Los filtros de año, territorio y categoría recortan ese conjunto y recalculan los gráficos. No lanzan de nuevo los cruces del OLTP.

Al cargar, el programa comprueba el control. Si no hay 60.398 líneas o el importe no es 29.358.677,2207, no arranca. Así un informe mal conectado no se presenta con el total de los dos canales.

Se ejecuta con:

```text
python dashboard.py
```

La dirección local es `http://127.0.0.1:8050/`. Sin filtros, la primera tarjeta tiene que mostrar **29.358.677,22 USD**.

### 8.1. Los cuatro bloques

**1. Tiempo.** Importe por `CalendarYear` e importe por `MonthName`. El mes se ordena con el número de mes, de enero a diciembre. Si se ordenara por el nombre, abril aparecería antes que enero. El texto bajo los gráficos indica el año de mayor importe y el mes de mayor y menor importe. Sin filtros, el año de mayor importe es 2024 y el mes de mayor importe es mayo.

**2. Producto.** Importe por `CategoryName` y los diez productos con mayor `SalesAmount`. La subcategoría está en el modelo y puede filtrarse en una ampliación; en esta entrega no ocupa una página propia.

**3. Territorio.** Importe por `TerritoryName`, el territorio del pedido. Sin filtros, el territorio de mayor importe es Australia.

**4. Categoría, territorio y año.** Una matriz de importe con la categoría en filas y el año en columnas, más una tabla con las quince combinaciones de categoría, territorio y año de mayor importe. Este bloque es la respuesta directa a la pregunta de la asignatura. Los filtros de arriba permiten fijar un territorio o un año y leer la matriz ya recortada.

Los filtros son comunes. Un año elegido cambia a la vez el tiempo, el producto, el territorio y la matriz. El importe de la tarjeta pasa a ser el del filtro, no el de control. Para volver al control hay que dejar los tres filtros vacíos.

## 9. Qué queda fuera y por qué

| Pregunta o tema | Decisión en esta entrega |
|---|---|
| Margen, coste y rentabilidad | Fuera. No hay coste de la línea en la fecha del pedido |
| Flete e impuesto | Fuera. Están en la cabecera y duplicarían el importe |
| Clientes, frecuencia y gasto medio | Fuera de los cuatro bloques. `Dim_Customer` está cargada para el almacén, no para este informe |
| Crecimiento contra el año anterior y estacionalidad elaborada | Fuera. El bloque de tiempo muestra el importe por año y por mes, que es la base para leerlas, pero no calcula una tasa |
| Año fiscal | Calculado en `Dim_Date` y no usado en los gráficos, para no mezclar dos calendarios en la misma pregunta |
| Reventa | Conservada en `Fact_Sales` y excluida de `vw_FactInternetSales` |

## 10. Orden para reproducir la entrega

1. Comprobar el origen con `sql/01_verificar_oltp.sql`.
2. Crear el esquema con `sql/02_crear_esquema_estrella.sql`.
3. Confirmar que el hecho está vacío antes de la primera carga con `sql/03_verificar_dwh_vacio.sql`.
4. Ejecutar `python etl/load_dwh.py` y repetirlo. Las dos ejecuciones deben dejar 121.317 líneas y 109.846.381,4250 de importe.
5. Crear la vista de internet con `sql/07_vista_ventas_internet.sql`. El resultado tiene que ser 60.398 líneas y 29.358.677,2207.
6. Revisar el conjunto con `sql/06_verificacion_final.sql`. Las catorce pruebas del almacén completo tienen que devolver `OK`.
7. Ejecutar `python dashboard.py` y comprobar la tarjeta de 29.358.677,22 USD sin filtros.

## 11. Cifras que deben citarse juntas

Conviene no mezclarlas en la defensa:

- **121.317 líneas y 109.846.381,4250 USD** demuestran que el ETL cargó todo el operacional.
- **60.398 líneas y 29.358.677,22 USD** son las ventas por internet y el único total válido del informe.

El segundo no sustituye al primero. El primero no debe aparecer como respuesta a la pregunta de ventas por internet.
