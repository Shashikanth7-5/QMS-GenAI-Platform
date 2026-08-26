# Load testing (Locust)

Locust-based load harness for the QMS GenAI Platform. Not executed in CI -
requires a live app.

## Install

```
pip install locust
```

## Environment

```
export QMS_HOST=https://qms.example.com
export QMS_TENANT=your-tenant-id
export QMS_API_KEY=your-tenant-api-key
```

On Windows PowerShell:

```
$env:QMS_HOST = "https://qms.example.com"
$env:QMS_TENANT = "your-tenant-id"
$env:QMS_API_KEY = "your-tenant-api-key"
```

## Run the target scenario (100 users, 30s ramp, 5m headless)

```
locust -f tests/load/locustfile.py --host $QMS_HOST --users 100 --spawn-rate 10 --run-time 5m --headless
```

## Interactive UI

```
locust -f tests/load/locustfile.py --host $QMS_HOST
```

Then open http://localhost:8089.

## User classes

- `AnonymousUser` - probes `/healthz` and `/readyz`
- `TenantUser`    - authenticated tenant traffic against `/api/v1/records`
                    and `/api/v1/capa/generate` (with a fresh `Idempotency-Key`
                    per request)

The `TenantUser` weight is 4x `AnonymousUser` to approximate real traffic mix.
