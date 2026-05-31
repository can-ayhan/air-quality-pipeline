{#- Fails for UTC timestamps later than now (plus a tolerance): a clock or time-zone mistake upstream. -#}
{% test not_in_future(model, column_name, tolerance_hours=1) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} > (now() at time zone 'utc') + interval '{{ tolerance_hours }} hours'

{% endtest %}
