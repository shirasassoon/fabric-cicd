# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "ed292c68-3154-4243-b874-b3ebd3376de6",
# META       "default_lakehouse_name": "wwilakehouse",
# META       "default_lakehouse_workspace_id": "a4ca8f1d-5d6e-4f09-b3bc-3039c6e789a4",
# META       "known_lakehouses": [
# META         {
# META           "id": "ed292c68-3154-4243-b874-b3ebd3376de6"
# META         }
# META       ]
# META     },
# META     "environment": {
# META       "environmentId": "36a31a36-c5be-a744-4450-d04887999a12",
# META       "workspaceId": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# ### Spark session configuration
# This cell sets Spark session settings to enable _Verti-Parquet_ and _Optimize on Write_. More details about _Verti-Parquet_ and _Optimize on Write_ in tutorial document.

# CELL ********************

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

spark.conf.set("spark.sql.parquet.vorder.enabled", "true")
spark.conf.set("spark.microsoft.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.microsoft.delta.optimizeWrite.binSize", "1073741824")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# #### Approach #1 - sale_by_date_city
# In this cell, you are creating three different Spark dataframes, each referencing an existing delta table.

# CELL ********************

df_fact_sale = spark.read.table("wwilakehouse.dbo.fact_sale") 
df_dimension_date = spark.read.table("wwilakehouse.dbo.dimension_date")
df_dimension_city = spark.read.table("wwilakehouse.dbo.dimension_city")
df_dimension_employee = spark.read.table("wwilakehouse.dbo.dimension_employee")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# In this cell, you are joining these tables using the dataframes created earlier, doing group by to generate aggregation, renaming few of the columns and finally writing it as delta table in the _Tables_ section of the lakehouse.

# CELL ********************

sale_by_date_city = df_fact_sale.alias("sale") \
.join(df_dimension_date.alias("date"), df_fact_sale.InvoiceDateKey == df_dimension_date.Date, "inner") \
.join(df_dimension_city.alias("city"), df_fact_sale.CityKey == df_dimension_city.CityKey, "inner") \
.select("date.Date", "date.CalendarMonthLabel", "date.Day", "date.ShortMonth", "date.CalendarYear", "city.City", "city.StateProvince", "city.SalesTerritory", "sale.TotalExcludingTax", "sale.TaxAmount", "sale.TotalIncludingTax", "sale.Profit")\
.groupBy("date.Date", "date.CalendarMonthLabel", "date.Day", "date.ShortMonth", "date.CalendarYear", "city.City", "city.StateProvince", "city.SalesTerritory")\
.sum("sale.TotalExcludingTax", "sale.TaxAmount", "sale.TotalIncludingTax", "sale.Profit")\
.withColumnRenamed("sum(TotalExcludingTax)", "SumOfTotalExcludingTax")\
.withColumnRenamed("sum(TaxAmount)", "SumOfTaxAmount")\
.withColumnRenamed("sum(TotalIncludingTax)", "SumOfTotalIncludingTax")\
.withColumnRenamed("sum(Profit)", "SumOfProfit")\
.orderBy("date.Date", "city.StateProvince", "city.City")

sale_by_date_city.write.mode("overwrite").format("delta").option("overwriteSchema", "true").save("Tables/dbo/aggregate_sale_by_date_city")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# #### Approach #2 - sale_by_date_employee
# In this cell, you are creating a temporary Spark view by joining 3 tables, doing group by to generate aggregation, renaming few of the columns. 

# CELL ********************

sale_by_date_employee = df_fact_sale.alias("sale") \
.join(df_dimension_date.alias("date"), df_fact_sale.InvoiceDateKey == df_dimension_date.Date, "inner") \
.join(df_dimension_employee.alias("employee"), df_fact_sale.SalespersonKey == df_dimension_employee.EmployeeKey, "inner") \
.select("date.Date", "date.CalendarMonthLabel", "date.Day", "date.ShortMonth", "date.CalendarYear", "employee.PreferredName", "employee.Employee", "sale.TotalExcludingTax", "sale.TaxAmount", "sale.TotalIncludingTax", "sale.Profit")\
.groupBy("date.Date", "date.CalendarMonthLabel", "date.Day", "date.ShortMonth", "date.CalendarYear", "employee.PreferredName", "employee.Employee")\
.sum("sale.TotalExcludingTax", "sale.TaxAmount", "sale.TotalIncludingTax", "sale.Profit")\
.withColumnRenamed("sum(TotalExcludingTax)", "SumOfTotalExcludingTax")\
.withColumnRenamed("sum(TaxAmount)", "SumOfTaxAmount")\
.withColumnRenamed("sum(TotalIncludingTax)", "SumOfTotalIncludingTax")\
.withColumnRenamed("sum(Profit)", "SumOfProfit")\
.orderBy("date.Date", "employee.PreferredName", "employee.Employee")

sale_by_date_employee.write.mode("overwrite").format("delta").option("overwriteSchema", "true").save("Tables/dbo/aggregate_sale_by_date_employee")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# %%sql
# CREATE OR REPLACE TEMPORARY VIEW sale_by_date_employee AS
# SELECT
# 	DD.Date, DD.CalendarMonthLabel
#     , DD.Day, DD.ShortMonth Month, CalendarYear Year
# 	,DE.PreferredName, DE.Employee
# 	,SUM(FS.TotalExcludingTax) SumOfTotalExcludingTax
# 	,SUM(FS.TaxAmount) SumOfTaxAmount
# 	,SUM(FS.TotalIncludingTax) SumOfTotalIncludingTax
# 	,SUM(Profit) SumOfProfit 
# FROM wwilakehouse.dbo.fact_sale FS
# INNER JOIN wwilakehouse.dbo.dimension_date DD ON FS.InvoiceDateKey = DD.Date
# INNER JOIN wwilakehouse.dbo.dimension_Employee DE ON FS.SalespersonKey = DE.EmployeeKey
# GROUP BY DD.Date, DD.CalendarMonthLabel, DD.Day, DD.ShortMonth, DD.CalendarYear, DE.PreferredName, DE.Employee
# ORDER BY DD.Date ASC, DE.PreferredName ASC, DE.Employee ASC

# MARKDOWN ********************

# In this cell, you are reading from the temporary Spark view created in the previous cell and and finally writing it as delta table in the _Tables_ section of the lakehouse.

# MARKDOWN ********************

# sale_by_date_employee = spark.sql("SELECT * FROM sale_by_date_employee")
# sale_by_date_employee.write.mode("overwrite").format("delta").option("overwriteSchema", "true").save("Tables/dbo/aggregate_sale_by_date_employee")
