-- One row per customer that still exists in the ERP
select customer_id, trim(name) as name, upper(city) as city, credit_limit, notes
from {{ src('customers') }}
