Index APIs	Create or update mappings
Create Or Update Mappings API
Introduced 1.0
If you want to create or add mappings and fields to an index, you can use the put mapping API operation. For an existing mapping, this operation updates the mapping.

You can’t use this operation to update mappings that already map to existing data in the index. You must first create a new index with your desired mappings, and then use the reindex API operation to map all the documents from your old index to the new index. If you don’t want any downtime while you re-index your indexes, you can use aliases.

Endpoints
PUT /<target-index>/_mapping
PUT /<target-index1>,<target-index2>/_mapping
Path parameters
The only required path parameter is the index with which to associate the mapping. If you don’t specify an index, you will get an error. You can specify a single index, or multiple indexes separated by a comma as follows:

PUT /<target-index>/_mapping
PUT /<target-index1>,<target-index2>/_mapping
Query parameters
Optionally, you can add query parameters to make a more specific request. For example, to skip any missing or closed indexes in the response, you can add the ignore_unavailable query parameter to your request as follows:

PUT /sample-index/_mapping?ignore_unavailable
The following table defines the put mapping query parameters:

Parameter	Data type	Description
allow_no_indices	Boolean	Whether to ignore wildcards that don’t match any indexes. Default is true.
expand_wildcards	String	Expands wildcard expressions to different indexes. Combine multiple values with commas. Available values are all (match all indexes), open (match open indexes), closed (match closed indexes), hidden (match hidden indexes), and none (do not accept wildcard expressions), which must be used with open, closed, or both. Default is open.
ignore_unavailable	Boolean	If true, OpenSearch does not include missing or closed indexes in the response.
cluster_manager_timeout	Time	How long to wait for a connection to the cluster manager node. Default is 30s.
timeout	Time	How long to wait for the response to return. Default is 30s.
write_index_only	Boolean	Whether OpenSearch should apply mapping updates only to the write index.
Request body fields
properties
The request body must contain properties, which has all of the mappings that you want to create or update.

{
  "properties":{
    "color":{
      "type": "text"
    },
    "year":{
      "type": "integer"
    }
  }
}
dynamic
You can make the document structure match the structure of the index mapping by setting the dynamic request body field to strict, as seen in the following example:

{
  "dynamic": "strict",
  "properties":{
    "color":{
      "type": "text"
    }
  }
}
Example request
The following request creates a new mapping for the sample-index index:

PUT /sample-index/_mapping

{
  "properties": {
    "age": {
      "type": "integer"
    },
    "occupation":{
      "type": "text"
    }
  }
}
Copy
Copy as cURL
Example response
Upon success, the response returns "acknowledged": true.

{
    "acknowledged": true
}







Type	Description
null	A null field can’t be indexed or searched. When a field is set to null, OpenSearch behaves as if the field has no value.
boolean	OpenSearch accepts true and false as Boolean values. An empty string is equal to false.
float	A single-precision, 32-bit IEEE 754 floating-point number, restricted to finite values.
double	A double-precision, 64-bit IEEE 754 floating-point number, restricted to finite values.
integer	A signed 32-bit number.
object	Objects are standard JSON objects, which can have fields and mappings of their own. For example, a movies object can have additional properties such as title, year, and director.
array	OpenSearch does not have a specific array data type. Arrays are represented as a set of values of the same data type (for example, integers or strings) associated with a field. When indexing, you can pass multiple values for a field, and OpenSearch will treat it as an array. Empty arrays are valid and recognized as array fields with zero elements—not as fields with no values. OpenSearch supports querying and filtering arrays, including checking for values, range queries, and array operations like concatenation and intersection. Nested arrays, which may contain complex objects or other arrays, can also be used for advanced data modeling.
text	A string sequence of characters that represent full-text values.
keyword	A string sequence of structured characters, such as an email address or ZIP code.
date detection string	Enabled by default, if new string fields match a date’s format, then the string is processed as a date field. For example, date: "2012/03/11" is processed as a date.
numeric detection string	If disabled, OpenSearch may automatically process numeric values as strings when they should be processed as numbers. When enabled, OpenSearch can process strings into long, integer, short, byte, double, float, half_float, scaled_float, and unsigned_long. Default is disabled.
Dynamic templates
Dynamic templates are used to define custom mappings for dynamically added fields based on the data type, field name, or field path. They allow you to define a flexible schema for your data that can automatically adapt to changes in the structure or format of the input data.

