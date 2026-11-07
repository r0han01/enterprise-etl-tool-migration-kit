select order_id, customer_id, order_date, status
from {{ src('orders') }}
