-- What the reports read: orders and revenue per day
select o.order_date, count(distinct o.order_id) as orders, sum(l.line_amount) as revenue
from {{ ref('silver_orders') }} o
join {{ ref('silver_order_lines') }} l using (order_id)
group by o.order_date
