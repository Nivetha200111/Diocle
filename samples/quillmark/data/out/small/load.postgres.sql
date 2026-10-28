-- SYNTHETIC SAMPLE - written for the Diocle hackathon project.
-- Fictional company. Not derived from any real system, employer, or client.

-- Run from this output directory: psql -v ON_ERROR_STOP=1 -f load.postgres.sql
-- Create the empty schema first using db2/schema.postgres.sql.
-- Each CSV has exactly two synthetic notice lines before its column header.
\set ON_ERROR_STOP on
BEGIN;
\copy product (product_id,product_name,currency) FROM PROGRAM 'tail -n +3 csv/product.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy customer (customer_id,display_name,full_name,customer_kind,open_date,status) FROM PROGRAM 'tail -n +3 csv/customer.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy customer_address (customer_id,address_seq,street,city,delivery_note) FROM PROGRAM 'tail -n +3 csv/customer_address.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy rate_table (product_id,effective_date,annual_rate) FROM PROGRAM 'tail -n +3 csv/rate_table.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy account (account_no,customer_id,product_id,balance,annual_rate,open_date,status) FROM PROGRAM 'tail -n +3 csv/account.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy account_holder (account_no,customer_id,holder_role) FROM PROGRAM 'tail -n +3 csv/account_holder.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy payment_batch (batch_id,business_date,created_at,status) FROM PROGRAM 'tail -n +3 csv/payment_batch.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy "TRANSACTION" (txn_id,account_no,posted_date,amount,txn_type,detail) FROM PROGRAM 'tail -n +3 csv/transaction.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy payment (payment_id,txn_id,batch_id,channel,amount) FROM PROGRAM 'tail -n +3 csv/payment.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy card (card_id,account_no,invalid_pan,expiry_date,status) FROM PROGRAM 'tail -n +3 csv/card.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy card_auth (card_id,auth_seq,auth_at,amount,decision) FROM PROGRAM 'tail -n +3 csv/card_auth.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy fee_schedule (product_id,fee_code,effective_date,amount) FROM PROGRAM 'tail -n +3 csv/fee_schedule.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy gl_account (gl_code,description) FROM PROGRAM 'tail -n +3 csv/gl_account.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy gl_posting (txn_id,line_no,gl_code,amount) FROM PROGRAM 'tail -n +3 csv/gl_posting.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
\copy fraud_alert (alert_id,txn_id,severity,reason) FROM PROGRAM 'tail -n +3 csv/fraud_alert.csv' WITH (FORMAT csv, HEADER true, NULL '\N')
COMMIT;
