WITH order_items_agg AS (
  SELECT
    DATE_TRUNC('MONTH', orders.ordered_at) AS orders__ordered_at__month,
    SUM(
      CASE
        WHEN (
          orders.status
        ) IN ('paid', 'refunded')
        THEN order_items.quantity * order_items.unit_price
      END
    ) AS item_total__f0
  FROM poc.order_items AS order_items
  LEFT JOIN poc.orders AS orders
    ON order_items.order_id = orders.order_id
  LEFT JOIN poc.customers AS customers
    ON orders.customer_id = customers.customer_id
  WHERE
    customers.carteira = 'Varejo'
    AND customers.carteira = 'Varejo'
    AND customers.carteira = 'Varejo'
  GROUP BY
    DATE_TRUNC('MONTH', orders.ordered_at)
), refunds_agg AS (
  SELECT
    DATE_TRUNC('MONTH', orders.ordered_at) AS orders__ordered_at__month,
    SUM(CASE WHEN (
      refunds.status
    ) = 'completed' THEN refunds.amount END) AS refund_value__f0
  FROM poc.refunds AS refunds
  LEFT JOIN poc.orders AS orders
    ON refunds.order_id = orders.order_id
  LEFT JOIN poc.customers AS customers
    ON orders.customer_id = customers.customer_id
  WHERE
    customers.carteira = 'Varejo'
    AND customers.carteira = 'Varejo'
    AND customers.carteira = 'Varejo'
  GROUP BY
    DATE_TRUNC('MONTH', orders.ordered_at)
), orders_agg AS (
  SELECT
    DATE_TRUNC('MONTH', orders.ordered_at) AS orders__ordered_at__month,
    COUNT(CASE WHEN (
      orders.status
    ) IN ('paid', 'refunded') THEN 1 END) AS order_count__f0
  FROM poc.orders AS orders
  LEFT JOIN poc.customers AS customers
    ON orders.customer_id = customers.customer_id
  WHERE
    customers.carteira = 'Varejo' AND customers.carteira = 'Varejo'
  GROUP BY
    DATE_TRUNC('MONTH', orders.ordered_at)
), dimensions AS (
  SELECT
    orders__ordered_at__month
  FROM order_items_agg
  UNION
  SELECT
    orders__ordered_at__month
  FROM refunds_agg
  UNION
  SELECT
    orders__ordered_at__month
  FROM orders_agg
)
SELECT
  dimensions.orders__ordered_at__month AS orders__ordered_at__month,
  order_items_agg.item_total__f0 AS gross_revenue,
  refunds_agg.refund_value__f0 AS refunds_completed,
  (
    order_items_agg.item_total__f0 - COALESCE(refunds_agg.refund_value__f0, 0)
  ) AS net_revenue,
  (
    CAST(order_items_agg.item_total__f0 AS DOUBLE) / NULLIF(orders_agg.order_count__f0, 0)
  ) AS average_order_value,
  (
    CAST(refunds_agg.refund_value__f0 AS DOUBLE) / NULLIF(order_items_agg.item_total__f0, 0)
  ) AS refund_rate
FROM dimensions
LEFT JOIN order_items_agg
  ON dimensions.orders__ordered_at__month IS NOT DISTINCT FROM order_items_agg.orders__ordered_at__month
LEFT JOIN refunds_agg
  ON dimensions.orders__ordered_at__month IS NOT DISTINCT FROM refunds_agg.orders__ordered_at__month
LEFT JOIN orders_agg
  ON dimensions.orders__ordered_at__month IS NOT DISTINCT FROM orders_agg.orders__ordered_at__month