You can use the following syntax to define a dynamic mapping template:

PUT index
{
  "mappings": {
    "dynamic_templates": [
        {
          "fields": {
            "mapping": {
              "type": "short"
            },
            "match_mapping_type": "string",
            "path_match": "status*"
          }
        }
    ]
  }
}
Copy
Copy as cURL
This mapping configuration dynamically maps any field with a name starting with status (for example, status_code) to the short data type if the initial value provided during indexing is a string.

Dynamic mapping parameters
The dynamic_templates support the following parameters for matching conditions and mapping rules. The default value is null.

Parameter	Description
match_mapping_type	Specifies the JSON data type (for example, string, long, double, object, binary, Boolean, date) that triggers the mapping.
match	A regular expression used to match field names and apply the mapping.
unmatch	A regular expression used to exclude field names from the mapping.
match_pattern	Determines the pattern matching behavior, either regex or simple. Default is simple.
path_match	Allows you to match nested field paths using a regular expression.
path_unmatch	Excludes nested field paths from the mapping using a regular expression.
mapping	The mapping configuration to apply.
Explicit mapping
If you know exactly which field data types you need to use, then you can specify them in your request body when creating your index, as shown in the following example request:

PUT sample-index1
{
  "mappings": {
    "properties": {
      "year":    { "type" : "text" },
      "age":     { "type" : "integer" },
      "director":{ "type" : "text" }
    }
  }
}
Copy
Copy as cURL
Response
{
    "acknowledged": true,
    "shards_acknowledged": true,
    "index": "sample-index1"
}
Copy
Copy as cURL
To add mappings to an existing index or data stream, you can send a request to the _mapping endpoint using the PUT or POST HTTP method, as shown in the following example request:

POST sample-index1/_mapping
{
  "properties": {
    "year":    { "type" : "text" },
    "age":     { "type" : "integer" },
    "director":{ "type" : "text" }
  }
}
Copy
Copy as cURL
You cannot change the mapping of an existing field, you can only modify the field’s mapping parameters.

Mapping parameters
Mapping parameters are used to configure the behavior of index fields. See Mappings and field types for more information.

Mapping limit settings
OpenSearch has certain mapping limits and settings, such as the settings listed in the following table. Settings can be configured based on your requirements.

Setting	Default value	Allowed value	Type	Description
index.mapping.nested_fields.limit	50	[0,)	Dynamic	Limits the maximum number of nested fields that can be defined in an index mapping.
index.mapping.nested_objects.limit	10,000	[0,)	Dynamic	Limits the maximum number of nested objects that can be created in a single document.
index.mapping.total_fields.limit	1,000	[0,)	Dynamic	Limits the maximum number of fields that can be defined in an index mapping.
index.mapping.depth.limit	20	[1,100]	Dynamic	Limits the maximum depth of nested objects and nested fields that can be defined in an index mapping.
index.mapping.field_name_length.limit	50,000	[1,50000]	Dynamic	Limits the maximum length of field names that can be defined in an index mapping.
index.mapper.dynamic	true	{true,false}	Dynamic	Determines whether new fields should be dynamically added to a mapping.
Get a mapping
To get all mappings for one or more indexes, use the following request:

GET <index>/_mapping
Copy
Copy as cURL
In the previous request, <index> may be an index name or a comma-separated list of index names.

To get all mappings for all indexes, use the following request:

GET _mapping
Copy
Copy as cURL
To get a mapping for a specific field, provide the index name and the field name:

GET _mapping/field/<fields>
GET /<index>/_mapping/field/<fields>
Copy
Copy as cURL
Both <index> and <fields> can be specified as either one value or a comma-separated list. For example, the following request retrieves the mapping for the year and age fields in sample-index1:

GET sample-index1/_mapping/field/year,age
Copy
Copy as cURL
The response contains the specified fields:

{
  "sample-index1" : {
    "mappings" : {
      "year" : {
        "full_name" : "year",
        "mapping" : {
          "year" : {
            "type" : "text"
          }
        }
      },
      "age" : {
        "full_name" : "age",
        "mapping" : {
          "age" : {
            "type" : "integer"
          }
        }
      }
    }
  }
}
Copy
Copy as cURL
Mappings use cases
See Mappings use cases for use case examples, including examples of mapping string fields and ignoring malformed IP addresses.