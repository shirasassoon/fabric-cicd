[DefaultOutputDestinationSettings = [DestinationDefinition = [Kind = "Reference", QueryName = "DefaultDestination", IsNewTarget = true], UpdateMethod = [Kind = "Replace"], DestinationTypeSettings = [Kind = "Table"]], StagingDefinition = [Kind = "FastCopy"]]
section Section1;
shared DefaultDestination = Lakehouse.Contents([EnableFolding = false]){[workspaceId = "a4ca8f1d-5d6e-4f09-b3bc-3039c6e789a4"]}[Data]{[lakehouseId = "ed292c68-3154-4243-b874-b3ebd3376de6"]}[Data];
[DataDestinations = {[Definition = [Kind = "Reference", QueryName = "dimension_customer 1_DataDestination", IsNewTarget = true], Settings = [Kind = "Automatic", TypeSettings = [Kind = "Table"]]]}]
shared #"dimension_customer 1" = let
  Source = Csv.Document(Web.Contents("https://microsoft-my.sharepoint.com/personal/shirasassoon_microsoft_com/Documents/Apps/Microsoft Power Query/Uploaded Files/dimension_customer 1.csv"), [Delimiter = ",", Columns = 11, Encoding = 65001, QuoteStyle = QuoteStyle.None]),
  #"Promoted headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
  #"Changed column type" = Table.TransformColumnTypes(#"Promoted headers", {{"CustomerKey", Int64.Type}, {"WWICustomerID", Int64.Type}, {"Customer", type text}, {"BillToCustomer", type text}, {"Category", type text}, {"BuyingGroup", type text}, {"PrimaryContact", type text}, {"PostalCode", type text}, {"ValidFrom", type datetime}, {"ValidTo", type datetime}, {"LineageKey", Int64.Type}})
in
  #"Changed column type";
shared #"dimension_customer 1_DataDestination" = let
  Pattern = Lakehouse.Contents([HierarchicalNavigation = null, CreateNavigationProperties = false, EnableFolding = false]),
  Navigation_1 = Pattern{[workspaceId = "a4ca8f1d-5d6e-4f09-b3bc-3039c6e789a4"]}[Data],
  Navigation_2 = Navigation_1{[lakehouseId = "ed292c68-3154-4243-b874-b3ebd3376de6"]}[Data],
  TableNavigation = Navigation_2{[Id = "dimension_customer", ItemKind = "Table"]}?[Data]?
in
  TableNavigation;
