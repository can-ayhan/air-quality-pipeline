{#- Use the configured schema as it is (staging, marts, reference) instead of prefixing it with the target schema. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
