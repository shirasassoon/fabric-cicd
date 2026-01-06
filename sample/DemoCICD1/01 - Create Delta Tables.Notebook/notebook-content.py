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

# PARAMETERS CELL ********************

env = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if env == "dev":
    connection = "abfss://fabricCICD_FeatureWS@msit-onelake.dfs.fabric.microsoft.com/wwilakehouse.Lakehouse/Tables/dbo/"
elif env == "prod":
    connection = "abfss://fabricCICD_DeploymentWS@msit-onelake.dfs.fabric.microsoft.com/wwilakehouse.Lakehouse/Tables/dbo/"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

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

# ### Fact - Sale
# 
# This cell reads raw data from the _Files_ section of the lakehouse, adds additional columns for different date parts and the same information is being used to create partitioned fact delta table.

# CELL ********************

table_name = "fact_sale"
file_path = "Files/wwi-raw-data/full/fact_sale_1y_full"
view_name = f"vw{table_name}"
spark.read.parquet(file_path).createOrReplaceTempView(view_name)

df = spark.sql(f"SELECT * FROM {view_name}")
df.write.mode("overwrite").format("delta").option("overwriteSchema", "true").save(connection + f"{table_name}/")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Dimensions
# This cell creates a function to read raw data from the _Files_ section of the lakehouse for the table name passed as a parameter. Next, it creates a list of dimension tables. Finally, it has a _for loop_ to loop through the list of tables and call above function with each table name as parameter to read data for that specific table and create delta table.

# CELL ********************

from pyspark.sql.types import *

def loadFullDataFromSource(table_name):
    file_path = 'Files/wwi-raw-data/full/' + table_name
    view_name = f"vw{table_name}"
    df = spark.read.parquet(file_path)
    df.select([c for c in df.columns if c != 'Photo']).createOrReplaceTempView(view_name)
   
    df = spark.sql(f"SELECT * FROM {view_name}")
    df.write.mode("overwrite").format("delta").option("overwriteSchema", "true").save(connection + f"{table_name}/")

full_tables = [
    'dimension_city',
    'dimension_customer',
    'dimension_date',
    'dimension_employee',
    'dimension_stock_item'
    ]

for table in full_tables:
    loadFullDataFromSource(table)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
