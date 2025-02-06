# Schemas General fields

This section contains the group of fields that should help admins and data curators to identify this specific schema. It also contains the fields for ordering and selection.

## Fields

- id: _string_  
  Unique id of this schema. Subsequent version of the same schema should have different ids. We suggest to use uuids, but there are not restrictions on the format.
- name: _string_  
  Name of this schema. This field is to be used by admin only and be able to assign a meaningful name for the configuration.
- instrument _string_  
  Comma separate list of instrument names where this schema would be applied to ingest the data from. This field is for admin use only. It provides an additional location to store information for easy identification and troubleshoot.
- selector _object_ or _string_ 
  This field contains the condition that needs to be met for the schema to be used when ingesting the input data file.  
  In the example below, the schema will be applied to files whose full path start with `/ess/data/coda` or `/ess/raw/coda`
  ```
  "selector" : {
    "or" : [
      "filename:starts_with:/ess/data/coda",
      "filename:starts_with:/ess/raw/coda"
    ]
  }
  ```
  In the next example, the selector indicates that the schema will be applied to files where the full path file name contains the word `coda`.
  ```
  "selector" : "filename:contains:coda" 
  ```
  The individual selectors can be placed combined with _and_ and _or_ operators.
  Each individual selector can be a single string composed of three parts divided by semicolon, called condensed selector, or an object with the three equivalend fields, called expanded selector. The three components of each selector are:
  - source of the value to use of the first operand
  - operator
  - second operand.
  The syntax of the condensed selector is:
  ```
  source_op_1:operator:op_2
  ```
  The syntax of the expanded selector is:
  ```
  {
    "source" : <SOURCE_OF_THE_FIRST_OPERAND>,
    "operator" : <OPERATOR>
    "operand_2" : <OPERAND_2>
  }
  ```
  The source can be set to the following options:
  - filename: the full path of the data file as provided as input argument with option *--nexus-file*
  - datafile: same as filename
  - nexusfile: same as filename

  Available operators are:
  - starts_with: the value retrieved from the source should start with  *operand_2*
  - contains: the value retrieved from the source should contain *operand_2*

  Operand two is interpreted as string. 

- order _integer_ 
  This field is used by the ingestor to order the schemas prior to evaluate the selector to select the correct schema for the file. The lower the order is, the earlier the schema is evaluated for applicability. In case a file matches multiple schema selector, the schema with lower order number will be used.

