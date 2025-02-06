# SciCat Ingestor Schemas

The schema files provides a specific set of directives that are used by the ingestor to collect needed information from multiple sources (being data file or scicat or else) and populate the dataset entry in SciCat.
These files have extension _imsc.json_ which stands for SciCat *i*ngestor *m*etadata *sc*hema and are json files with some mandatory high level fields.  

The schemas files contains the following information:
- the schema selection, which are the rules that specify when to apply such schemato which file
- variables definition, meaning which information are gathered and how, and how the are saved in local variables,
- dataset creation, which instruct how to use the variables to populate the different fields of available in a SciCat dataset 

## File Sections
An imsc file has three main sections:
- *general*
  This section contains a group of fields which includes unique id, name of the schema, which instrument is associated with and the rules for matching to which data file it applies.
  Please visit the detailed [general section documentation](./SCHEMAS_GENERAL_SECTION.md) for more information.
- *variables*
  The fields in this section define a set of pair key-values retrieved from multiple different sources that are later used in the schema section.
  Please visit the detailed [variables section documentation](./SCHEMAS_VARIABLES_SECTION.md) for more information.
- *schema*
  The fields is this section define which variable's values are assigned to the specific SciCat dataset fields. They explain how to populate the SciCat dataset object.
  Please visit the detailed [general section documentation](./SCHEMAS_SCHEMA_SECTION.md) for more information.

## File Structure
When viewing or editing an imsc file, the user is presented with the high level json structure
```
{
  "order": <NUMBER>,
  "id": <UNIQUE_STRING>,
  "name" : <NAME_OF_THE_SCHEMA>,
  "instrument" : <COMMA_SEPARATED_LIST_OF_INSTRUMENTS_NAMES>,
  "selector" : <OBJECT_WITH_SELECTION_RULES>,
  "variables" : {
    <VARIABLE_NAME> : <VARIABLE_DEFINITION>
  },
  "schemas: : {
    <MNEMONIC_ENTRY_NAME> : <SCHEMA_ENTRY_DEFINITION>
  }
}

```
