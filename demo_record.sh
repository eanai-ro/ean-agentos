#!/bin/bash
# Demo script — rulează în container fresh
# Populează DB cu erori reale, apoi arată mem suggest

cd /app/scripts

echo ""
echo "🧠 EAN AgentOS — Demo"
echo "   Never solve the same bug twice."
echo ""
sleep 2

# 1. Populează cu erori + soluții reale
echo "📝 Session 1: Saving solutions from past debugging sessions..."
sleep 1

python3 -c "
from v2_common import get_db
conn = get_db()

# CORS error
conn.execute('''INSERT INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name, created_at)
    VALUES ('CORS error: blocked by CORS policy - No Access-Control-Allow-Origin header',
            'Add flask-cors middleware and configure CORS(app, resources)',
            'pip install flask-cors\nfrom flask_cors import CORS\nCORS(app)',
            1, 'claude-code', '2026-01-12 14:30:00')''')

# ModuleNotFoundError
conn.execute('''INSERT INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name, created_at)
    VALUES ('ModuleNotFoundError: No module named redis',
            'Install redis package with pip',
            'pip install redis',
            1, 'gemini-cli', '2026-02-05 09:15:00')''')

# PostgreSQL connection
conn.execute('''INSERT INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name, created_at)
    VALUES ('psycopg2.OperationalError: connection refused - PostgreSQL not running',
            'Start PostgreSQL service and verify it is running on port 5432',
            'sudo systemctl start postgresql\nsudo systemctl status postgresql',
            1, 'codex-cli', '2026-02-18 16:45:00')''')

# JWT expired
conn.execute('''INSERT INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name, created_at)
    VALUES ('jwt.exceptions.ExpiredSignatureError: Signature has expired',
            'Token was expired. Refresh token before API call or increase token TTL',
            'token = jwt.encode(payload, secret, algorithm=\"HS256\")\n# Set exp to 24h: exp=datetime.utcnow() + timedelta(hours=24)',
            1, 'claude-code', '2026-03-01 11:20:00')''')

# Docker permission
conn.execute('''INSERT INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name, created_at)
    VALUES ('PermissionError: docker.sock permission denied - Cannot connect to Docker daemon',
            'Add user to docker group and restart session',
            'sudo usermod -aG docker \$USER\nnewgrp docker',
            1, 'kimi-cli', '2026-03-10 08:30:00')''')

conn.commit()
conn.close()
print('  ✅ 5 solutions saved from past sessions')
"
sleep 2

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Session 2: 3 months later... same errors appear"
echo ""
sleep 2

# 2. Demonstrează mem suggest
echo '$ mem suggest "CORS error"'
echo ""
sleep 1
python3 solution_index.py suggest "CORS error"
sleep 3

echo ""
echo '$ mem suggest "module not found redis"'
echo ""
sleep 1
python3 solution_index.py suggest "module not found redis"
sleep 3

echo ""
echo '$ mem suggest "docker permission denied"'
echo ""
sleep 1
python3 solution_index.py suggest "docker permission denied"
sleep 3

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🧠 Never solve the same bug twice."
echo "   https://github.com/eanai-ro/ean-agentos"
echo ""
sleep 2
