chmod o+x cfmrda/srv.py cfmrda/export.py cfmrda/send_cfm_requests.py
chown postgres:postgres cfmrda.sql
cp cfmrda/*.py ../cfmrda
cp cfmrda/schemas.json ../cfmrda
systemctl restart cfmrda
