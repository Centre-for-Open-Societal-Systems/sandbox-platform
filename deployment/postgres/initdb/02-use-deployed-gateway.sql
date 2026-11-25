-- Runs once, after 01-oan-sandbox-data.sql.gz, on the first start.
--
-- The snapshot comes from a developer machine where some end-points (all in
-- the retired, deleted product "OAN Access to Credit (A2C)") stored the local
-- Kong address. An end-point's own URL wins over GATEWAY_SANDBOX_URL, so clear
-- those addresses: every gateway call then goes to the Kong deployed for the
-- environment.
UPDATE public.endpoint SET sandbox_api_url = NULL
 WHERE sandbox_api_url ~* '^https?://(localhost|127\.0\.0\.1|kong|host\.docker\.internal)(:[0-9]+)?/?$';
UPDATE public.endpoint SET uat_api_url = NULL
 WHERE uat_api_url ~* '^https?://(localhost|127\.0\.0\.1|kong|host\.docker\.internal)(:[0-9]+)?/?$';
UPDATE public.endpoint SET prod_api_url = NULL
 WHERE prod_api_url ~* '^https?://(localhost|127\.0\.0\.1|kong|host\.docker\.internal)(:[0-9]+)?/?$';
