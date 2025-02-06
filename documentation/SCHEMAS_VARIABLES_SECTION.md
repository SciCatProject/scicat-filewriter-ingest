# Schemas Variables Section
The variables section of the imsc file, contains the definitions for variables and their values prepared to be used in the schema section.
It can contains as many definitions as the user needs in order to define the correct values to populate the dataset metadata in the later section.
The order of the definitions in the section is important, as the ingestor will follow it when processing the file, and variables defined earlier will be available to be used in defining later ones.

## Section Structure
When working with the variable section of the imsc file, the user is presented with the following sub satructure:
```
"variables" : {
  <VARIABLE_NAME_1> : <VARIABLE_DEFINITION_1>,
  <VARIABLE_NAME_2> : <VARIABLE_DEFINITION_2>,
}
```

This will results in a structure containing the key-value pairs that the offline ingestor will save in memory and will be available when evaluating the schema section

Example: given the following variables structure:
```
"variables" : {
  "job_id": {
    "source": "VALUE",
    "value": "26e95e54",
    "value_type": "string"
  },
  "owner_group": {
    "source": "VALUE",
    "value": "group_<proposal_id>",
    "value_type": "string"
  },
  "access_groups": {
    "source": "VALUE",
    "value": ["group_1", "group_2"],
    "value_type": "string[]"
  }
}
```
The variables structure that will be stored in memory will be the following:
```
"variables" : {
  "job_id": "26e95e54",
  "owner_group": "group_26e95e54",
  "access_groups": ["group_1", "group_2"],
}
```

## Variable definition
Each value definition has the following structure:
```
"<variable_name>" : {
    "source": "<source_of_value>",
    "value_type": "<type_of_value>",
    ...additional fields...
}
```
This definition will define in the ingestor memory a variable of name  *variable_name* of type *type_of_value* and the value of such variable will be retrieved from *source_of_value*. Additional fields might be required and are dependent from which source is specified.   

## Sources
Currently, the source field accepts the following options:
- **NXS**  
  the nexus file specified as input argument with the option --nexus-file, also referred to as the data file
- **SC**
  the api of the SciCat instance of reference which the ingestor is configured to interact with the configuration option _scicat.host_
- **VALUE**
  a static value specified directly in the definition

## Value types
The field *value_type* accept the following options:
- string
- dict (equivalent to a typescript object)
- list (equivalent to a typescript array)
- date (ISO8601 format)
- integer
- string[] (an array of strings)


## Variables Definitions by Sources
### NXS (nexus)
This definition define a variables with a value retrieved from the nexus data file at the specific nexus path.  
The expected definition has the following structure:
```
"<variable_name>" : {
    "source": "NXS",
    "path": "<nexus_path>",
    "value_type": "<type_of_value>",
}
```
This definition defines a variable of name  *variable_name* of type *type_of_value* and the value will be retrieved from the nexus file provided in input at the nexus path *nexus_path*.  
The following is a concrete example:
```
"job_id": {
    "source": "NXS",
    "path": "/entry/entry_identifier_uuid",
    "value_type": "string"
},
```
This definition will define a variable named *job_id* whose value is a string retrieved from the input nexus file at the internal path */entry/entry_identifier_uuid*.

### VALUE
This definition define a variable whose value is assigned directly from static value specified in the definition itself.
The basic structure of a value definition is as follow:
```
"<variable_name>" : {
    "source": "VALUE",
    ["operator": "<OPERATOR_NAME>",]
    "value": "<variable_value>",
    "value_type": "<type_of_value>",
}
```
This definition defines a variable of name  *variable_name* of type *type_of_value* and the value is *variable_value*. Additionally if the field _operator_ is specified, the operator *operator_name* is applied to the value before been assigned to the variable.  
The variable value can contain references to previously defined variables with the syntax _<variable_name>_. The ingestor automatically inject the value of the referenced variable while evaluating the value of the current variable.

An example of a basic value definition is:
```
"pid": {
    "source": "VALUE",
    "value": "20.500.12269/23c40f04-de76-11ef-897f-bb426f5f764f",
    "value_type": "string"
},
```
This definition defines a variable named *pid* with the value of *20.500.12269/23c40f04-de76-11ef-897f-bb426f5f764f* of type *string*.

