# RAH AI — Local PG16 + Local Ollama

## Run
```bash
docker compose up -d --build
docker compose exec api python -m app.init_db   # safe to run multiple times
```

## Create first user
```bash
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d '{
  "first_name":"Admin","last_name":"User","username":"admin",
  "email":"admin@example.com","branch":"HQ","location":"Mumbai",
  "password":"ChangeMe_123"
}'
```

## Open
- Web UI: http://localhost:5173 (login with admin / ChangeMe_123)
- API:    http://localhost:8000/docs

## Verify Ollama is running locally
```bash
# 1) Ollama version
ollama --version

# 2) API reachable
curl http://localhost:11434/api/version

# 3) List models
ollama list

# 4) Pull required models (if missing)
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 5) Test a quick generation
curl -s http://localhost:11434/api/generate -d '{"model":"llama3.1:8b","prompt":"Say hi"}'
```

If #2 fails, start Ollama (`open -a Ollama` on macOS) or ensure it listens on 11434.

## Notes
- DB is **local PostgreSQL 16** → DSN: `postgresql+asyncpg://rah:rahpw@host.docker.internal:5432/rah`
- JWT env: `JWT_SECRET`, `JWT_EXPIRE_HOURS` in docker-compose.yml
- Frontend stores JWT in localStorage and uses it for protected calls.
