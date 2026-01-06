[StagingDefinition = [Kind = "FastCopy"]]
section Section1;
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "dimension_customer 2_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"dimension_customer 2" = let
  Source = Csv.Document(Web.Contents("https://microsoft-my.sharepoint.com/personal/shirasassoon_microsoft_com/Documents/Apps/Microsoft Power Query/Uploaded Files/dimension_customer 2.csv"), [Delimiter = ",", Columns = 11, Encoding = 65001, QuoteStyle = QuoteStyle.None]),
  #"Promoted headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
  #"Changed column type" = Table.TransformColumnTypes(#"Promoted headers", {{"CustomerKey", Int64.Type}, {"WWICustomerID", Int64.Type}, {"Customer", type text}, {"BillToCustomer", type text}, {"Category", type text}, {"BuyingGroup", type text}, {"PrimaryContact", type text}, {"PostalCode", type text}, {"ValidFrom", type datetime}, {"ValidTo", type datetime}, {"LineageKey", Int64.Type}})
in
  #"Changed column type";
shared #"dimension_customer 2_DataDestination" = let
  Pattern = Lakehouse.Contents([HierarchicalNavigation = null, CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "3709ee0d-d28f-4ee1-bdd6-0ac853f6bff1"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "ba8a019e-9221-4edd-9a5a-7c5447cdff95"]}[Data],
  TableNavigation = Navigation_2{[Id = "dimension_customer", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
