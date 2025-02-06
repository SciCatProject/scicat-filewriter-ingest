# SciCat Ingestor Schemas
The schema section of the imsc file, contains the assignments which specify how to populate the SciCat dataset fields specified in the input dto using values of the variables previously defined in the variables section.
This section should contains at least as many assignments are needed for the required fields.
In this section the order is not important.
There are two different type of assignments:
- high level field
- scientific metadata field

## Section Structure
When working with the schema section of the imsc file, the user is presented with the following sub structure:
```
"schema" : {
  <ASSIGNMENT_NAME_1> : <FIELD_ASSIGNMENT_1>,
  <ASSIGNMENT_NAME_2> : <FIELD_ASSIGNMENT_2>,
}
```

This will will instruct the ingestor to assign the specified value to the specified field in the SciCat dataset dto.

Example: given the following schema structure:
```
"schema" : {
  "pid": {
    "field_type": "high_level",
    "machine_name": "pid",
    "value": "<pid>",
    "type": "string"
  },
  "type" : {
    "field_type": "high_level",
    "machine_name": "type",
    "value": "raw",
    "type": "string"
  },
  "proposal_id": {
    "field_type": "high_level",
    "machine_name": "proposalId",
    "value": "<proposal_id>",
    "type": "string"
  },
  "dataset_name": {
    "field_type": "high_level",
    "machine_name": "datasetName",
    "value": "<dataset_name>",
    "type": "string"
  }
}
```
Will assign the value of the variable _pid_ to the dataset field _pid_, the value _raw_ to the dataset field _type_, the value of the variable *proposal_id* to the dataset field _proposalId_ and, at last, the value of the variable *dataset_name* to the datasets field _datasetName_.

As you can notice, also in the schema section, the values can leverage the variable injection using the variable name wrapped with angle brackets.

## Field assignment
As mentioned before, there are two type of fields: *high_level* and *scientific_metadata* ones.
The two assignements share most of the syntax with some differences. We cover them separately.
The assignment name is not used byt he ingestor, it is most for the benefit of the data curator, so she/he can use a more meaningful name when the assignment might be complicated at first glance.

### High level field assignment
A high level field assignment has the following syntax:
```
<ASSIGNMENT_NAME>: {
  "field_type": "high_level",
  "machine_name": <SCICAT_DATASET_FIELD>,
  "value": <FIELD_VALUE>,
  "type": <VALUE_TYPE>
}
```

The *scicat_dataset_field* is the name of one of the field listed in the SciCat dataset create dto. An arbitrary field name will generate an error when sendign the request to SciCat BE and the dataset entry will not be created.
Assignement *assignment_name* will assign the value *field_value* of type *field_type* to the dataset field *scicat_dataset_field* which is listed in the dataset create dto.

A simple assignment can be:
```
"type" : {
  "field_type": "high_level",
  "machine_name": "type",
  "value": "raw",
  "type": "string"
},
```
This assignment will assign the value _raw_ to the dataset field _type_.

An example with variable injection is:
```
"creation_location": {
  "field_type": "high_level",
  "machine_name": "creationLocation",
  "value": "ESS:CODA:<instrument_name>",
  "type": "string"
},
```
Assuming that variable *instrument_name* has the value _dream_, this assignment will assign the string "ESS:CODE:dream" to the dataset field _creationLocation_.

### Scientific metadata field assignment
A scientific metadata assignment has the following syntax:
```
<ASSIGNMENT_NAME>: {
  "field_type": "scientific_metadata",
  "machine_name": <SCIENTIFIC_METADATA_MACHINE_FIELD_NAME>,
  "human_name": <SCIENTIFIC_METADATA_HUMAN_FIELD_NAME>,
  "value": <FIELD_VALUE>,
  "type": <VALUE_TYPE>
}
```
In this case assignment *assignment_name* will create a scientific metadata entry named _scientific_metadata_machine_name_ (which is machine consumable) with a value of *field_value* of type *value_type*. It will also add the optional field *human_name* with value *scientific_metadata_human_field_name* which will be used in SciCat to show this entry in the frontend.

Two examples of assignments are:
```
"start_time": {
  "field_type": "scientific_metadata",
  "machine_name": "start_time",
  "human_name": "Start Time",
  "value": "<start_time>",
  "type": "date"
},
"end_time": {
  "field_type": "scientific_metadata",
  "machine_name": "end_time",
  "human_name": "End Time",
  "value": "<end_time>",
  "type": "date"
},
```

Assuming that variable *start_time* has value _2025-01-20 12:00:00_ and variable *end_time* _2025-01-20 12:30:00_, this assignments will results in the following metadata definition in scicat:
```
"scientific_metadata" { 
  "start_time" : {
    "value" : "2025-01-20 12:00:00"
    "unit" : ""
    "human_name" : "Start time"
    "type" : "date"
  },
  "end_time" : {
    "value" : "2025-01-20 12:30:00"
    "unit" : ""
    "human_name" : "End time"
    "type" : "date"
  }
}
```

