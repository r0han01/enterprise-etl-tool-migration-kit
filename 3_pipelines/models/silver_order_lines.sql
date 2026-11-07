select order_id, line_no, item_id, qty, line_amount
from {{ src('order_lines') }}