An example of value definition using variables injection is:
```
"pid": {
    "source": "VALUE",
    "value": "20.500.12269/<job_id>",
    "value_type": "string"
},
```
Let's assume that the variable *job_id* is already defined and has a value of *cc59b538-de76-11ef-b192-d3d4305b1b90*. This definition results in a variable named *pid* with the value of *20.500.12269/cc59b538-de76-11ef-b192-d3d4305b1b90* of type *string*. As previously explained, the ingestor check the value for variable names, it recognizes that there is a reference to the variable *job_id*, and proceed with the substitution of the variable references with its current value.

#### Value Operators
The value definition can contain an additional field named *operator* which specifies an operator that will be applied to the value once has been defined.
The current list of the operators available with their functionality is the following:
- getitem
  Assumes that the value is a list or a dict and return just the selected element or key. This operator requires the following additional fields:
  The full value definition with the _getitem_ operator is the following:
  ```
  <VARIABLE_NAME>: {
    "source": "VALUE",
    "operator": "getitem",
    "value": <VARIABLE_VALUE>,
    "field" : <FIELD_NAME>,
    "value_type": "string"
  },
  ```
  In the following example, we are assuming that the ingestor has already defined a variable named *proposal_data*, which is a dict with, among others, contains a field named *pi_firstname* which is a string, like:
  ```
  "proposal_data": {
    "pi_firstname" : "John",
    "pi_lastname" : "Doe",
    ...
  }
  ```
  Given the value definition as follow:
  ```
  "pi_firstname": {
    "source": "VALUE",
    "operator": "getitem",
    "value": "<proposal_data>",
    "field" : "pi_firstname",
    "value_type": "string"
  }
  ```
  The results will be a variable named *pi_firstname* with value _John_.
- to_upper
  Convert the value to upper case
- to_lower
  Convert the value to lower case
- urlsafe
  Convert the value to a safe format to be used in a url. Please check the ... documentation for more information
- join_with_space
  Assumes that the value is an array and joins all the elements of the array with a space as separating character. The output is a string
- dirname
  Assumes that the value is a file system path and return the parent folder, aka it eliminates the last element from the path.
- dirname-2
  Assumes that the value is a file system path and return the grand-parent folder, aka it eliminates the last two elements from the path.
- str_replace
  Replace a pattern with a string within the value. This operator requires the following additional fields:
  The full value definition with the _str_replace_ operator is the following:
  ```
  <VARIABLE_NAME>: {
    "source": "VALUE",
    "operator": "str-replace",
    "value": <VARIABLE_VALUE>,
    "pattern": <REPLACEMENT_PATTERN>,
    "replacement": <REPLACEMENT_STRING>,
    "value_type": "string"
  },

  ```
  In the following example, we assume that the ingestor has already defined a variable named *raw_folder* with value _/ess/raw/instrument/year/proposal_.
  The value will be assigned to a new variable named *source_folder*.
  Once the assignment has been performed, the variable engine will look for the pattern _ess/raw_ and substitute it with the string _ess/data_.
  Given the value definition:
  ```
  "source_folder": {
    "source": "VALUE",
    "operator": "str-replace",
    "value": "<raw_folder>",
    "pattern": "ess/raw",
    "replacement": "ess/data",
    "value_type": "string"
  },
  ```
  It will define a variable named *source_folder* with value _/ess/data/instrument/year/proposal_.

### SC (SciCat)
This definition define a variable whose value is retrieved from a SciCat instance placing a request to the URL specified.
The basic structure of a value definition is as follow:
```
"<VARIABLE_NAME>" : {
    "source": "SC",
    "url": "<ENDPOINT_URL>",
    "field" : "<NAME_OF_THE_FIELD>
    "value_type": "<TYPE_OF_VALUE>",
}
```
This definition defines a variable of name  *variable_name* of type *type_of_value* with the value 
retrieved from the SciCat instance endpoint specified by the field _url_. 
If _field_ is specified, it will extract just the field from the results, otherwise it will assign the full object returned by scicat.
The url specified is the relative path of the endpoint and it is relative to the url of the SciCat instance of reference.

An example of a SciCat definition is:
```
"proposal_data": {
  "source": "SC",
  "url": "proposals/<proposal_id>",
  "field" : "",
  "value_type": "dict"
},
```
This definition will instruct the ingestor to put through a GET request to the endpoint proposals to retrieve the specific proposal whose id is stored in the variable *proposal_id*.
The results returned by SciCat should be a dict containing all the information regarding the proposal selected.
The dict will be assigned to the variable named *proposal_data*.